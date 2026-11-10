#!/bin/sh
# Planificador de GPU de HALO (05-11): llama-swap reparte la 7900 XTX entre el modelo de texto, Whisper-GPU y
# ComfyUI (grupo gpu: uno a la vez). Root, en HALO, desde este directorio.
# Requisitos: ../whisper/install-gpu.sh ejecutado (binario whisper-server-vulkan).
# Uso: sudo sh apply.sh <audio.wav de prueba, sin datos personales>
# Rollback: sh $B/rollback.sh
set -eu
cd "$(dirname "$0")"
AUDIO=${1:?falta el audio de prueba}
H=http://${HALO_TAILNET_IP}:11434
B=/root/sip-agent-backups/$(date +%F)/gpu-halo
[ ! -e "$B" ] || { echo "ERROR: ya existe $B" >&2; exit 1; }
[ -x /opt/sip-whisper/bin/whisper-server-vulkan ] || { echo "ERROR: falta whisper-server-vulkan" >&2; exit 1; }
[ "$(systemctl is-enabled sip-comfyui 2>&1)" = disabled ] || { echo "ERROR: sip-comfyui debería estar deshabilitado" >&2; exit 1; }

install -d -m 700 "$B"
cp -a /var/lib/sip-llm/llama-swap.yaml /etc/systemd/system/llama-swap.service /etc/systemd/system/sip-comfyui.service "$B/"
ls -la /etc/polkit-1/rules.d/ > "$B/polkit-rules.d.txt"
cat > "$B/rollback.sh" <<EOF
#!/bin/sh
# Deja HALO como antes del planificador de GPU.
systemctl stop sip-comfyui.service sip-whisper-gpu.service 2>/dev/null
rm -f /etc/polkit-1/rules.d/50-sip-llm-gpu.rules /etc/systemd/system/sip-whisper-gpu.service \\
      /etc/systemd/system/llama-swap.service.d/50-sip-gpu.conf
rm -rf /usr/local/lib/sip-gpu
rmdir /etc/systemd/system/llama-swap.service.d 2>/dev/null
install -o root -g sip-llm -m 640 $B/llama-swap.yaml /var/lib/sip-llm/llama-swap.yaml
install -m 644 $B/sip-comfyui.service /etc/systemd/system/sip-comfyui.service
systemctl daemon-reload; systemctl restart llama-swap
sleep 3; curl -s -o /dev/null -w "llama-swap /v1/models: %{http_code}\n" $H/v1/models
EOF
echo "copia en $B"

install -o root -g root -m 644 50-sip-llm-gpu.rules /etc/polkit-1/rules.d/50-sip-llm-gpu.rules
install -d -o root -g root -m 755 /usr/local/lib/sip-gpu
install -o root -g root -m 755 sip-gpu-unidad /usr/local/lib/sip-gpu/sip-gpu-unidad
install -o root -g root -m 644 sip-whisper-gpu.service /etc/systemd/system/sip-whisper-gpu.service
install -o root -g root -m 644 ../comfyui/sip-comfyui.service /etc/systemd/system/sip-comfyui.service
install -d -m 755 /etc/systemd/system/llama-swap.service.d
install -o root -g root -m 644 llama-swap-gpu.conf /etc/systemd/system/llama-swap.service.d/50-sip-gpu.conf
install -o root -g sip-llm -m 640 ../llm-halo/llama-swap.yaml /var/lib/sip-llm/llama-swap.yaml
systemd-analyze verify /etc/systemd/system/sip-whisper-gpu.service 2>&1 | grep -v "^$" || true
systemctl daemon-reload
systemctl restart llama-swap
ok=0
for i in $(seq 60); do curl -sf -o /dev/null $H/v1/models && { ok=1; break; }; sleep 2; done
[ $ok = 1 ] || { echo "RESULTADO: FALLO llama-swap no responde (rollback: sh $B/rollback.sh)" >&2; journalctl -u llama-swap -n 20 --no-pager; exit 1; }

sh ./verificar.sh "$AUDIO" || { echo "RESULTADO: REVISAR (rollback: sh $B/rollback.sh)" >&2; exit 1; }
echo "RESULTADO: OK (rollback: sh $B/rollback.sh)"
