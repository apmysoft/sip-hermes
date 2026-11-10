#!/bin/sh
# Instala sip-panico (root, en Neo) sin activarlo. Fichero nuevo: nada que respaldar.
# Rollback: rm /usr/local/sbin/sip-panico. La prueba real (stop → comprobar → start) va aparte, en una
# ventana elegida por el usuario: para las zonas.
set -eu
cd "$(dirname "$0")"
install -o root -g root -m 0755 sip-panico /usr/local/sbin/sip-panico
/usr/local/sbin/sip-panico stop --simular | grep -c '^\[simular\]'
test ! -e /var/lib/sip-panico/estado
/usr/local/sbin/sip-panico estado | head -1
echo "RESULTADO: OK"
