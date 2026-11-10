#!/bin/sh
# Instala sip-alertas (root, en Neo). Ficheros nuevos: nada que respaldar.
# Rollback: systemctl disable --now sip-alertas.timer; rm /usr/local/sbin/sip-alertas.py
# /etc/systemd/system/sip-alertas.{service,timer}; systemctl daemon-reload; rm -r /var/lib/sip-alertas.
set -eu
cd "$(dirname "$0")"
install -o root -g root -m 0755 sip-alertas.py /usr/local/sbin/sip-alertas.py
install -o root -g root -m 0644 sip-alertas.service sip-alertas.timer /etc/systemd/system/
systemctl daemon-reload
echo "-- simulación"
python3 -I /usr/local/sbin/sip-alertas.py --dry-run
echo "-- ejecución real (primer aviso con lo que ya esté alto)"
systemctl start sip-alertas.service
journalctl -u sip-alertas.service -n 12 --no-pager -o cat | grep -v "^Starting\|^Finished\|Deactivated\|Consumed"
test -s /var/lib/sip-alertas/estado.json
systemctl enable --now sip-alertas.timer
systemctl is-active sip-alertas.timer
echo "RESULTADO: OK"
