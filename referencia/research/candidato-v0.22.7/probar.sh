#!/bin/sh
# Prueba la candidata v0.22.7 de RESEARCH en un contenedor desechable (root, en Neo), sobre una COPIA del
# volumen real (sip-research_hermes-research-home -> hermes-research-cand-home), con la config candidata y
# los plugins del repo. Sin socket de filegate: no escribe en PARA. Mismas restricciones que producción.
# Uso: sh probar.sh <dir con config.yaml y plugins/>   (lo borra todo al terminar)
set -u
SRC=${1:?dir de la candidata}
TAG=hermes-research:cand-0.26.0-a0.22.7
V=hermes-research-cand-home
C="docker exec hermes-research-cand"
docker rm -f hermes-research-cand >/dev/null 2>&1; docker volume rm $V >/dev/null 2>&1
docker volume inspect sip-research_hermes-research-home >/dev/null || { echo "ERROR: no existe el volumen real" >&2; exit 1; }
docker volume create $V >/dev/null
docker run --rm -v sip-research_hermes-research-home:/s:ro -v $V:/d busybox:1.36.1 cp -a /s/. /d/
docker run -d --name hermes-research-cand --network research --user 995:985 --group-add 986 --init \
  --read-only --tmpfs /tmp:rw,nosuid,nodev,size=768m --shm-size 256m --memory 2g --cpus 2 \
  --pids-limit 512 --cap-drop ALL --security-opt no-new-privileges:true -v $V:/opt/data \
  --env-file /root/sip-litellm-research-cloud.env \
  -e HERMES_HOME=/opt/data -e HOME=/opt/data -e XDG_CACHE_HOME=/tmp/cache \
  -e AGENT_BROWSER_EXECUTABLE_PATH=/opt/hermes/tools/chromium-1208/chrome-linux64/chrome \
  -e AGENT_BROWSER_ARGS=--no-sandbox \
  --entrypoint sleep "$TAG" infinity >/dev/null || exit 1
# Config y plugins candidatos (como haría el apply del corte)
docker exec -i hermes-research-cand sh -c 'cat > /opt/data/config.yaml' < "$SRC/config.yaml"
tar -C "$SRC" -cf - plugins | docker exec -i hermes-research-cand tar -C /opt/data -xf -
$C sh -c 'rm -rf /opt/data/plugins/sip-browser-guard'
echo "== versiones"
$C sh -c 'id; python3 -V; agent-browser --version; PYTHONPATH=/opt/yt-dlp python3 -m yt_dlp --version; hermes --version 2>/dev/null | head -1'
$C python3 -c 'import sqlite3;c=sqlite3.connect(":memory:");o=[r[0] for r in c.execute("pragma compile_options")];print("sqlite",sqlite3.sqlite_version,"FTS5" if "ENABLE_FTS5" in o else "SIN-FTS5")'
echo "== plugins"; $C hermes plugins list 2>&1 | grep -E "^│ sip-" | cut -c1-40
echo "== herramientas visibles por plataforma"
$C python3 -W ignore -c '
import sys; sys.path.insert(0,"/opt/hermes")
from hermes_cli.plugins import discover_plugins
discover_plugins()
from hermes_cli.config import load_config
from model_tools import get_tool_definitions
cfg=load_config()
for plat in ("cli","api_server"):
    ts=cfg["platform_toolsets"][plat]
    n=sorted(x["function"]["name"] for x in get_tool_definitions(enabled_toolsets=ts,quiet_mode=True))
    malas=[t for t in n if t in ("terminal","browser_exec","write_file","read_file","patch","execute_code","tool_search") or t.startswith("browser_")]
    print(plat, n, "PROHIBIDAS:"+str(malas) if malas else "OK sin terminal/ficheros/browser_exec/tool_search")' 2>&1 | tail -2 | cut -c1-400
echo "== política (llamada directa al plugin, sin modelo)"
$C python3 -W ignore -c '
import sys,json; sys.path.insert(0,"/opt/data/plugins")
import importlib; m=importlib.import_module("sip-navegador".replace("-","_")) if False else None
import importlib.util as u
s=u.spec_from_file_location("nav","/opt/data/plugins/sip-navegador/__init__.py"); m=u.module_from_spec(s); s.loader.exec_module(m)
for url in ("file:///etc/passwd","http://localhost:8642/","https://www.bbva.es/","http://10.20.0.10:4000/","http://${NEO_TAILNET_IP}:8787/","https://accounts.google.com/"):
    print("bloquea" if "error" in json.loads(m.navegador_abrir({"url":url})) else "PERMITE!!", url)
r=json.loads(m.navegador_abrir({"url":"https://example.com"})); print("example.com:", r.get("url"), "elementos" in r, r.get("error",""))
r=json.loads(m.navegador_leer({})); print("leer:", "documentation" in r.get("texto",""))
m.navegador_cerrar({})'
echo "== modelo + navegador (1 llamada)"
timeout 170 $C hermes -z "Con el navegador abre https://example.com y responde solo con el texto del encabezado h1." 2>&1 | tail -2 | cut -c1-200
echo "== config tras migración"; $C sh -c 'grep -E "^_config_version|^  backend|enabled: .off" /opt/data/config.yaml'
docker rm -f hermes-research-cand >/dev/null; docker volume rm $V >/dev/null
