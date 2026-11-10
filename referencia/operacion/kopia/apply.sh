#!/bin/sh
# Instala la copia nocturna del estado SIP para Kopia (root, en Neo). No toca Kopia ni su repositorio:
# deja la copia cifrada en una carpeta que KopiaUI ya copia (fuente ${PARA_ROOT}, 22:00).
# Ficheros nuevos: nada que respaldar. Rollback: systemctl disable --now sip-kopia-estado.timer;
# rm /usr/local/sbin/sip-kopia-estado.py /etc/systemd/system/sip-kopia-estado.{service,timer};
# systemctl daemon-reload. La carpeta _copias-sip-estado se deja (la borra el usuario si quiere).
set -eu
cd "$(dirname "$0")"
D="${PARA_ROOT}/01_proyectos/Implementación SIP + Hermes agent"
C="$D/_copias-sip-estado"
test -d "$D"
# Carpeta solo de usuario: sin las ACL heredadas de PARA (filegate rwx, hermes-ro r-x)
install -d -o usuario -g usuario -m 0700 "$C"
setfacl -b "$C"
chmod 0700 "$C"
install -o root -g root -m 0755 sip-kopia-estado.py /usr/local/sbin/sip-kopia-estado.py
install -o root -g root -m 0644 sip-kopia-estado.service sip-kopia-estado.timer /etc/systemd/system/
systemctl daemon-reload
systemctl start sip-kopia-estado.service
journalctl -u sip-kopia-estado.service -n 10 --no-pager -o cat | grep '^OK:' | tail -1
stat -c '%U:%G %a' "$C"
getfacl -cp "$C" | grep -qE 'filegate|hermes-ro' && { echo "ACL heredadas presentes"; exit 1; }
for u in filegate sip-gestor; do
    id "$u" >/dev/null 2>&1 || continue
    sudo -u "$u" test -r "$C" && { echo "$u puede leer la carpeta"; exit 1; }
done
systemctl enable --now sip-kopia-estado.timer
systemctl is-active sip-kopia-estado.timer
echo "RESULTADO: OK"
