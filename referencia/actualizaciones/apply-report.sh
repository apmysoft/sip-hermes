#!/bin/sh
# Instala el informe semanal de actualizaciones (root, en Neo). Requiere sip-config/notify.
# Rollback: systemctl disable --now sip-updates-report.timer; borrar las unidades y el script.
set -eu
cd "$(dirname "$0")"
install -o root -g root -m 0755 sip-updates-report.py /usr/local/sbin/sip-updates-report.py
install -o root -g root -m 0644 sip-updates-report.service sip-updates-report.timer /etc/systemd/system/
systemctl daemon-reload
systemctl enable --now sip-updates-report.timer
systemctl list-timers sip-updates-report.timer --no-pager | head -2
