#!/bin/sh
# Genera config.api.yaml (root, en Neo) desde la config del perfil personal de hermes-webui:
# - herramientas de api_server fijadas (sin terminal: v2.4, PERSONAL sin terminal);
# - aprobaciones deterministas: por la API nadie puede aprobar, así que lo peligroso se deniega.
# El consentimiento de los renombres sigue siendo el código de un solo uso del gestor (no usa aprobaciones).
# Volver a lanzar tras cambiar la config de personal y recrear hermes-personal-api.
# 09-11: lista de api_server al día (imagen, procesar y delegation, añadidas por los bloques del 05-11 y 06-11) y
# comprobación de los plugins actuales. Con un argumento escribe ahí en lugar de config.api.yaml (para comparar).
set -eu
cd "$(dirname "$0")"
SALIDA=${1:-config.api.yaml}
docker exec -u 1000 -e HOME=/home/hermeswebui hermes-webui /app/venv/bin/python -c '
import sys, yaml
c = yaml.safe_load(open("/home/hermeswebui/.hermes/profiles/personal/config.yaml"))
assert "sip-documentos" in c["plugins"]["enabled"], "falta el plugin sip-documentos"
for p in ("sip-transcribir", "sip-imagen", "sip-medios", "advanced-delegation", "sip-flujos", "sip-halo-wake"):
    assert p in c["plugins"]["enabled"], "falta el plugin " + p
c.setdefault("platform_toolsets", {})["api_server"] = ["documentos", "file", "memory", "session_search", "skills", "todo",
                                                       "transcribir", "imagen", "procesar", "delegation"]
a = c.setdefault("approvals", {})
a["mode"] = "manual"
a["timeout"] = 5
assert c["memory"]["write_approval"] is True
yaml.safe_dump(c, sys.stdout, sort_keys=False, allow_unicode=True)' > "$SALIDA.tmp"
if [ "$SALIDA" = config.api.yaml ]; then
  cat "$SALIDA.tmp" > config.api.yaml   # mismo inodo: el contenedor lo monta como fichero suelto
  rm -f "$SALIDA.tmp"
else
  mv "$SALIDA.tmp" "$SALIDA"
fi
chmod 644 "$SALIDA"
grep -A3 '^approvals:' "$SALIDA"
grep -A11 '  api_server:' "$SALIDA"
