#!/bin/sh
# OBSOLETO desde la migración a llama-swap (05-11): usa /api/create y /api/show de Ollama. La variante
# qwen3.8:27b-64k es ahora un alias en sip-config/llm-halo/llama-swap.yaml; no relanzar.
# PERSONAL pasa de qwen3.8:27b (32k) a qwen3.8:27b-64k (root, en Neo). Motivo: el 03-11 la revisión de un
# lote se congelaba y truncaba con 32k. La etiqueta ya existe en HALO (la usa CODING: num_ctx 65536,
# temperature 0.6, 17,5 GB, 100 % GPU); compartirla evita que HALO cambie de modelo entre zonas.
# Fallbacks sin cambios. Rollback: cp -p "$B"/config.yaml "$C" (las sesiones nuevas lo toman).
set -eu
C=${DOCKER_DATA}/docker_root/volumes/hermes_hermes-home/_data/profiles/personal/config.yaml
B=/root/sip-agent-backups/$(date +%F)/personal-64k
M=qwen3.8:27b-64k
install -d -m 0700 "$B"
[ -e "$B/config.yaml" ] || cp -p "$C" "$B/"

curl -sf http://${HALO_TAILNET_IP}:11434/api/show -d "{\"model\":\"$M\"}" | python3 -c '
import json, re, sys
p = json.load(sys.stdin)["parameters"]
assert re.search(r"^num_ctx\s+65536$", p, re.M), p
print("HALO: la etiqueta existe con num_ctx 65536")'

# Reemplazos de texto exactos para conservar comentarios, modo y propietario.
M="$M" python3 -I - "$C" <<'EOF'
import os, sys
p, m = sys.argv[1], os.environ["M"]
s = open(p).read()
for old, new in (
    ("model:\n  default: qwen3.8:27b\n  provider: custom:ollama\n",
     "model:\n  default: %s\n  provider: custom:ollama\n" % m),
    ("    default_model: qwen3.8:27b\n", "    default_model: %s\n    context_length: 65536\n" % m),
):
    if new in s and old not in s:
        continue  # ya aplicado
    assert s.count(old) == 1, old
    s = s.replace(old, new)
with open(p, "r+") as f:
    f.write(s)
    f.truncate()
EOF
stat -c "config: %U:%G %a" "$C"

docker exec -u 1000 -e HOME=/home/hermeswebui -e HERMES_HOME=/home/hermeswebui/.hermes/profiles/personal \
  -w /opt/hermes-agent hermes-webui /app/venv/bin/python -c '
from hermes_cli.config import load_config
from hermes_cli.config_providers import get_custom_provider_context_length as g
c = load_config()
n = g(c["model"]["default"], "http://${HALO_TAILNET_IP}:11434/v1", config=c)
print("PERSONAL:", c["model"]["default"], c["model"]["provider"], "| contexto:", n,
      "| fallbacks:", [f["model"] for f in c["fallback_providers"]])
assert (c["model"]["default"], n) == ("qwen3.8:27b-64k", 65536)'
echo "RESULTADO: OK. Copia previa en $B"
