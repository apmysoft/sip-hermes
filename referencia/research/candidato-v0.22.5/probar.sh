#!/bin/sh
# Prueba la candidata en un contenedor desechable (root, en Neo). No toca hermes-research ni filegate.
# Se borra sola al terminar; el volumen es anónimo.
set -u
cd "$(dirname "$0")"
TAG=hermes-research:cand-0.26.0-a0.22.5
docker build -q -t "$TAG" . || exit 1
docker rm -f hermes-research-cand >/dev/null 2>&1
docker run -d --name hermes-research-cand --network research --user 995:985 --init \
  --read-only --tmpfs /tmp:rw,nosuid,nodev,size=768m --shm-size 256m --memory 2g --cpus 2 \
  --pids-limit 512 --cap-drop ALL --security-opt no-new-privileges:true --tmpfs /opt/data:rw,nosuid,nodev,uid=995,gid=985,size=256m \
  --env-file /root/sip-litellm-research-cloud.env \
  -e HERMES_HOME=/opt/data -e HOME=/opt/data -e XDG_CACHE_HOME=/tmp/cache \
  -e AGENT_BROWSER_EXECUTABLE_PATH=/opt/hermes/tools/chromium-1208/chrome-linux64/chrome \
  -e AGENT_BROWSER_ARGS=--no-sandbox \
  --entrypoint sleep "$TAG" infinity >/dev/null || exit 1
docker exec -i hermes-research-cand sh -c 'cat > /opt/data/config.yaml' < ../config.yaml
tar -C .. -cf - plugins | docker exec -i hermes-research-cand tar -C /opt/data -xf -
C="docker exec hermes-research-cand"
$C sh -c 'id; python3 --version; agent-browser --version; hermes --version 2>/dev/null | sed -n 1p'
$C hermes plugins list 2>&1 | grep -iE "entrada" | cut -c1-90
$C python3 -W ignore -c '
import sys; sys.path.insert(0,"/opt/hermes")
from hermes_cli.plugins import discover_plugins
discover_plugins()
from model_tools import get_tool_definitions
n=[x["function"]["name"] for x in get_tool_definitions(enabled_toolsets=["browser","entrada"],quiet_mode=True)]
print("tools", [t for t in n if t in ("browser_navigate","entrada_guardar","browser_exec")])' 2>&1 | tail -1 | cut -c1-200
$C sh -c 'cd /tmp; mkdir -p w; echo "<h1>Marca-CAND-4417</h1>" > w/i.html; cd w; nohup timeout 200 python3 -m http.server 8088 --bind 127.0.0.1 > /tmp/acc.log 2>&1 &'
sleep 2
$C sh -c 'cat /opt/data/config.yaml | sed "s/allow_private_urls: false/allow_private_urls: true/" > /tmp/c && cp /tmp/c /opt/data/config.yaml'
timeout 170 $C hermes -z "Con el navegador abre http://127.0.0.1:8088/i.html y responde solo con el texto del h1." 2>&1 | tail -4 | cut -c1-260
echo "--- accesos"; $C grep -c 'GET /i.html' /tmp/acc.log
$C grep -E '"_config_version"|^_config_version' /opt/data/config.yaml | head -1
docker rm -f hermes-research-cand >/dev/null
