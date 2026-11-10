#!/bin/sh
# Instala el puente de stacks (05-11). Root, en Neo, desde este directorio.
# Rollback: systemctl disable --now sip-stacks-bridge.path; borrar las dos unidades,
#   /usr/local/sbin/sip-stacks-request.py, /usr/local/lib/sip-stacks y /var/lib/sip-stacks; daemon-reload;
#   borrar skills/servicios-docker de personal y raíz; restaurar sip-notify.py de $B.
set -eu
cd "$(dirname "$0")"
B=/root/sip-agent-backups/$(date +%F)/stacks-puente
V=${DOCKER_DATA}/docker_root/volumes/hermes_hermes-home/_data
install -d -m 700 "$B"
cp -p /usr/local/sbin/sip-notify.py "$B/"
install -o root -g root -m 0755 ../../notify/sip-notify.py /usr/local/sbin/sip-notify.py
install -o root -g root -m 0755 sip-stacks-request.py /usr/local/sbin/sip-stacks-request.py
install -d -o root -g root -m 0755 /usr/local/lib/sip-stacks
install -o root -g root -m 0755 ../actualizar-stack.sh /usr/local/lib/sip-stacks/actualizar-stack.sh
install -d -o root -g root -m 0700 /var/lib/sip-stacks /root/.docker
for s in "" /requests /results /processed; do install -d -o 1000 -g 1000 -m 0750 "${DOCKER_DATA}/hermes/workspace/_stacks$s"; done
install -o root -g root -m 0644 sip-stacks-bridge.path sip-stacks-bridge.service /etc/systemd/system/
for d in "$V/profiles/personal" "$V"; do
  install -d -o 1000 -g 1000 -m 0750 "$d/skills/servicios-docker"
  install -o 1000 -g 1000 -m 0640 servicios-docker/SKILL.md "$d/skills/servicios-docker/SKILL.md"
done
systemctl daemon-reload
systemctl enable --now sip-stacks-bridge.path
systemctl is-active sip-stacks-bridge.path
echo "copia en $B"
