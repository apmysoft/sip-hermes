#!/bin/sh
# Decidir lotes desde Hermes PERSONAL con código por Telegram (root, en Neo, desde ~/sip-inventario).
# Instala el gestor y el puente nuevos, la unidad (grupo sip-notify y bandeja de avisos) y la skill
# en los perfiles de PERSONAL. No decide ni aplica ningún lote.
# Rollback: cp -p $B/sip-gestor-request.py $B/gestor-entrada.py /usr/local/bin/
#           cp -p $B/sip-gestor-bridge.service /etc/systemd/system/ && systemctl daemon-reload
#           rm /etc/systemd/system/sip-gestor-permisos.service /usr/local/bin/sip-gestor-permisos.py
#           for p in personal default sandbox; do cp -p $B/SKILL-$p.md $V/profiles/$p/skills/gestor-entrada/SKILL.md; done
#           rm -rf /var/lib/sip-gestor-entrada/borradores
#           setfacl -k ${DOCKER_DATA}/hermes/workspace/_gestor/requests   (ACL por defecto; ver $B/acl-requests.txt)
set -eu
cd "$(dirname "$0")"
B=/root/sip-agent-backups/2026-11-03/gestor-puente
V=${DOCKER_DATA}/docker_root/volumes/hermes_hermes-home/_data
install -d -m 0700 "$B"
if [ ! -e "$B/sip-gestor-request.py" ]; then
  cp -p /usr/local/bin/sip-gestor-request.py /usr/local/bin/gestor-entrada.py \
    /etc/systemd/system/sip-gestor-bridge.service "$B/"
  for p in personal default sandbox; do cp -p "$V/profiles/$p/skills/gestor-entrada/SKILL.md" "$B/SKILL-$p.md"; done
fi

install -o root -g sip-gestor -m 0755 gestor-entrada.py /usr/local/bin/
install -o root -g root -m 0755 sip-gestor-request.py /usr/local/bin/
install -o root -g root -m 0755 sip-gestor-permisos.py /usr/local/bin/
install -o root -g root -m 0644 sip-gestor-bridge.service sip-gestor-permisos.service /etc/systemd/system/
systemctl daemon-reload
for p in personal default sandbox; do
  install -o 1000 -g 1000 -m 0640 SKILL.md "$V/profiles/$p/skills/gestor-entrada/SKILL.md"
done

# El terminal de Hermes trabaja con umask 077: sus peticiones salían 0600 y sip-gestor no las leía
# (PermissionError). Con ACL por defecto el umask no se aplica y salen 0660 (grupo sip-gestor por setgid).
Q=${DOCKER_DATA}/hermes/workspace/_gestor/requests
[ -e "$B/acl-requests.txt" ] || getfacl -p "$Q" > "$B/acl-requests.txt"
setfacl -d -m u::rw,g::rw,o::- "$Q"

# La unidad puede escribir en la bandeja de avisos (sin mandar nada: un .tmp que se borra).
systemd-run --quiet --wait --collect -p User=sip-gestor -p Group=sip-gestor -p SupplementaryGroups=sip-notify \
  -p ProtectSystem=strict -p ReadWritePaths=/var/lib/sip-notify/outbox \
  sh -c 'touch /var/lib/sip-notify/outbox/.prueba-gestor.tmp && rm /var/lib/sip-notify/outbox/.prueba-gestor.tmp'
echo "bandeja de avisos: escribible por la unidad del puente"

# Petición real desde el contenedor de PERSONAL (uid 1000): lotes escrita con modo 0600 explícito, como
# la herramienta de ficheros de Hermes, y un proponer inválido (no avisa).
ID=prueba-$(date +%Y%m%d-%H%M%S)
docker exec -u 1000 hermes-webui python3 -c "
import os
fd = os.open('/workspace/_gestor/requests/$ID-l.json', os.O_WRONLY | os.O_CREAT, 0o600)
os.write(fd, b'{\"id\":\"$ID-l\",\"action\":\"lotes\"}'); os.close(fd)"
docker exec -u 1000 hermes-webui sh -c "echo '{\"id\":\"$ID-p\",\"action\":\"proponer\",\"lote\":\"lote-20261029-120413\",\"modo\":\"rm\"}' > /workspace/_gestor/requests/$ID-p.json"
R=${DOCKER_DATA}/hermes/workspace/_gestor/results
for _ in $(seq 30); do [ -e "$R/$ID-l.json" ] && [ -e "$R/$ID-p.json" ] && break; sleep 1; done
python3 -I - "$R/$ID-l.json" "$R/$ID-p.json" <<'EOF'
import json, sys
l, p = (json.load(open(f)) for f in sys.argv[1:])
assert l["ok"] and "pendiente" in l["stdout"], l
assert not p["ok"] and "modo" in p["error"], p
print("lotes desde PERSONAL:", sum(1 for x in l["stdout"].splitlines() if "\tpendiente\t" in x), "pendientes")
print("proponer inválido rechazado:", p["error"])
EOF
echo "RESULTADO: OK. Copia previa en $B"
