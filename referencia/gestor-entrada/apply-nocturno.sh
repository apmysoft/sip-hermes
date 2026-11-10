#!/bin/sh
# Instala el barrido nocturno del gestor (root, en Neo). Requiere el gestor ya desplegado (Fase 4).
# Rollback: systemctl disable --now sip-gestor-nocturno.timer; borrar las unidades y el script de condición.
set -eu
cd "$(dirname "$0")"
install -o root -g sip-gestor -m 0755 gestor-nocturno-check.py /usr/local/bin/gestor-nocturno-check.py
install -o root -g root -m 0644 sip-gestor-nocturno.service sip-gestor-nocturno.timer /etc/systemd/system/
systemctl daemon-reload
systemctl enable --now sip-gestor-nocturno.timer
systemctl list-timers sip-gestor-nocturno.timer --no-pager | head -2
