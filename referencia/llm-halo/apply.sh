#!/bin/sh
# Cambio de servidor de modelos en HALO: Ollama -> llama-swap (05-11). Root, en HALO, desde el repo.
# Requisitos: install-halo.sh y modelos.sh ya ejecutados (binarios y GGUF con sha256 verificado).
# Ollama NO se desinstala ni se borran sus modelos (/usr/share/ollama): solo se para y deshabilita.
# Rollback: sh $B/rollback.sh  (llama-swap fuera, Ollama de vuelta en el mismo puerto)
# 05-11 (noche): YA NO SIRVE. Ollama está desinstalado tras verificar el arranque de HALO; volver exigiría
# reinstalarlo y recrear los modelos desde los GGUF de /var/lib/sip-llm/models.
set -eu
cd "$(dirname "$0")"
L=/var/lib/sip-llm
B=/root/sip-agent-backups/$(date +%F)/llm-halo
[ ! -e "$B" ] || { echo "ERROR: ya existe $B" >&2; exit 1; }
for f in qwen3.8-27b-Q4_K_M.gguf gpt-oss-20b-MXFP4.gguf Qwen3VL-30B-A3B-Instruct-Q4_K_M.gguf; do
  [ -f "$L/models/$f.sha256ok" ] || { echo "ERROR: falta $f (modelos.sh)" >&2; exit 1; }
done
install -d -m 700 "$B"
cp -a /etc/systemd/system/ollama.service /etc/systemd/system/ollama.service.d "$B/"
systemctl is-enabled ollama > "$B/ollama.is-enabled" 2>&1 || true
OLLAMA_HOST=${HALO_TAILNET_IP} ollama list > "$B/ollama-list.txt" 2>&1 || true
cat > "$B/rollback.sh" <<EOF
#!/bin/sh
# Vuelve a Ollama (modelos intactos en /usr/share/ollama).
systemctl disable --now llama-swap
systemctl enable --now ollama
sleep 3; curl -s -o /dev/null -w "Ollama /api/version: %{http_code}\n" http://${HALO_TAILNET_IP}:11434/api/version
EOF
echo "copia en $B"

install -o root -g sip-llm -m 640 llama-swap.yaml $L/llama-swap.yaml
install -o root -g root -m 644 llama-swap.service /etc/systemd/system/llama-swap.service
systemd-analyze verify /etc/systemd/system/llama-swap.service 2>&1 | grep -v "^$" || true
pkill -u sip-llm -f "llama-swap --config" 2>/dev/null || true   # instancia de prueba en 127.0.0.1:18081
systemctl daemon-reload
systemctl disable --now ollama
systemctl enable --now llama-swap
ok=0
for i in $(seq 60); do curl -sf -o /dev/null http://${HALO_TAILNET_IP}:11434/v1/models && { ok=1; break; }; sleep 2; done
[ $ok = 1 ] || { echo "RESULTADO: FALLO llama-swap no responde (rollback: sh $B/rollback.sh)" >&2; journalctl -u llama-swap -n 20 --no-pager; exit 1; }

echo "== verificación"
ss -ltnp | grep ":11434 " | sed 's/users:.*//'
echo "modelos: $(curl -s http://${HALO_TAILNET_IP}:11434/v1/models | python3 -c 'import json,sys; print(len(json.load(sys.stdin)["data"]))')"
t=$(date +%s)
curl -s http://${HALO_TAILNET_IP}:11434/v1/chat/completions -H 'Content-Type: application/json' \
  -d '{"model":"qwen3.8:27b-64k","messages":[{"role":"user","content":"Responde solo OK"}],"max_tokens":400}' \
  | python3 -c 'import json,sys; d=json.load(sys.stdin); print("turno qwen3.8:27b-64k:", d["choices"][0]["message"]["content"].strip()[:20], "| t/s", round(d["timings"]["predicted_per_second"]))'
echo "  ($(( $(date +%s) - t )) s con la carga)"
systemctl is-active llama-swap; systemctl is-enabled llama-swap; echo "ollama: $(systemctl is-active ollama) / $(systemctl is-enabled ollama)"
echo "RESULTADO: OK (rollback: sh $B/rollback.sh)"
