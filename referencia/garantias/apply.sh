#!/bin/sh
# Garantías de PARA (05-11). PREPARADO, SIN DESPLEGAR: lee todo PARA; lo decide el usuario.
# Root, en Neo, desde sip-config/garantias, DESPUÉS de sip-config/indice/apply.sh (usuario sip-indice).
# Rollback: systemctl disable --now sip-garantias.timer; rm /etc/systemd/system/sip-garantias.*;
#   rm /usr/local/sbin/sip-garantias.py; rm -rf /var/lib/sip-garantias.
set -eu
cd "$(dirname "$0")"
id sip-indice >/dev/null
getent group sip-notify >/dev/null && usermod -aG sip-notify sip-indice
install -d -m 2750 -o sip-indice -g usuario /var/lib/sip-garantias /var/lib/sip-garantias/informes
install -o root -g root -m 755 sip-garantias.py /usr/local/sbin/sip-garantias.py
install -o root -g root -m 644 sip-garantias.service sip-garantias.timer /etc/systemd/system/
systemctl daemon-reload
systemctl enable --now sip-garantias.timer
systemctl list-timers sip-garantias.timer --no-legend | cut -c1-60
