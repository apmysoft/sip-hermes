#!/bin/sh
# Integridad de binarios (v2.4 M.14), en Neo como root.
# 1. Lo que ejecuta o carga root pasa a root:root (había 2 scripts y 3 unidades de usuario).
# 2. filegate verifica su sha256 antes de cada conexión, contra un manifiesto solo de root.
# Rollback: rm -r /etc/systemd/system/filegate@.service.d/10-integridad.conf; systemctl daemon-reload;
# propietarios y modos originales en $B/stat.txt (chown/chmod a mano).
set -eu
B=/root/sip-agent-backups/$(date +%F)/integridad-$(date +%H%M%S)
M=/etc/sip-integridad
D=/etc/systemd/system/filegate@.service.d
SOCK=/run/filegate.sock
FICH="/usr/local/bin/filegate-ttl.sh /usr/local/bin/sip-docker-user-ssh.sh"
UNID="/etc/systemd/system/filegate-ttl.service /etc/systemd/system/filegate-ttl.timer /etc/systemd/system/sip-docker-user-ssh.service"

mkdir -p "$B"
stat -c '%U:%G %a %n' $FICH $UNID /usr/local/bin/filegate.sh > "$B/stat.txt"
cp -a $FICH $UNID /etc/systemd/system/filegate@.service "$B/"
echo "copia previa en $B"

chown root:root $FICH $UNID
chmod 0755 $FICH
chmod 0644 $UNID

sonda() { printf 'x\n' | timeout 10 socat -t 5 - "UNIX-CONNECT:$SOCK" 2>/dev/null || true; }

install -d -o root -g root -m 0700 "$M"
sha256sum /usr/local/bin/filegate.sh > "$M/filegate.sha256"
chmod 0600 "$M/filegate.sha256"
install -d -o root -g root -m 0755 "$D"
cat > "$D/10-integridad.conf" <<'EOF'
# v2.4 M.14: no arrancar si filegate.sh no coincide con el manifiesto solo de root.
[Service]
# --status: sin salida (la salida estándar de la unidad es el socket del cliente).
ExecStartPre=+/usr/bin/sha256sum --status --strict -c /etc/sip-integridad/filegate.sha256
EOF
chmod 0644 "$D/10-integridad.conf"
systemctl daemon-reload

# Positiva: filegate responde.
r=$(sonda); echo "con manifiesto bueno: $r"
case "$r" in "ERROR cabecera incompleta"*) ;; *) echo "FALLO: filegate no responde"; exit 1 ;; esac

# Negativa: con un hash falso no debe arrancar. Se restaura pase lo que pase.
cp -a "$M/filegate.sha256" "$B/manifiesto.bueno"
trap 'cp -a "$B/manifiesto.bueno" "$M/filegate.sha256"' EXIT
printf '%064d  /usr/local/bin/filegate.sh\n' 0 > "$M/filegate.sha256"
r=$(sonda); echo "con manifiesto falso: '${r}'"
cp -a "$B/manifiesto.bueno" "$M/filegate.sha256"; trap - EXIT
[ -z "$r" ] || { echo "FALLO: filegate arrancó con un hash falso"; exit 1; }

r=$(sonda)
case "$r" in "ERROR cabecera incompleta"*) ;; *) echo "FALLO: filegate no responde tras restaurar"; exit 1 ;; esac
stat -c '%U:%G %a %n' $FICH $UNID "$M/filegate.sha256" "$D/10-integridad.conf"
echo "RESULTADO: OK"
