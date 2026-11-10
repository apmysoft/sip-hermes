#!/bin/sh
# Fase 7: instala el firewall candidato y crea las redes gateway y gw-research. Ejecutar en Neo
# como root, con nftables-sip.candidate.nft junto al script.
#
# Reversión automática: si las comprobaciones fallan o el script se corta, un temporizador
# restaura el fichero anterior a los 5 minutos. Si todo pasa, cancela la reversión.
# Rollback manual: copiar la copia de $B sobre /etc/nftables-sip.nft, reiniciar
# nft-sip-zones y borrar las redes con `docker network rm gateway gw-research`.
set -eu
cd "$(dirname "$0")"

B=/root/sip-agent-backups/$(date +%F)/fase7
UNIT=sip-nft-rollback
IMG=hermes-research:0.26.0-a2026.9.14  # solo para la sonda: trae python

nft -c -f nftables-sip.candidate.nft
install -d -m 700 "$B"
cp -p /etc/nftables-sip.nft "$B/nftables-sip.nft-pre"
nft list table inet sip-zones > "$B/sip-zones-vivo-pre.txt"

systemd-run --quiet --on-active=300 --unit="$UNIT" /bin/sh -c \
  "cp -p $B/nftables-sip.nft-pre /etc/nftables-sip.nft; systemctl restart nft-sip-zones"

install -o root -g root -m 644 nftables-sip.candidate.nft /etc/nftables-sip.nft
systemctl restart nft-sip-zones

docker network inspect gateway >/dev/null 2>&1 || \
  docker network create --driver bridge --subnet 10.21.0.0/24 --gateway 10.21.0.1 gateway >/dev/null
docker network inspect gw-research >/dev/null 2>&1 || \
  docker network create --driver bridge --internal --subnet 10.22.0.0/24 --gateway 10.22.0.1 gw-research >/dev/null

PROBE='
import socket, sys
ok = True
for host, port, want in CHECKS:
    try:
        if port == 0:
            socket.getaddrinfo(host, 443); got = True
        else:
            with socket.create_connection((host, port), timeout=4): got = True
    except OSError:
        got = False
    print("PASS" if got == want else "FAIL", NET, host, port or "dns", "abierto" if got else "cerrado")
    ok = ok and got == want
sys.exit(0 if ok else 1)
'
sonda() {  # $1 red, $2 lista de comprobaciones; contenedor desechable sin privilegios
  docker run --rm --network "$1" --read-only --cap-drop ALL --user 65534:65534 \
    --entrypoint python3 "$IMG" -c "NET='$1'; CHECKS=$2
$PROBE"
}

# Lo existente no cambia (mismas comprobaciones que en Fase 6) y lo nuevo solo abre Telegram.
if docker exec -i hermes-webui /app/venv/bin/python - <<'PY' \
  && sonda gateway "(('api.telegram.org',0,True),('149.154.166.110',443,True),('1.1.1.1',443,False),('${LAN_GATEWAY}',80,False),('${HALO_TAILNET_IP}',11434,False),('10.21.0.1',22,False),('${NEO_TAILNET_IP}',8787,False))" \
  && sonda gw-research "(('10.22.0.1',22,False),('1.1.1.1',443,False),('149.154.166.110',443,False))"
import socket, sys
checks = (('sip-litellm', 4000, True), ('${HALO_TAILNET_IP}', 11434, True), ('${HALO_TAILNET_IP}', 22, True),
          ('172.30.0.2', 2222, True), ('${LAN_GATEWAY}', 80, False), ('1.1.1.1', 443, False),
          ('${NEO_TAILNET_IP}', 8787, False))
ok = True
for host, port, want in checks:
    try:
        with socket.create_connection((host, port), timeout=4): got = True
    except OSError:
        got = False
    print('PASS' if got == want else 'FAIL', 'sip', host, port, 'abierto' if got else 'cerrado')
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
