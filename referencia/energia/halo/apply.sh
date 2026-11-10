#!/bin/sh
# Apagado de HALO, parte de HALO (05-11). Root, en HALO, desde este directorio.
# Uso: sudo sh apply.sh <clave-publica-de-neo.pub>   (la genera ../neo/apply.sh en Neo, como sip-wol)
# Rollback: sh $B/rollback.sh
set -eu
cd "$(dirname "$0")"
PUB=${1:?falta la clave pública de Neo}
grep -qE '^ssh-ed25519 [A-Za-z0-9+/=]+ sip-energia@neo$' "$PUB" || { echo "ERROR: clave pública no válida" >&2; exit 1; }
B=/root/sip-agent-backups/$(date +%F)/energia-halo
[ ! -e "$B" ] || { echo "ERROR: ya existe $B" >&2; exit 1; }
install -d -m 700 "$B"
ls -la /etc/polkit-1/rules.d/ > "$B/polkit-rules.d.txt"
cat > "$B/rollback.sh" <<R
#!/bin/sh
systemctl stop sip-apagado-programado.timer 2>/dev/null
rm -f /etc/polkit-1/rules.d/51-sip-energia.rules /etc/tmpfiles.d/sip-energia.conf /usr/local/sbin/sip-actividad.py \\
      /etc/systemd/system/sip-actividad.service /etc/systemd/system/sip-apagar-auto.service \\
      /etc/systemd/system/sip-apagar-usuario.service
rm -rf /usr/local/lib/sip-energia /var/lib/sip-energia /run/sip-energia /run/sip-energia-pet
userdel sip-energia
systemctl daemon-reload
R
echo "copia en $B"

id sip-energia >/dev/null 2>&1 || useradd --system --home-dir /var/lib/sip-energia --no-create-home \
  --shell /bin/sh sip-energia
passwd -l sip-energia >/dev/null
install -d -o root -g root -m 755 /var/lib/sip-energia /var/lib/sip-energia/.ssh
printf 'from="${NEO_TAILNET_IP}",command="/usr/local/lib/sip-energia/orden",restrict %s\n' "$(cat "$PUB")" \
  > /var/lib/sip-energia/.ssh/authorized_keys
chmod 644 /var/lib/sip-energia/.ssh/authorized_keys
install -d -o root -g root -m 755 /usr/local/lib/sip-energia
install -o root -g root -m 755 orden /usr/local/lib/sip-energia/orden
install -o root -g root -m 755 sip-actividad.py /usr/local/sbin/sip-actividad.py
install -o root -g root -m 644 sip-energia.tmpfiles /etc/tmpfiles.d/sip-energia.conf
install -o root -g root -m 644 51-sip-energia.rules /etc/polkit-1/rules.d/51-sip-energia.rules
install -o root -g root -m 644 sip-actividad.service sip-apagar-auto.service sip-apagar-usuario.service /etc/systemd/system/
systemd-tmpfiles --create /etc/tmpfiles.d/sip-energia.conf
systemctl daemon-reload
systemctl start sip-actividad.service
echo "== verificación"
ls -ld /run/sip-energia /run/sip-energia-pet; ls -l /var/lib/sip-energia/.ssh/authorized_keys
sshd -T -C user=sip-energia,host=neo,addr=${NEO_TAILNET_IP} 2>/dev/null | grep -E "^(permittty|allowtcpforwarding) " || true
python3 -c 'import json; d=json.load(open("/run/sip-energia/estado.json")); print("muestra:", len(d["bloqueos"]), "bloqueos,", d["inactivo_min"], "min inactivo")'
echo "RESULTADO: OK (rollback: sh $B/rollback.sh)"
