#!/bin/sh
# Conecta LiteLLM a la red research, añade Gemini y verifica (root, en Neo). No toca firewall.
# Rollback: copiar docker-compose.yml y litellm.config.yaml del backup a /opt/sip-litellm,
# docker compose up -d litellm; revocar la clave con /key/delete y borrar
# /root/sip-litellm-research-cloud.env.
set -eu
cd "$(dirname "$0")"
B="/root/sip-agent-backups/$(date +%F)/fase6d"
install -d -m 700 "$B"
cp -p /opt/sip-litellm/docker-compose.yml /opt/sip-litellm/litellm.config.yaml "$B/"
docker exec sip-litellm-db pg_dump -U litellm litellm | gzip > "$B/litellm-db-pre.sql.gz"
chmod 600 "$B/litellm-db-pre.sql.gz"
docker compose -f docker-compose.yml config -q
install -m 0644 docker-compose.yml litellm.config.yaml /opt/sip-litellm/
cd /opt/sip-litellm
# Recrear siempre: install cambia el inodo y el bind mount seguiría con el fichero anterior.
docker compose up -d --wait --force-recreate --no-deps litellm
docker inspect sip-litellm --format '{{range $k,$v := .NetworkSettings.Networks}}{{$k}}={{$v.IPAddress}} {{end}}'
exec python3 "$OLDPWD/cloud-setup.py"
