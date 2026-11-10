#!/bin/sh
# Apagado de HALO, parte de Neo (05-11). Root, en Neo, desde este directorio.
#   sudo sh apply.sh clave           # 1) genera la clave de sip-wol e imprime la pública (para ../halo/apply.sh)
#   sudo sh apply.sh instalar "<línea known_hosts de HALO>"   # 2) instala, tras ../halo/apply.sh
# Rollback: sh $B/rollback.sh
set -eu
cd "$(dirname "$0")"
S=/var/lib/sip-energia
W=${DOCKER_DATA}/hermes/workspace
V=${DOCKER_DATA}/docker_root/volumes/hermes_hermes-home/_data
case "${1:-}" in
clave)
  install -d -o sip-wol -g sip-wol -m 700 "$S"
  [ -f "$S/id_ed25519" ] || runuser -u sip-wol -- ssh-keygen -q -t ed25519 -N '' -C sip-energia@neo -f "$S/id_ed25519"
  cat "$S/id_ed25519.pub" ;;
instalar)
  KH=${2:?falta la línea known_hosts de HALO}
  echo "$KH" | grep -qE '^${HALO_TAILNET_IP} ssh-ed25519 [A-Za-z0-9+/=]+$' || { echo "ERROR: known_hosts no válido" >&2; exit 1; }
  B=/root/sip-agent-backups/$(date +%F)/energia-neo
  [ ! -e "$B" ] || { echo "ERROR: ya existe $B" >&2; exit 1; }
  install -d -m 700 "$B"
  cat > "$B/rollback.sh" <<R
#!/bin/sh
systemctl disable --now sip-energia-auto.timer sip-energia.path
rm -f /etc/systemd/system/sip-energia-auto.service /etc/systemd/system/sip-energia-auto.timer \\
      /etc/systemd/system/sip-energia.service /etc/systemd/system/sip-energia.path /usr/local/sbin/sip-energia.py
rm -rf $W/_energia $V/skills/halo-energia $V/profiles/personal/skills/halo-energia
systemctl daemon-reload
echo "La clave de $S queda: bórrala (rm -rf $S) y quita la línea de HALO (/var/lib/sip-energia/.ssh/authorized_keys)."
R
  echo "copia en $B (no había nada previo)"
  echo "$KH" > "$S/known_hosts"; chown sip-wol:sip-wol "$S/known_hosts"; chmod 600 "$S/known_hosts"
  install -o root -g root -m 0755 sip-energia.py /usr/local/sbin/sip-energia.py
  install -d -o usuario -g sip-wol -m 2750 "$W/_energia"
  install -d -o usuario -g sip-wol -m 2770 "$W/_energia/requests" "$W/_energia/results"
  setfacl -d -m u:sip-wol:rw "$W/_energia/requests"
  for d in "$V/profiles/personal" "$V"; do
    install -d -o 1000 -g 1000 -m 0750 "$d/skills/halo-energia"
    install -o 1000 -g 1000 -m 0640 halo-energia/SKILL.md "$d/skills/halo-energia/SKILL.md"
  done
  install -o root -g root -m 0644 sip-energia-auto.service sip-energia-auto.timer sip-energia.service sip-energia.path /etc/systemd/system/
  systemctl daemon-reload
  echo "== verificación"
  r=$(runuser -u sip-wol -- ssh -F /dev/null -i $S/id_ed25519 -o IdentitiesOnly=yes -o BatchMode=yes \
      -o UserKnownHostsFile=$S/known_hosts -o StrictHostKeyChecking=yes sip-energia@${HALO_TAILNET_IP} estado)
  echo "$r" | python3 -c 'import json,sys; d=json.load(sys.stdin); print("estado de HALO:", len(d["bloqueos"]), "bloqueo(s),", d["inactivo_min"], "min sin actividad")'
  r=$(runuser -u sip-wol -- ssh -F /dev/null -i $S/id_ed25519 -o IdentitiesOnly=yes -o BatchMode=yes \
      -o UserKnownHostsFile=$S/known_hosts -o StrictHostKeyChecking=yes sip-energia@${HALO_TAILNET_IP} "cat /etc/passwd" || true)
  echo "orden no permitida -> $r"
  systemctl start sip-energia-auto.service; journalctl -u sip-energia-auto -n 3 --no-pager -o cat | tail -2
  systemctl enable --now sip-energia-auto.timer sip-energia.path
  systemctl is-active sip-energia-auto.timer sip-energia.path
  echo "RESULTADO: OK (rollback: sh $B/rollback.sh)" ;;
*) echo "uso: apply.sh clave | instalar <known_hosts>" >&2; exit 2 ;;
esac
