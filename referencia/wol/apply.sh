#!/bin/sh
# Instala el emisor WOL en Neo (root). No toca firewall.
# Rollback: systemctl disable --now sip-wol-halo.path; borrar las unidades, el script
# y ${DOCKER_DATA}/hermes/workspace/_wol; setfacl -x u:sip-wol en la cadena; userdel sip-wol.
set -eu
cd "$(dirname "$0")"
W=${DOCKER_DATA}/hermes/workspace
id sip-wol >/dev/null 2>&1 || useradd --system --no-create-home --shell /usr/sbin/nologin sip-wol
for d in ${DOCKER_DATA} ${DOCKER_DATA}/hermes "$W"; do setfacl -m u:sip-wol:x "$d"; done
install -d -o usuario -g sip-wol -m 2750 "$W/_wol"
install -d -o usuario -g sip-wol -m 2770 "$W/_wol/requests" "$W/_wol/results"
install -o root -g root -m 0755 sip-wol-halo.py /usr/local/sbin/sip-wol-halo.py
install -o root -g root -m 0644 sip-wol-halo.path sip-wol-halo.service /etc/systemd/system/
systemctl daemon-reload
systemctl enable --now sip-wol-halo.path
systemctl is-active sip-wol-halo.path
