#!/bin/sh
# Instala el canal de avisos del host y conecta el WOL. Uso en Neo: sudo sh apply.sh
# (con sip-notify.* y ../wol junto a este directorio). Requiere /root/sip-telegram.env.
# Rollback: systemctl disable --now sip-notify.path; borrar sus unidades, el script y
#   /var/lib/sip-notify; restaurar de $B sip-wol-halo.py y sip-wol-halo.service;
#   daemon-reload; userdel sip-notify.
set -eu
cd "$(dirname "$0")"
[ -f /root/sip-telegram.env ] || { echo "ERROR: falta /root/sip-telegram.env" >&2; exit 1; }
B=/root/sip-agent-backups/$(date +%F)/notify
mkdir -p "$B"
cp -p /usr/local/sbin/sip-wol-halo.py /etc/systemd/system/sip-wol-halo.service "$B/"
id sip-notify >/dev/null 2>&1 || useradd --system --no-create-home --shell /usr/sbin/nologin sip-notify
install -d -o root -g sip-notify -m 0750 /var/lib/sip-notify
install -d -o root -g sip-notify -m 2770 /var/lib/sip-notify/outbox
install -o root -g root -m 0755 sip-notify.py /usr/local/sbin/sip-notify.py
install -o root -g root -m 0644 sip-notify.path sip-notify.service /etc/systemd/system/
install -o root -g root -m 0755 ../wol/sip-wol-halo.py /usr/local/sbin/sip-wol-halo.py
install -o root -g root -m 0644 ../wol/sip-wol-halo.service /etc/systemd/system/
systemctl daemon-reload
systemctl enable --now sip-notify.path
systemctl is-active sip-notify.path sip-wol-halo.path
echo "copia en $B"
