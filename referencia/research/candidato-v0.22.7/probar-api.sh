#!/bin/sh
# Prueba la candidata en modo `hermes gateway run` (como producción) con la clave real de la API, sobre una
# copia del volumen; escucha solo dentro del contenedor (127.0.0.1). Root, en Neo. Uso: sh probar-api.sh <dir>
set -u
SRC=${1:?dir de la candidata}
TAG=hermes-research:cand-0.26.0-a0.22.7
V=hermes-research-cand-home
docker rm -f hermes-research-cand >/dev/null 2>&1; docker volume rm $V >/dev/null 2>&1
docker volume create $V >/dev/null
docker run --rm -v sip-research_hermes-research-home:/s:ro -v $V:/d busybox:1.36.1 cp -a /s/. /d/
docker run --rm -v $V:/d -v "$SRC/config.yaml:/c:ro" -v "$SRC/plugins:/p:ro" busybox:1.36.1 sh -c \
  'cp /c /d/config.yaml; cp -r /p/. /d/plugins/; rm -rf /d/plugins/sip-browser-guard /d/gateway.pid /d/gateway.lock /d/gateway.sock; chown -R 995:985 /d/config.yaml /d/plugins; chmod 600 /d/config.yaml'
docker run -d --name hermes-research-cand --network research --user 995:985 --group-add 986 --init \
  --read-only --tmpfs /tmp:rw,nosuid,nodev,size=768m --shm-size 256m --memory 2g --cpus 2 \
  --pids-limit 512 --cap-drop ALL --security-opt no-new-privileges:true -v $V:/opt/data \
  --env-file /root/sip-litellm-research-cloud.env --env-file /root/sip-research-api.env \
  -e HERMES_HOME=/opt/data -e HOME=/opt/data -e XDG_CACHE_HOME=/tmp/cache \
  -e AGENT_BROWSER_EXECUTABLE_PATH=/opt/hermes/tools/chromium-1208/chrome-linux64/chrome \
  -e AGENT_BROWSER_ARGS=--no-sandbox -e API_SERVER_HOST=127.0.0.1 -e API_SERVER_PORT=8642 \
  --entrypoint hermes "$TAG" gateway run >/dev/null || exit 1
for i in $(seq 40); do
  docker exec hermes-research-cand python3 -c 'import urllib.request;urllib.request.urlopen("http://127.0.0.1:8642/health",timeout=3)' 2>/dev/null && break; sleep 3
done
docker exec hermes-research-cand python3 -c '
import urllib.request,json,os
print("health", urllib.request.urlopen("http://127.0.0.1:8642/health",timeout=5).status)
for k in (None,"mala"):
    try:
        r=urllib.request.Request("http://127.0.0.1:8642/v1/models",headers={"Authorization":"Bearer "+k} if k else {})
        print("sin clave/clave mala ->", urllib.request.urlopen(r,timeout=5).status, "(MAL)")
    except urllib.error.HTTPError as e: print("sin clave/clave mala ->", e.code)
body=json.dumps({"model":"hermes-agent","messages":[{"role":"user","content":"Con el navegador abre https://example.com y responde solo con el texto del encabezado h1."}]}).encode()
r=urllib.request.Request("http://127.0.0.1:8642/v1/chat/completions",data=body,headers={"Authorization":"Bearer "+os.environ["API_SERVER_KEY"],"Content-Type":"application/json"})
d=json.load(urllib.request.urlopen(r,timeout=170))
print("respuesta:", d["choices"][0]["message"]["content"][:120])'
docker logs hermes-research-cand 2>&1 | grep -iE "error|warn|notice|removed|traceback" | cut -c1-200 | head -8
docker rm -f hermes-research-cand >/dev/null; docker volume rm $V >/dev/null
