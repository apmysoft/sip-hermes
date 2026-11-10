#!/bin/sh
# OCR del índice delegado en HALO (09-11, decisión del usuario: ventana 02:00-06:00). Root, en Neo, desde este
# directorio, DESPUÉS de apply.sh. Instala: sip-indice.py (--sin-ocr) y su unidad, sip-indice-ocr (servicio y timer),
# y un WOL propio (sip-wol-indice.path/.service: mismo emisor y cupo que sip-wol-halo, carpeta propia).
# Permisos: requests/ la escribe sip-indice (grupo) y la vacía sip-wol (dueño); results/ la escribe sip-wol y la lee
# sip-indice. Rollback: sh $B/rollback.sh
set -eu
cd "$(dirname "$0")"
B=/root/sip-agent-backups/$(date +%F)/indice-ocr
[ ! -e "$B" ] || { echo "ERROR: ya existe $B" >&2; exit 1; }
id sip-indice >/dev/null && id sip-wol >/dev/null
test -x /usr/local/sbin/sip-wol-halo.py
install -d -m 700 "$B"
cp -p /usr/local/sbin/sip-indice.py /etc/systemd/system/sip-indice.service /etc/systemd/system/sip-indice.timer "$B/"
cat > "$B/rollback.sh" <<R
#!/bin/sh
systemctl disable --now sip-indice-ocr.timer sip-wol-indice.path
rm -f /etc/systemd/system/sip-indice-ocr.* /etc/systemd/system/sip-wol-indice.* /usr/local/sbin/sip-indice-ocr.py /etc/tmpfiles.d/sip-indice-wol.conf
rm -rf /var/lib/sip-indice-wol
cp -p $B/sip-indice.py /usr/local/sbin/; cp -p $B/sip-indice.service $B/sip-indice.timer /etc/systemd/system/
systemctl daemon-reload
R
install -d -m 2750 -o sip-wol -g sip-indice /var/lib/sip-indice-wol
install -d -m 2770 -o sip-wol -g sip-indice /var/lib/sip-indice-wol/requests
install -d -m 2750 -o sip-wol -g sip-indice /var/lib/sip-indice-wol/results
install -o root -g root -m 644 sip-indice-wol.tmpfiles /etc/tmpfiles.d/sip-indice-wol.conf
install -o root -g root -m 755 sip-indice.py sip-indice-ocr.py /usr/local/sbin/
install -o root -g root -m 644 sip-indice.service sip-indice.timer sip-indice-ocr.service sip-indice-ocr.timer \
  sip-wol-indice.path sip-wol-indice.service /etc/systemd/system/
systemctl daemon-reload
systemctl enable --now sip-wol-indice.path sip-indice-ocr.timer
systemctl list-timers sip-indice.timer sip-indice-ocr.timer --no-legend | cut -c1-70
echo "RESULTADO: OK (rollback: sh $B/rollback.sh)"
