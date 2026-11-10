#!/bin/sh
# OBSOLETO desde la migración a llama-swap (05-11): usa /api/create y /api/show de Ollama. La variante
# qwen3.8:27b-64k es ahora un alias en sip-config/llm-halo/llama-swap.yaml; no relanzar.
# Cambia el ejecutor de CODING de qwen3-coder:30b a qwen3.8:27b-64k (root, en Neo, desde una copia del
# repo con sip-config/). Motivo: piloto 2 del 03-11-2026 (el coder falló 4 de 4; qwen3.8 con 65.536 de
# contexto y razonamiento entregó). Pasos idempotentes:
#   1. HALO: etiqueta qwen3.8:27b-64k (FROM qwen3.8:27b, num_ctx 65536, temperature 0.6). PERSONAL sigue
#      con qwen3.8:27b sin tocar.
#   2. LiteLLM: modelo nuevo en la config y en la lista de sk-coding.
#   3. CODING: modelo principal por LiteLLM; fallback solo gpt-oss:20b (el coder sale de la cadena, sigue
#      instalado). Regenera la config de la API y recrea hermes-coding-api.
# Rollback: copiar "$B"/litellm.config.yaml a /opt/sip-litellm y recrear litellm; copiar "$B"/config.yaml
# al volumen de hermes-coding (docker cp + chown 993); sh make-api-config.sh y recrear hermes-coding-api.
# La lista de modelos de sk-coding queda ampliada (inocuo); el valor anterior está en "$B"/sk-coding.models.
set -eu
R=$(cd "$(dirname "$0")/.." && pwd)        # sip-config/
D=/home/usuario/sip-fase7-coding              # despliegue de CODING
B=/root/sip-agent-backups/$(date +%F)/coding-executor-$(date +%H%M%S)
M=qwen3.8:27b-64k
install -d -m 700 "$B"
cp -p /opt/sip-litellm/litellm.config.yaml "$B/"
docker exec hermes-coding cat /home/hermeswebui/.hermes/config.yaml > "$B/config.yaml"
cp -p "$D/config.api.yaml" "$B/"
docker exec sip-litellm-db psql -U litellm -d litellm -At \
  -c "select models from \"LiteLLM_VerificationToken\" where key_alias='sk-coding'" > "$B/sk-coding.models"

# 1. HALO
curl -sf http://${HALO_TAILNET_IP}:11434/api/create -d "{\"model\":\"$M\",\"from\":\"qwen3.8:27b\",
  \"parameters\":{\"num_ctx\":65536,\"temperature\":0.6},\"stream\":false}" | grep -q success
curl -sf http://${HALO_TAILNET_IP}:11434/api/show -d "{\"model\":\"$M\"}" | python3 -c '
import json, re, sys
p = json.load(sys.stdin)["parameters"]
assert re.search(r"^num_ctx\s+65536$", p, re.M) and re.search(r"^temperature\s+0.6$", p, re.M), p
print("HALO: etiqueta con num_ctx 65536 y temperature 0.6")'

# 2. LiteLLM
grep -q "model_name: $M" "$R/litellm/litellm.config.yaml"
if ! cmp -s "$R/litellm/litellm.config.yaml" /opt/sip-litellm/litellm.config.yaml; then
  install -m 0644 "$R/litellm/litellm.config.yaml" /opt/sip-litellm/
  # Recrear siempre: install cambia el inodo y el bind mount seguiría con el fichero anterior.
  (cd /opt/sip-litellm && docker compose up -d --wait --force-recreate --no-deps litellm)
fi
M="$M" python3 - <<'EOF'
import json, os, urllib.error, urllib.request
env = dict(l.rstrip("\n").split("=", 1) for l in open("/root/sip-litellm.env") if "=" in l and not l.startswith("#"))
zones = {i["zone"]: i["key"] for i in json.load(open("/root/sip-litellm-keys.json"))}
def call(path, key, body):
    req = urllib.request.Request("http://${NEO_TAILNET_IP}:4000" + path, json.dumps(body).encode(),
                                 {"Authorization": "Bearer " + key, "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=300) as r:
            return r.status, json.load(r)
    except urllib.error.HTTPError as e:
        return e.code, {}
models = ["qwen3-coder:30b", "qwen3.8:27b", "qwen3.6:27b", "gpt-oss:20b", os.environ["M"]]
s, _ = call("/key/update", env["LITELLM_MASTER_KEY"], {"key": zones["coding"], "models": models})
assert s == 200, f"key/update {s}"
s, d = call("/v1/chat/completions", zones["coding"], {"model": os.environ["M"], "max_tokens": 300,
            "messages": [{"role": "user", "content": "Responde solo: OK"}]})
assert s == 200, f"chat {s}"
print("LiteLLM: sk-coding llega a", os.environ["M"], "->", (d["choices"][0]["message"].get("content") or "").strip()[:40])
EOF

# 3. CODING
docker exec -i -u 993 -e M="$M" hermes-coding /app/venv/bin/python - <<'EOF'
import os
# Reemplazos de texto exactos para conservar los comentarios de la config.
p = "/home/hermeswebui/.hermes/config.yaml"
s = open(p).read()
m = os.environ["M"]
for old, new in (
    ("model:\n  default: qwen3-coder:30b\n  provider: custom:litellm\n",
     "model:\n  default: %s\n  provider: custom:litellm\n" % m),
    ("    default_model: qwen3-coder:30b\n    context_length: 65536\n",
     "    default_model: %s\n    context_length: 65536\n" % m),
    ("fallback_providers:\n  - provider: custom:ollama\n    model: qwen3.8:27b\n"
     "    base_url: http://${HALO_TAILNET_IP}:11434/v1\n", "fallback_providers:\n"),
):
    if new in s and old not in s:
        continue  # ya aplicado
    assert s.count(old) == 1, old
    s = s.replace(old, new)
open(p, "w").write(s)
EOF
docker exec -u 993 -e HOME=/home/hermeswebui -w /opt/hermes-agent hermes-coding /app/venv/bin/python -c '
from hermes_cli.config import load_config
from hermes_cli.config_providers import get_custom_provider_context_length as g
c = load_config()
n = g(c["model"]["default"], "http://sip-litellm:4000/v1", config=c)
print("CODING:", c["model"]["default"], c["model"]["provider"], "| contexto:", n,
      "| fallbacks:", [f["model"] for f in c["fallback_providers"]])
assert (c["model"]["default"], n) == ("qwen3.8:27b-64k", 65536)
assert [f["model"] for f in c["fallback_providers"]] == ["gpt-oss:20b"]'
cd "$D"
sh make-api-config.sh
docker compose up -d --force-recreate hermes-coding-api
grep -n -A2 "^model:" config.api.yaml
echo "RESULTADO: OK. Copia previa en $B"
