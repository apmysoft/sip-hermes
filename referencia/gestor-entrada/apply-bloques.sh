#!/bin/sh
# Revisión por bloques de 10 en el puente (root, en Neo, desde ~/sip-inventario/sip-config/gestor-entrada).
# Instala el puente (ver con bloque, anotar, proponer anotado) y la skill en los perfiles de PERSONAL.
# No decide ni aplica nada: prueba sobre un lote ya aplicado, que proponer rechaza sin mandar código.
# Rollback: cp -p $B/sip-gestor-request.py /usr/local/bin/
#           for p in personal default sandbox; do cp -p $B/SKILL-$p.md $V/profiles/$p/skills/gestor-entrada/SKILL.md; done
set -eu
cd "$(dirname "$0")"
B=/root/sip-agent-backups/$(date +%F)/gestor-bloques
V=${DOCKER_DATA}/docker_root/volumes/hermes_hermes-home/_data
L=lote-20261029-232339
install -d -m 0700 "$B"
if [ ! -e "$B/sip-gestor-request.py" ]; then
  cp -p /usr/local/bin/sip-gestor-request.py "$B/"
  for p in personal default sandbox; do cp -p "$V/profiles/$p/skills/gestor-entrada/SKILL.md" "$B/SKILL-$p.md"; done
fi
install -o root -g root -m 0755 sip-gestor-request.py /usr/local/bin/
for p in personal default sandbox; do
  install -o 1000 -g 1000 -m 0640 SKILL.md "$V/profiles/$p/skills/gestor-entrada/SKILL.md"
done

# Peticiones reales desde el contenedor de PERSONAL, con 0600 como la herramienta de ficheros de Hermes.
ID=prueba-$(date +%Y%m%d-%H%M%S)
docker exec -u 1000 hermes-webui python3 -c "
import json, os
for sufijo, req in (('v', {'action': 'ver', 'lote': '$L', 'bloque': 5}),
                    ('a', {'action': 'anotar', 'lote': '$L', 'bloque': 1, 'modo': 'todo', 'veto': [12]}),
                    ('p', {'action': 'proponer', 'lote': '$L', 'modo': 'anotado'})):
    fd = os.open(f'/workspace/_gestor/requests/$ID-{sufijo}.json', os.O_WRONLY | os.O_CREAT, 0o600)
    os.write(fd, json.dumps({'id': f'$ID-{sufijo}', **req}).encode()); os.close(fd)"
R=${DOCKER_DATA}/hermes/workspace/_gestor/results
for _ in $(seq 30); do [ -e "$R/$ID-v.json" ] && [ -e "$R/$ID-a.json" ] && [ -e "$R/$ID-p.json" ] && break; sleep 1; done
python3 -I - "$R/$ID-v.json" "$R/$ID-a.json" "$R/$ID-p.json" "$R" <<'EOF'
import json, sys
v, a, p = (json.load(open(f)) for f in sys.argv[1:4])
assert v["ok"] and v["bloques"] == 5 and v["items"] == [41, 50], v
txt = open(sys.argv[4] + "/" + v["informe"].split("/results/", 1)[1]).read().splitlines()
assert sum(1 for l in txt if l[:1].isdigit()) == 10, "el bloque no trae 10 ítems"
assert not a["ok"] and "fuera del bloque 1" in a["error"], a
assert not p["ok"] and "faltan bloques por anotar: 1-5" in p["error"], p
print("ver bloque 5: ítems 41-50 (10 líneas numeradas)")
print("anotar con un ítem de otro bloque: rechazado")
print("proponer anotado sin bloques: rechazado, sin código")
EOF
echo "RESULTADO: OK. Copia previa en $B"
