#!/bin/sh
# yt-dlp en RESEARCH (05-11): imagen derivada + plugin sip-medios + config. Root, en Neo, desde este
# directorio; despliega en ~usuario/sip-fase7-research (donde corre el compose). No toca firewall ni redes.
# Rollback: cp $B/docker-compose.yml $B/config.yaml de vuelta (config al volumen como abajo), borrar
#   plugins/sip-medios del volumen y `docker compose up -d --force-recreate` en ~/sip-fase7-research.
set -eu
cd "$(dirname "$0")"
R=/home/usuario/sip-fase7-research
V=sip-research_hermes-research-home
TAG=hermes-research:0.26.0-a2026.9.14-ytdlp2026.10.26
B=/root/sip-agent-backups/$(date +%F)/research-ytdlp
install -d -m 700 "$B"
cp -p "$R/docker-compose.yml" "$B/"
docker exec hermes-research cat /opt/data/config.yaml > "$B/config.yaml"
docker build -q -f Dockerfile.ytdlp -t "$TAG" . >/dev/null
docker run --rm --network none --entrypoint sh "$TAG" -c 'PYTHONPATH=/opt/yt-dlp python3 -m yt_dlp --version'
docker run --rm --network none -v "$V:/d" -v "$PWD/config.yaml:/c:ro" -v "$PWD/plugins:/p:ro" busybox:1.36.1 \
  sh -c 'cp /c /d/config.yaml; mkdir -p /d/plugins; cp -r /p/. /d/plugins/
         chown -R 995:985 /d/config.yaml /d/plugins; chmod 600 /d/config.yaml'
install -o usuario -g usuario -m 644 docker-compose.yml "$R/docker-compose.yml"
(cd "$R" && docker compose config -q && docker compose up -d --force-recreate)
for i in $(seq 40); do
  [ "$(docker inspect -f '{{.State.Status}}' hermes-research)" = running ] && break; sleep 3
done
docker exec -w /opt/hermes hermes-research /opt/hermes/.venv/bin/python -c '
from hermes_cli.config import load_config
from hermes_cli.tools_config import _get_platform_tools
for p in ("cli", "api_server"):
    t = sorted(_get_platform_tools(load_config(), p)); print(p, t)
    assert "medios" in t and "terminal" not in t'
echo "RESULTADO: OK"
