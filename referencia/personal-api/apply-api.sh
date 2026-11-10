#!/bin/sh
# Levanta hermes-personal-api en gw-personal (10.25.0.10:8642) y lo verifica. Root, en Neo, desde este
# directorio. Requiere apply-firewall.sh (red gw-personal) y la imagen hermes-webui-sip:para-lectura.
# Rollback: docker compose down (la clave /root/sip-personal-api.env puede quedarse).
set -eu
cd "$(dirname "$0")"
KEYF=/root/sip-personal-api.env
IMG=hermes-research:0.26.0-a2026.9.14  # solo para la sonda

docker network inspect gw-personal -f '{{.Internal}}' | grep -qx true
if [ ! -f "$KEYF" ]; then
  (umask 077; printf 'API_SERVER_KEY=%s\n' "$(openssl rand -hex 32)" > "$KEYF")
  echo "clave nueva en $KEYF"
fi
sh make-api-config.sh
docker compose config -q
docker compose up -d --force-recreate
for i in $(seq 60); do
  [ "$(docker inspect -f '{{.State.Health.Status}}' hermes-personal-api)" = healthy ] && break; sleep 3
done
echo "salud: $(docker inspect -f '{{.State.Health.Status}}' hermes-personal-api)"

# Herramientas efectivas de api_server y PARA en solo lectura
docker exec -w /opt/hermes-agent hermes-personal-api /app/venv/bin/python -c '
from hermes_cli.config import load_config
from hermes_cli.tools_config import _get_platform_tools
t = sorted(_get_platform_tools(load_config(), "api_server"))
print("api_server:", t); assert "terminal" not in t and "documentos" in t'
for d in 00_entrada 01_proyectos 02_areas 03_recursos 04_archivo; do
  docker exec hermes-personal-api sh -c "touch /para/$d/.sip-prueba 2>&1" | grep -q "Read-only file system" \
    || { echo "FALLO: /para/$d escribible" >&2; exit 1; }
done
echo "PARA: solo lectura en las cinco"

sonda() {  # $1 red; la clave entra por --env-file, no por la línea de órdenes
  docker run --rm --network "$1" --read-only --cap-drop ALL --user 65534:65534 --env-file "$KEYF" \
    --entrypoint python3 "$IMG" -c "
import os, sys, urllib.request, urllib.error
def get(key):
    r = urllib.request.Request('http://10.25.0.10:8642/v1/models')
    if key: r.add_header('Authorization', 'Bearer ' + key)
    try:
        return urllib.request.urlopen(r, timeout=5).status
    except urllib.error.HTTPError as e:
        return e.code
    except OSError:
        return 'cerrado'
res = (get(None), get('mala'), get(os.environ['API_SERVER_KEY']))
print('$1', 'sin clave / clave mala / clave buena:', res)
want = (401, 401, 200) if '$1' == 'gw-personal' else ('cerrado',) * 3
sys.exit(0 if res == want else 1)"
}
sonda gw-personal
sonda gw-coding
sonda gateway
echo "RESULTADO: OK"
