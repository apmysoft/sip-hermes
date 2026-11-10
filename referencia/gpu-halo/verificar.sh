#!/bin/sh
# Verificación del planificador de GPU de HALO (05-11). Root, en HALO. Repetible.
# Uso: sudo sh verificar.sh <audio.wav de prueba, sin datos personales>
set -eu
cd "$(dirname "$0")"
AUDIO=${1:?falta el audio de prueba}
H=http://${HALO_TAILNET_IP}:11434
fallo=0
corre() { curl -s $H/running | python3 -c 'import json,sys; print(" ".join(sorted(m["model"] for m in json.load(sys.stdin).get("running", []) if m.get("state") in ("ready","starting"))) or "-")'; }
gpu() { echo "$(systemctl is-active sip-whisper-gpu) / $(systemctl is-active sip-comfyui)"; }
texto() {
  curl -s $H/v1/chat/completions -H 'Content-Type: application/json' \
    -d '{"model":"qwen3.8:27b","messages":[{"role":"user","content":"Responde solo OK"}],"max_tokens":400}' \
    | python3 -c 'import json,sys; d=json.load(sys.stdin); print(d["choices"][0]["message"]["content"].strip()[:10])' 2>/dev/null || echo FALLO
}
echo "== 1. modelos en /v1/models: $(curl -s $H/v1/models | python3 -c 'import json,sys; print(len(json.load(sys.stdin)["data"]))') (esperados 12)"

echo "== 2. polkit: sip-llm no puede tocar otras unidades ni otros verbos"
# Como llama-swap: proceso de sip-llm SIN sesión de logind (unidad transitoria). Con runuser desde una sesión
# gráfica polkit pregunta al usuario del escritorio y la prueba no vale (incidencia del 05-11).
como_llm() { systemd-run --quiet --uid=sip-llm --gid=sip-llm --pipe --wait --collect "$@" >/dev/null 2>&1; }
for c in "start sip-whisper.service" "restart sip-comfyui.service" "stop sip-whisper.service" "start ssh.service"; do
  if como_llm /bin/systemctl --no-ask-password $c; then echo "  PERMITIDO (mal): $c"; fallo=1; else echo "  denegado: $c"; fi
done
if como_llm /bin/systemctl --no-ask-password start sip-whisper-gpu.service && como_llm /bin/systemctl --no-ask-password stop sip-whisper-gpu.service; then
  echo "  permitido (bien): start/stop sip-whisper-gpu.service"; else echo "  DENEGADO (mal): start/stop sip-whisper-gpu"; fallo=1; fi
runuser -u sip-llm -- /usr/local/lib/sip-gpu/sip-gpu-unidad sip-whisper.service 2>&1 | sed 's/^/  /'
[ "$(systemctl is-active llama-swap)" = active ] || { echo "  llama-swap parado: FALLO"; exit 1; }

echo "== 3. texto -> audio largo por la GPU"
echo "  texto: $(texto) | en GPU: $(corre)"
t=$(date +%s)
n=$(curl -s -F file=@"$AUDIO" -F response_format=text -F temperature=0 $H/upstream/whisper-gpu/inference | wc -w)
echo "  audio: $n palabras en $(( $(date +%s) - t )) s (con el cambio) | en GPU: $(corre) | whisper-gpu/comfyui: $(gpu)"
[ "$n" -gt 100 ] || fallo=1

echo "== 4. vuelta al texto"
t=$(date +%s); r=$(texto); echo "  texto: $r en $(( $(date +%s) - t )) s | en GPU: $(corre) | whisper-gpu/comfyui: $(gpu)"
[ "$r" = OK ] || fallo=1

echo "== 5. imagen con ComfyUI por /comfyui"
img=$(SIP_COMFY_API=$H/comfyui python3 ../comfyui/probar-imagen.py "a lighthouse on a cliff at sunset, photo" 7 flux 2>&1 | tail -1)
echo "  $img | en GPU: $(corre) | whisper-gpu/comfyui: $(gpu)"
case "$img" in OK*) f=$(echo "$img" | sed -n "s/.*\['\([^']*\)'.*/\1/p"); [ -n "$f" ] && rm -f "/opt/sip-comfyui/ComfyUI/output/$f" && echo "  (imagen de prueba borrada)";; *) fallo=1;; esac

echo "== 6. vuelta al texto"
t=$(date +%s); r=$(texto); echo "  texto: $r en $(( $(date +%s) - t )) s | en GPU: $(corre) | whisper-gpu/comfyui: $(gpu)"
[ "$r" = OK ] || fallo=1
[ "$(gpu)" = "inactive / inactive" ] || fallo=1

[ $fallo = 0 ] && echo "VERIFICACIÓN: OK" || { echo "VERIFICACIÓN: FALLO" >&2; exit 1; }
