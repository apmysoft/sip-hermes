#!/bin/sh
# Retención del journal de Neo (v2.4 M.12), como root. Fichero nuevo: nada que respaldar.
# Rollback: rm /etc/systemd/journald.conf.d/sip-retencion.conf; systemctl restart systemd-journald.
set -eu
cd "$(dirname "$0")"
install -d -o root -g root -m 0755 /etc/systemd/journald.conf.d
install -o root -g root -m 0644 sip-retencion.conf /etc/systemd/journald.conf.d/sip-retencion.conf
systemctl restart systemd-journald
systemctl is-active systemd-journald
systemd-analyze cat-config systemd/journald.conf | grep -E '^MaxRetentionSec'
journalctl --list-boots --no-pager | sed -n 2p
logger -t sip-retencion "prueba de escritura tras la retención"
journalctl -t sip-retencion -n 1 --no-pager | tail -1
echo "RESULTADO: OK"
