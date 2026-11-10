#!/bin/sh
# Instala la evaluación semanal de modelos (root, en Neo). Requiere LiteLLM, la API de RESEARCH
# (research/apply-api.sh) y sip-notify.
# Rollback: systemctl disable --now sip-model-eval.timer; borrar las unidades y el script
#   (los informes de /var/lib/sip-model-eval pueden quedarse).
set -eu
cd "$(dirname "$0")"
install -o root -g root -m 0755 sip-model-eval.py /usr/local/sbin/sip-model-eval.py
install -o root -g root -m 0644 sip-model-eval.service sip-model-eval.timer /etc/systemd/system/
systemctl daemon-reload
systemctl enable --now sip-model-eval.timer
systemctl list-timers sip-model-eval.timer --no-pager | head -2
