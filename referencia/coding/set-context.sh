#!/bin/sh
# Fija en CODING el contexto real de cada proveedor (root, en Neo), para que Hermes resuma la
# conversación antes de pasarse. Sin esto supone 128K y Ollama recorta en silencio por encima de su
# num_ctx (incidencia del piloto 2, 02-11-2026). Valores: qwen3-coder:30b con num_ctx 65536 (Modelfile
# propio en HALO); el resto de modelos de Ollama, con el global de 32768.
# Rollback: copiar "$B/config.yaml" al volumen y relanzar make-api-config.sh + recrear hermes-coding-api.
set -eu
cd "$(dirname "$0")"
B=/root/sip-agent-backups/$(date +%F)/coding-context-$(date +%H%M%S)
install -d -m 700 "$B"
docker exec hermes-coding cat /home/hermeswebui/.hermes/config.yaml > "$B/config.yaml"

docker exec -i -u 993 hermes-coding /app/venv/bin/python - <<'EOF'
p = "/home/hermeswebui/.hermes/config.yaml"
s = open(p).read()
for anchor, line in (("    default_model: qwen3-coder:30b\n", "    context_length: 65536\n"),
                     ("    default_model: qwen3.8:27b\n", "    context_length: 32768\n")):
    if anchor + line in s:
        continue  # ya aplicado
    assert s.count(anchor) == 1, anchor
    s = s.replace(anchor, anchor + line)
open(p, "w").write(s)
EOF

docker exec -u 993 -e HOME=/home/hermeswebui -w /opt/hermes-agent hermes-coding /app/venv/bin/python -c '
from hermes_cli.config import load_config
from hermes_cli.config_providers import get_custom_provider_context_length as g
c = load_config()
coder = g("qwen3-coder:30b", "http://sip-litellm:4000/v1", config=c)
alt = g("qwen3.8:27b", "http://${HALO_TAILNET_IP}:11434/v1", config=c)
print("contexto coder:", coder, "| alternativa:", alt)
assert (coder, alt) == (65536, 32768)'

sh make-api-config.sh
grep -n "context_length" config.api.yaml
docker compose up -d --force-recreate hermes-coding-api
echo "RESULTADO: OK. Copia previa en $B"
