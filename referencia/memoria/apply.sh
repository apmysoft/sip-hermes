#!/bin/sh
# Instala el recordatorio semanal de curación de memoria (root, en Neo). Requiere sip-config/notify.
# Rollback: systemctl disable --now sip-memory-review.timer; borrar las unidades y el script.
set -eu
cd "$(dirname "$0")"
install -o root -g root -m 0755 sip-memory-review.py /usr/local/sbin/sip-memory-review.py
install -o root -g root -m 0644 sip-memory-review.service sip-memory-review.timer /etc/systemd/system/
systemctl daemon-reload
systemctl enable --now sip-memory-review.timer
systemctl list-timers sip-memory-review.timer --no-pager | head -2
