#!/bin/sh
# Zona PERSONAL por Telegram (04-11): instala el firewall candidato (solo añade gw-personal a dos reglas
# de descarte) y crea la red gw-personal (10.25.0.0/24, internal). Root, en Neo, desde este directorio.
# Reversión automática: si las comprobaciones fallan o el script se corta, a los 5 minutos se restaura
# el fichero anterior. Rollback manual: copiar $B/nftables-sip.nft-pre sobre /etc/nftables-sip.nft,
# systemctl restart nft-sip-zones y docker network rm gw-personal.
set -eu
cd "$(dirname "$0")"
B=/root/sip-agent-backups/$(date +%F)/personal-api-firewall
UNIT=sip-nft-rollback-personal
IMG=hermes-research:0.26.0-a2026.9.14  # solo para la sonda: trae python

nft -c -f nftables-sip.candidate.nft
install -d -m 700 "$B"
cp -p /etc/nftables-sip.nft "$B/nftables-sip.nft-pre"
nft list table inet sip-zones > "$B/sip-zones-vivo-pre.txt"
systemd-run --quiet --on-active=300 --unit="$UNIT" /bin/sh -c \
  "cp -p $B/nftables-sip.nft-pre /etc/nftables-sip.nft; systemctl restart nft-sip-zones"

install -o root -g root -m 644 nftables-sip.candidate.nft /etc/nftables-sip.nft
systemctl restart nft-sip-zones
docker network inspect gw-personal >/dev/null 2>&1 || \
  docker network create --driver bridge --internal --subnet 10.25.0.0/24 --gateway 10.25.0.1 gw-personal >/dev/null

sonda() {  # $1 red, $2 comprobaciones (host, puerto, ¿abierto?); contenedor desechable sin privilegios
  docker run --rm --network "$1" --read-only --cap-drop ALL --user 65534:65534 --entrypoint python3 "$IMG" -c "
import socket, sys
ok = True
for host, port, want in $2:
    try:
        with socket.create_connection((host, port), timeout=4): got = True
    except OSError:
        got = False
    print('PASS' if got == want else 'FAIL', '$1', host, port, 'abierto' if got else 'cerrado')
    ok = ok and got == want
sys.exit(0 if ok else 1)"
}

# Nuevo: gw-personal no sale a ningún sitio. Existente: sin cambios.
if sonda gw-personal "(('10.25.0.1',22,False),('1.1.1.1',443,False),('${HALO_TAILNET_IP}',11434,False),('149.154.166.110',443,False),('${LAN_GATEWAY}',80,False))" \
  && sonda gateway "(('149.154.166.110',443,True),('1.1.1.1',443,False),('${LAN_GATEWAY}',80,False),('${HALO_TAILNET_IP}',11434,False))" \
  && sonda sip "(('${HALO_TAILNET_IP}',11434,True),('1.1.1.1',443,False),('${LAN_GATEWAY}',80,False),('10.23.0.10',4000,False))" \
  && sonda coding "(('${HALO_TAILNET_IP}',22,True),('1.1.1.1',443,False),('${LAN_GATEWAY}',80,False))" \
  && sonda gw-coding "(('10.24.0.1',22,False),('1.1.1.1',443,False))"
then
  systemctl stop "$UNIT.timer"
  echo "RESULTADO: OK. Reversión cancelada; firewall nuevo activo."
else
  echo "RESULTADO: FALLO. Se revertirá solo en 5 minutos; no hagas nada." >&2
  exit 1
fi
