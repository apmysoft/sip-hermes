#!/bin/sh
# Instala la auditoría trimestral (root, en Neo) y la ejecuta una vez bajo systemd (avisa por Telegram).
# Ficheros nuevos: nada que respaldar. Rollback: systemctl disable --now sip-auditoria.timer;
# rm /usr/local/sbin/sip-auditoria.py /etc/systemd/system/sip-auditoria.{service,timer}; daemon-reload.
set -eu
cd "$(dirname "$0")"
install -o root -g root -m 0755 sip-auditoria.py /usr/local/sbin/sip-auditoria.py
install -o root -g root -m 0644 sip-auditoria.service sip-auditoria.timer /etc/systemd/system/
systemctl daemon-reload
systemctl start sip-auditoria.service
systemctl show -p Result --value sip-auditoria.service
ls -l /var/lib/sip-auditoria/
systemctl enable --now sip-auditoria.timer
systemctl list-timers sip-auditoria.timer --no-pager | sed -n 2p
echo "RESULTADO: OK"
