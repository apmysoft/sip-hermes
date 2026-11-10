#!/bin/sh
# O4 (v2.4): qué ve una skill maliciosa desde el terminal de cada zona. En Neo, como usuario (usa docker).
# Ejecuta la herramienta de terminal real de Hermes (tools.terminal_tool) con el usuario del agente y
# muestra solo NOMBRES de variables sensibles y si el .env es legible; nunca valores.
# RESEARCH no tiene terminal (solo browser y entrada): se comprueba con `hermes tools list`.
set -eu
PRUEBA=$(cat <<'EOF'
import json, os, sys
sys.path.insert(0, os.getcwd())
from hermes_cli.env_loader import load_hermes_dotenv
load_hermes_dotenv()
import tools.terminal_tool as T
cmd = ("hostname; printenv | cut -d= -f1 | grep -iE 'key|token|secret|pass|auth' || echo '(ninguna variable sensible)'; "
       "test -r ~/.hermes/.env && echo '.env de Hermes LEGIBLE' || echo '.env de Hermes: no'")
print(json.loads(T.terminal_tool(command=cmd, task_id="o4-lab")).get("output"))
EOF
)
echo "== CODING (API, uid 993)"
echo "$PRUEBA" | docker exec -i -u 993 -w /opt/hermes-agent -e HOME=/home/hermeswebui hermes-coding-api /app/venv/bin/python -
echo "== PERSONAL (perfil personal, uid 1000)"
echo "$PRUEBA" | docker exec -i -u 1000 -w /tmp -e HOME=/home/hermeswebui \
    -e HERMES_HOME=/home/hermeswebui/.hermes/profiles/personal hermes-webui \
    sh -c 'cd "$(dirname "$(find / -xdev -path "*/tools/terminal_tool.py" 2>/dev/null | head -1)")/.." && /app/venv/bin/python -'
echo "== RESEARCH (uid 995): herramientas activas"
for p in cli api_server; do
    echo "-- $p: $(docker exec -u 995 hermes-research hermes tools list --platform $p 2>&1 | grep '✓' | awk '{print $3}' | tr '\n' ' ')"
done
