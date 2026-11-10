#!/bin/sh
# Fase 6: instala el firewall candidato y crea la red research. Ejecutar en Neo como root,
# con nftables-sip.candidate.nft junto al script.
#
# Reversión automática: si las comprobaciones fallan o el script se corta, un temporizador
# restaura el fichero anterior a los 5 minutos. Si todo pasa, cancela la reversión.
# Rollback manual: copiar la copia de $B sobre /etc/nftables-sip.nft, reiniciar
# nft-sip-zones y borrar la red con `docker network rm research`.
set -eu
cd "$(dirname "$0")"

B=/root/sip-agent-backups/$(date +%F)/fase6c
UNIT=sip-nft-rollback

nft -c -f nftables-sip.candidate.nft
install -d -m 700 "$B"
cp -p /etc/nftables-sip.nft "$B/nftables-sip.nft-pre"
nft list table inet sip-zones > "$B/sip-zones-vivo-pre.txt"

systemd-run --quiet --on-active=300 --unit="$UNIT" /bin/sh -c \
  "cp -p $B/nftables-sip.nft-pre /etc/nftables-sip.nft; systemctl restart nft-sip-zones"

install -o root -g root -m 644 nftables-sip.candidate.nft /etc/nftables-sip.nft
systemctl restart nft-sip-zones

docker network inspect research >/dev/null 2>&1 || \
  docker network create --driver bridge --subnet 10.20.0.0/24 --gateway 10.20.0.1 research >/dev/null

# proxy, HALO y runner deben abrir; LAN, WAN y la IP tailnet del host deben seguir cerradas
if docker exec -i hermes-webui /app/venv/bin/python - <<'PY'
import socket, sys
checks = (('sip-litellm', 4000, True), ('${HALO_TAILNET_IP}', 11434, True), ('${HALO_TAILNET_IP}', 22, True),
          ('172.30.0.2', 2222, True), ('${LAN_GATEWAY}', 80, False), ('1.1.1.1', 443, False),
          ('${NEO_TAILNET_IP}', 8787, False))
ok = True
for host, port, want in checks:
    s = socket.socket()
    s.settimeout(4)
    try:
        s.connect((host, port))
        got = True
    except OSError:
        got = False
    s.close()
    print('PASS' if got == want else 'FAIL', host, port, 'abierto' if got else 'cerrado')
    ok = ok and got == want
sys.exit(0 if ok else 1)
PY
then
  systemctl stop "$UNIT.timer"
  echo "RESULTADO: OK. Reversion cancelada; firewall nuevo activo."
else
  echo "RESULTADO: FALLO. Se revertira solo en 5 minutos; no hagas nada." >&2
  exit 1
fi
