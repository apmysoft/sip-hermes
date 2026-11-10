#!/bin/sh
# Instala la copia diaria en Neo. Se ejecuta como root con los ficheros junto al script.
# Rollback: systemctl disable --now sip-litellm-backup.timer; borrar las 3 unidades instaladas.
set -eu
cd "$(dirname "$0")"
install -o root -g root -m 0700 sip-litellm-backup.sh /usr/local/sbin/sip-litellm-backup.sh
install -o root -g root -m 0644 sip-litellm-backup.service sip-litellm-backup.timer /etc/systemd/system/
systemctl daemon-reload
systemctl enable --now sip-litellm-backup.timer
systemctl start sip-litellm-backup.service
systemctl is-failed sip-litellm-backup.service || true
ls -la /var/backups/sip-litellm
systemctl list-timers sip-litellm-backup.timer --no-pager | head -2
