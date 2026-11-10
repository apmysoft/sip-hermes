#!/bin/sh
# Partes B y C del respaldo de PERSONAL con el tiny de Neo (v2.4 §H.3), aprobadas por el usuario el 06-11.
#   B: sip-tiny-personal.socket/.service (172.29.0.1:11435 -> 127.0.0.1:11434, solo .200 y .201).
#   C: excepción en sip-zones (input): WebUI y API de PERSONAL -> 172.29.0.1:11435.
# La parte A (tiny a 32K) está en ../llm-neo/llama-swap.yaml; la D (fallback_providers de Hermes) va aparte.
# Root, en Neo, desde este directorio. Rollback: sh $B/rollback.sh
set -eu
cd "$(dirname "$0")"
B=/root/sip-agent-backups/$(date +%F)/tiny-personal/bc
[ ! -e "$B" ] || { echo "ERROR: ya existe $B" >&2; exit 1; }
systemctl is-active -q llama-swap || { echo "ERROR: llama-swap no está activo" >&2; exit 1; }
nft -c -f nftables-sip.candidate.nft
# La candidata se hizo sobre las reglas vigentes del 06-11: si han cambiado, no se aplica a ciegas.
if diff /etc/nftables-sip.nft nftables-sip.candidate.nft | grep -E '^[<>]' | grep -vE '11435|respaldo de PERSONAL|sip-tiny-personal'; then
  echo "ERROR: /etc/nftables-sip.nft ha cambiado desde la candidata; rehazla" >&2; exit 1
fi
install -d -m 700 "$B"
cp -p /etc/nftables-sip.nft "$B/nftables-sip.nft-pre"
cat > "$B/rollback.sh" <<X
#!/bin/sh
systemctl disable --now sip-tiny-personal.socket; systemctl stop sip-tiny-personal.service
rm -f /etc/systemd/system/sip-tiny-personal.socket /etc/systemd/system/sip-tiny-personal.service
systemctl daemon-reload
cp -p $B/nftables-sip.nft-pre /etc/nftables-sip.nft; systemctl restart nft-sip-zones
X
install -o root -g root -m 644 sip-tiny-personal.socket sip-tiny-personal.service /etc/systemd/system/
systemctl daemon-reload
systemctl enable --now sip-tiny-personal.socket
install -o root -g root -m 644 nftables-sip.candidate.nft /etc/nftables-sip.nft
systemctl restart nft-sip-zones
echo "== verificación"
ss -ltn | grep -q '172.29.0.1:11435' && echo "  socket escuchando en 172.29.0.1:11435"
for c in hermes-personal-api hermes-webui; do
  docker exec $c python3 -c "
import json,urllib.request
d=json.load(urllib.request.urlopen('http://172.29.0.1:11435/v1/models',timeout=20))
print('  $c -> tiny:', [m['id'] for m in d['data']])"
done
docker exec hermes-research python3 -c "
import urllib.request
try: urllib.request.urlopen('http://172.29.0.1:11435/v1/models',timeout=5); print('  MAL: RESEARCH llega'); raise SystemExit(1)
except OSError as e: print('  RESEARCH no llega:', type(e).__name__)"
nft list ruleset | grep -E 'dport 11435 counter' | sed 's/^ */  regla: /'
echo "RESULTADO: OK (rollback: sh $B/rollback.sh)"
