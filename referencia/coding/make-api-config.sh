#!/bin/sh
# Genera config.api.yaml (root, en Neo) desde la config de CODING con aprobaciones deterministas:
# por la API nadie puede aprobar, así que lo peligroso se deniega sin consultar a ningún modelo
# (decisión: nada destructivo por Telegram). La WebUI sigue con su modo smart. Volver a lanzar tras
# cambiar la config de CODING y recrear hermes-coding-api.
set -eu
cd "$(dirname "$0")"
docker exec -u 993 -e HOME=/home/hermeswebui -w /opt/hermes-agent hermes-coding /app/venv/bin/python -c '
import sys, yaml
c = yaml.safe_load(open("/home/hermeswebui/.hermes/config.yaml"))
a = c.setdefault("approvals", {})
a["mode"] = "manual"
a["timeout"] = 5
assert c["platform_toolsets"]["api_server"] == ["terminal", "file", "todo", "memory", "session_search", "skills"]
yaml.safe_dump(c, sys.stdout, sort_keys=False, allow_unicode=True)' > config.api.yaml.tmp
mv config.api.yaml.tmp config.api.yaml
chmod 644 config.api.yaml
grep -A3 '^approvals:' config.api.yaml
