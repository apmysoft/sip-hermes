#!/bin/sh
# Instala el traspaso nocturno (root, en Neo). Requiere CODING (Fase 7), sip-notify y el servicio WOL.
# Nada que respaldar: servicio nuevo. Rollback: systemctl disable --now sip-traspaso.timer; borrar las
# unidades y /usr/local/sbin/sip-traspaso.py. /var/lib/sip-traspaso se conserva (registro e informes).
set -eu
cd "$(dirname "$0")"
install -o root -g root -m 0755 sip-traspaso.py /usr/local/sbin/sip-traspaso.py
install -o root -g root -m 0644 sip-traspaso.service sip-traspaso.timer /etc/systemd/system/
install -d -o root -g root -m 0700 /var/lib/sip-traspaso /var/lib/sip-traspaso/cola /var/lib/sip-traspaso/hecho
systemctl daemon-reload
systemctl enable --now sip-traspaso.timer
systemctl list-timers sip-traspaso.timer --no-pager | head -2
# Con la cola vacía, la condición debe saltar el servicio sin error.
systemctl start sip-traspaso.service
systemctl show sip-traspaso.service -p Result -p ExecMainStatus --value | tr '\n' ' '; echo
journalctl -u sip-traspaso.service -n 3 --no-pager | tail -2
echo "RESULTADO: OK"
