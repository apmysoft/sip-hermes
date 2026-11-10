#!/bin/sh
# Arranca sip-gateway (root, en Neo), con docker-compose.yml y sip_gateway.py junto al script.
# Requiere apply-firewall.sh, research/apply-api.sh, coding/, personal-api/, /root/sip-telegram.env y las claves de
# las APIs de zona, que se copian con nombre propio a /root/sip-gateway-zones.env.
# Rollback: docker compose down -v (borra solo el estado del gateway: offset y zona recordada).
set -eu
cd "$(dirname "$0")"
for f in /root/sip-telegram.env /root/sip-research-api.env /root/sip-coding-api.env /root/sip-personal-api.env; do
  [ -f "$f" ] || { echo "ERROR: falta $f" >&2; exit 1; }
done
(umask 077
 sed -n 's/^API_SERVER_KEY=/RESEARCH_API_KEY=/p' /root/sip-research-api.env > /root/sip-gateway-zones.env
 sed -n 's/^API_SERVER_KEY=/CODING_API_KEY=/p' /root/sip-coding-api.env >> /root/sip-gateway-zones.env
 sed -n 's/^API_SERVER_KEY=/PERSONAL_API_KEY=/p' /root/sip-personal-api.env >> /root/sip-gateway-zones.env)
[ "$(grep -c '_API_KEY=.' /root/sip-gateway-zones.env)" = 3 ] || { echo "ERROR: claves de zona incompletas" >&2; exit 1; }
docker compose config -q
docker compose up -d --no-start
docker run --rm --network none -v sip-gateway_state:/d busybox:1.36.1 sh -c 'chown 978:978 /d; chmod 700 /d'
docker compose up -d --force-recreate
sleep 5
docker logs sip-gateway 2>&1 | tail -3
docker inspect sip-gateway --format 'estado={{.State.Status}} reinicios={{.RestartCount}}'
