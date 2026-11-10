#!/bin/sh
# S.2 de v2.4: tiny en la 1070 con triple contención (transcodificación NVENC de Jellyfin + ML de Immich
# + tiny a la vez), con carga sintética: vídeo testsrc2 1080p generado por ffmpeg e imágenes de ruido,
# sin tocar las bibliotecas. Como usuario en Neo (docker). No cambia ninguna configuración.
# Mide el tiny con la misma petición que el gestor (JSON por schema, max_tokens 300).
set -eu
DUR=${S2_DUR:-120}
OUT=${S2_OUT:-/tmp/s2-$(date +%Y%m%d-%H%M%S)}
mkdir -p "$OUT"

tiny() {  # $1 = etiqueta; 4 peticiones seguidas
  python3 -I - "$1" <<'EOF'
import json, sys, time, urllib.request
SCHEMA = {"name": "renombre", "strict": True, "schema": {"type": "object", "additionalProperties": False,
          "required": ["nuevo_nombre", "confianza", "abstencion", "motivo"],
          "properties": {"nuevo_nombre": {"type": "string"}, "confianza": {"type": "number"},
                         "abstencion": {"type": "boolean"}, "motivo": {"type": "string"}}}}
txt = ("Acta de la reunión de la comunidad de propietarios del 12 de marzo. Orden del día: cuentas del "
       "ejercicio, derrama para la fachada y cambio de administrador. ") * 8
res = []
for _ in range(4):
    body = {"model": "qwen3-4b-instruct", "max_tokens": 300, "temperature": 0.2,
            "response_format": {"type": "json_schema", "json_schema": SCHEMA},
            "messages": [{"role": "system", "content": "Propón un nombre de fichero descriptivo en JSON."},
                         {"role": "user", "content": f"Fichero actual: `doc.pdf`.\nExtracto:\n<<<\n{txt}\n>>>"}]}
    t = time.time()
    with urllib.request.urlopen(urllib.request.Request("http://127.0.0.1:11434/v1/chat/completions",
            json.dumps(body).encode(), {"Content-Type": "application/json"}), timeout=300) as r:
        d = json.load(r)
    dt = time.time() - t
    json.loads(d["choices"][0]["message"]["content"])          # JSON válido
    res.append((dt, d["usage"]["completion_tokens"] / dt))
s = sorted(r[0] for r in res)
print(f"{sys.argv[1]}: {len(res)} peticiones, JSON válido; segundos/petición mediana {s[len(s)//2]:.2f} "
      f"máx {s[-1]:.2f}; tok/s de salida medio {sum(r[1] for r in res)/len(res):.1f}")
EOF
}

gpu() { nvidia-smi --query-gpu=memory.used,utilization.gpu,utilization.encoder --format=csv,noheader; }

echo "reposo GPU: $(gpu)"
tiny "solo tiny" | tee "$OUT/base.txt"

# Carga: transcodificación 1080p NVENC sin -re (peor caso) e inferencias CLIP + caras en bucle.
# Sin -re, una pasada de 120 s de vídeo dura ~12 s (10x): se sostiene con timeout durante toda la prueba.
docker exec -d jellyfin sh -c "timeout $((DUR + 10)) /usr/lib/jellyfin-ffmpeg/ffmpeg -hide_banner -nostats -f lavfi \
  -i testsrc2=size=1920x1080:rate=30 -t 36000 -c:v h264_nvenc -preset p4 -b:v 8M -f null - \
  > /tmp/s2-ffmpeg.log 2>&1"
docker exec -d immich_machine_learning python3 -c "
import io, json, time, requests
from PIL import Image
e = json.dumps({'clip': {'visual': {'modelName': 'ViT-B-32__openai', 'options': {}}},
     'facial-recognition': {'detection': {'modelName': 'buffalo_l', 'options': {'minScore': 0.7}},
                            'recognition': {'modelName': 'buffalo_l', 'options': {}}}})
fin, n = time.time() + $DUR, 0
while time.time() < fin:
    b = io.BytesIO(); Image.effect_noise((1920, 1080), 64).convert('RGB').save(b, 'JPEG')
    requests.post('http://127.0.0.1:3003/predict', data={'entries': e}, files={'image': b.getvalue()}); n += 1
open('/tmp/s2-ml.txt', 'w').write(str(n))"
sleep 15
echo "con carga GPU: $(gpu)" | tee "$OUT/gpu.txt"
tiny "triple contención" | tee "$OUT/carga.txt"
echo "con carga GPU: $(gpu)" | tee -a "$OUT/gpu.txt"
nvidia-smi --query-compute-apps=pid,process_name,used_memory --format=csv,noheader | tee -a "$OUT/gpu.txt"
nvidia-smi | grep -E " (C|G|C\+G) " | tee -a "$OUT/gpu.txt" || true
sleep "$DUR"
sleep 10
echo "ffmpeg: $(docker exec jellyfin sh -c 'tail -c 300 /tmp/s2-ffmpeg.log; rm -f /tmp/s2-ffmpeg.log' | tr '\r\n' '  ' | grep -o 'frame= *[0-9]*.*speed=[^ ]*' | tail -1)"
echo "Immich ML: $(docker exec immich_machine_learning sh -c 'cat /tmp/s2-ml.txt; rm -f /tmp/s2-ml.txt') inferencias en ${DUR} s"
echo "reposo GPU después: $(gpu)"
echo "RESULTADO en $OUT"
