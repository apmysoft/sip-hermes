#!/bin/sh
# Instala `lotes`, `decidir` y `descartar` del gestor y el filtro de descartados del barrido nocturno y
# del resumen (root, en Neo, desde ~/sip-inventario). Solo cambia estado: no decide ni aplica ningún lote.
# Rollback: install -o root -g sip-gestor -m 0755 $B/gestor-entrada.py $B/gestor-nocturno-check.py /usr/local/bin/
#           install -o root -g root -m 0755 $B/sip-morning.py /usr/local/sbin/
#           (la tabla `discarded` puede quedarse: el código anterior no la lee)
set -eu
cd "$(dirname "$0")"
B=/root/sip-agent-backups/2026-11-03/gestor-decidir
install -d -m 0700 "$B"
[ -e "$B/gestor-entrada.py" ] || cp -p /usr/local/bin/gestor-entrada.py /usr/local/bin/gestor-nocturno-check.py \
  /usr/local/sbin/sip-morning.py "$B/"
[ -e "$B/state.db" ] || sqlite3 /var/lib/sip-gestor-entrada/state.db ".backup '$B/state.db'"

install -o root -g sip-gestor -m 0755 gestor-entrada.py gestor-nocturno-check.py /usr/local/bin/
install -o root -g root -m 0755 ../resumen/sip-morning.py /usr/local/sbin/

# Crea la tabla `discarded` antes de que la lean el barrido y el resumen.
sudo -u sip-gestor /usr/local/bin/gestor-entrada.py status >/dev/null
sudo -u sip-gestor /usr/local/bin/gestor-entrada.py lotes
sudo -u sip-gestor /usr/local/bin/gestor-nocturno-check.py || true
python3 -I /usr/local/sbin/sip-morning.py --dry-run | grep -i lote || true
echo "RESULTADO: OK. Copia previa en $B"
