#!/bin/sh
# Instala el resumen matutino (root, en Neo). Requiere sip-config/notify y el tiny (llm-neo).
# Rollback: systemctl disable --now sip-morning.timer; borrar las unidades y el script.
set -eu
cd "$(dirname "$0")"
install -o root -g root -m 0755 sip-morning.py /usr/local/sbin/sip-morning.py
install -o root -g root -m 0644 sip-morning.service sip-morning.timer /etc/systemd/system/
systemctl daemon-reload
systemctl enable --now sip-morning.timer
systemctl list-timers sip-morning.timer --no-pager | head -2
