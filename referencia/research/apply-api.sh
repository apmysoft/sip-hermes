#!/bin/sh
# Fase 7: expone la API de RESEARCH en gw-research (10.22.0.10:8642) para sip-gateway. Root, en Neo,
# con docker-compose.yml y config.yaml junto al script. Requiere las redes de gateway/apply-firewall.sh.
# Rollback: copiar de $B docker-compose.yml y config.yaml (este al volumen, como abajo) y
#   docker compose up -d --force-recreate; la clave /root/sip-research-api.env puede quedarse.
set -eu
cd "$(dirname "$0")"
B=/root/sip-agent-backups/$(date +%F)/fase7-research-$(date +%H%M%S)
IMG=hermes-research:0.26.0-a2026.9.14
V=sip-research_hermes-research-home
KEYF=/root/sip-research-api.env

install -d -m 700 "$B"
docker exec hermes-research cat /opt/data/config.yaml > "$B/config.yaml"
D=$(docker inspect hermes-research --format '{{index .Config.Labels "com.docker.compose.project.working_dir"}}')
cp -p "$D/docker-compose.yml" "$B/docker-compose.yml"

if [ ! -f "$KEYF" ]; then
  (umask 077; printf 'API_SERVER_KEY=%s\n' "$(openssl rand -hex 32)" > "$KEYF")
  echo "clave nueva en $KEYF"
fi

docker compose config -q
docker run --rm --network none -v "$V:/d" -v "$PWD/config.yaml:/c:ro" busybox:1.36.1 \
  sh -c 'cp /c /d/config.yaml; chown 995:985 /d/config.yaml; chmod 600 /d/config.yaml'
docker compose up -d --force-recreate

# Herramientas de la plataforma api_server: deben ser exactamente las de cli.
docker exec -w /opt/hermes hermes-research /opt/hermes/.venv/bin/python -c '
from hermes_cli.config import load_config
from hermes_cli.tools_config import _get_platform_tools
t = sorted(_get_platform_tools(load_config(), "api_server"))
print("api_server:", t); assert t == ["browser", "entrada"]'

sonda() {  # $1 red; la clave entra por --env-file, no por la línea de órdenes
  docker run --rm --network "$1" --read-only --cap-drop ALL --user 65534:65534 --env-file "$KEYF" \
    --entrypoint python3 "$IMG" -c "
import os, sys, time, urllib.request, urllib.error
def get(key):
    r = urllib.request.Request('http://10.22.0.10:8642/v1/models')
    if key: r.add_header('Authorization', 'Bearer ' + key)
    try:
        return urllib.request.urlopen(r, timeout=5).status
    except urllib.error.HTTPError as e:
        return e.code
    except OSError:
        return 'cerrado'
NET = '$1'
for _ in range(30):
    if get(None) != 'cerrado' or NET != 'gw-research': break
    time.sleep(2)
res = (get(None), get('mala'), get(os.environ['API_SERVER_KEY']))
print(NET, 'sin clave / clave mala / clave buena:', res)
want = (401, 401, 200) if NET == 'gw-research' else ('cerrado',) * 3
sys.exit(0 if res == want else 1)"
}
sonda gw-research
sonda research
echo "RESULTADO: OK. Copia previa en $B"
