#!/bin/sh
# Índice de texto completo de PARA (05-11; libros fuera, borrados cada noche y VACUUM el 09-11). Aprobado por el usuario
# el 09-11. Lee todo PARA en solo lectura (grupo hermes-ro y other::r); sin red; base en /var/lib/sip-indice
# (grupo usuario, para que PERSONAL la lea en solo lectura en /indice). Root, en Neo, desde este directorio.
# Rollback: systemctl disable --now sip-indice.timer; rm /etc/systemd/system/sip-indice.*;
#   rm /usr/local/sbin/sip-indice.py; rm -rf /var/lib/sip-indice; userdel sip-indice.
set -eu
cd "$(dirname "$0")"
id sip-indice >/dev/null 2>&1 || useradd --system --no-create-home --home-dir /nonexistent --shell /usr/sbin/nologin sip-indice
usermod -aG hermes-ro sip-indice
install -d -m 2750 -o sip-indice -g usuario /var/lib/sip-indice
install -o root -g root -m 755 sip-indice.py /usr/local/sbin/sip-indice.py
install -o root -g root -m 644 sip-indice.service sip-indice.timer /etc/systemd/system/
systemctl daemon-reload
systemctl enable --now sip-indice.timer
systemctl list-timers sip-indice.timer --no-legend | cut -c1-60
echo "RESULTADO: OK (la primera pasada empieza a las 00:30; o: systemctl start --no-block sip-indice)"
