#!/bin/sh
# Construye y arranca hermes-research (root, en Neo). No toca firewall ni otros servicios.
# Rollback: docker compose down -v; docker rmi hermes-research:0.26.0-a2026.9.14.
set -eu
cd "$(dirname "$0")"
docker build -q -t hermes-research:0.26.0-a2026.9.14 .
docker compose config -q
docker compose up -d --no-start
V=sip-research_hermes-research-home
docker run --rm --network none -v "$V:/d" -v "$PWD/config.yaml:/c:ro" -v "$PWD/plugins:/p:ro" busybox:1.36.1 \
  sh -c 'cp /c /d/config.yaml; mkdir -p /d/plugins; cp -r /p/. /d/plugins/
         chown -R 995:985 /d; chmod 700 /d; chmod 600 /d/config.yaml'
docker compose up -d --force-recreate
docker exec hermes-research sh -c 'id; agent-browser --version; hermes --version | head -1'
