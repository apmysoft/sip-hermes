#!/bin/sh
# sip-medios (06-11): servicio HTTP de herramientas en HALO detrás de llama-swap. Root, en HALO, desde este dir.
# Requisitos: install-halo.sh (/opt/sip-medios) y gpu-halo ya desplegado. Rollback: sh $B/rollback.sh
set -eu
cd "$(dirname "$0")"
B=/root/sip-agent-backups/$(date +%F)/medios-api
[ ! -e "$B" ] || { echo "ERROR: ya existe $B" >&2; exit 1; }
install -d -m 700 "$B"
cp -p /var/lib/sip-llm/llama-swap.yaml /etc/polkit-1/rules.d/50-sip-llm-gpu.rules /usr/local/lib/sip-gpu/sip-gpu-unidad \
      /etc/systemd/system/llama-swap.service.d/50-sip-gpu.conf "$B/"
cat > "$B/rollback.sh" <<R
#!/bin/sh
systemctl stop sip-medios.service 2>/dev/null
install -o root -g sip-llm -m 640 $B/llama-swap.yaml /var/lib/sip-llm/llama-swap.yaml
install -m 644 $B/50-sip-llm-gpu.rules /etc/polkit-1/rules.d/50-sip-llm-gpu.rules
install -m 755 $B/sip-gpu-unidad /usr/local/lib/sip-gpu/sip-gpu-unidad
install -m 644 $B/50-sip-gpu.conf /etc/systemd/system/llama-swap.service.d/50-sip-gpu.conf
rm -f /etc/systemd/system/sip-medios.service; rm -rf /usr/local/lib/sip-medios; userdel sip-medios
systemctl daemon-reload; systemctl restart llama-swap
R
echo "copia en $B"
id sip-medios >/dev/null 2>&1 || useradd --system --home-dir /nonexistent --no-create-home --shell /usr/sbin/nologin sip-medios
install -d -o root -g root -m 755 /usr/local/lib/sip-medios
install -o root -g root -m 755 sip-medios-api.py /usr/local/lib/sip-medios/sip-medios-api.py
install -o root -g root -m 644 sip-medios.service /etc/systemd/system/sip-medios.service
install -o root -g root -m 644 ../gpu-halo/50-sip-llm-gpu.rules /etc/polkit-1/rules.d/50-sip-llm-gpu.rules
install -o root -g root -m 755 ../gpu-halo/sip-gpu-unidad /usr/local/lib/sip-gpu/sip-gpu-unidad
install -o root -g root -m 644 ../gpu-halo/llama-swap-gpu.conf /etc/systemd/system/llama-swap.service.d/50-sip-gpu.conf
install -o root -g sip-llm -m 640 ../llm-halo/llama-swap.yaml /var/lib/sip-llm/llama-swap.yaml
systemd-analyze verify /etc/systemd/system/sip-medios.service 2>&1 | grep -v "^$" || true
systemctl daemon-reload
systemctl restart llama-swap
for i in $(seq 60); do curl -sf -o /dev/null http://${HALO_TAILNET_IP}:11434/v1/models && break; sleep 2; done
echo "== verificación"
como_llm() { systemd-run --quiet --uid=sip-llm --gid=sip-llm --pipe --wait --collect "$@" >/dev/null 2>&1; }
como_llm /bin/systemctl --no-ask-password start ssh.service && { echo "  MAL: polkit permite otras unidades"; exit 1; } || echo "  polkit: otras unidades denegadas"
curl -s -o /dev/null http://${HALO_TAILNET_IP}:11434/v1/chat/completions -H 'Content-Type: application/json' \
  -d '{"model":"qwen3.8:27b","messages":[{"role":"user","content":"di OK"}],"max_tokens":300}'
echo "  antes: $(curl -s http://${HALO_TAILNET_IP}:11434/running | python3 -c 'import json,sys; print(sorted(m["model"] for m in json.load(sys.stdin)["running"]))')"
runuser -u usuario -- sh ./probar-api.sh | sed 's/^/  /'
echo "  después: $(curl -s http://${HALO_TAILNET_IP}:11434/running | python3 -c 'import json,sys; print(sorted(m["model"] for m in json.load(sys.stdin)["running"]))') (el modelo de texto debe seguir)"
echo "  sip-medios: $(systemctl is-active sip-medios) como $(systemctl show -p User --value sip-medios)"
echo "RESULTADO: revisar las líneas de arriba (rollback: sh $B/rollback.sh)"
