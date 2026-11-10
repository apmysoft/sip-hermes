#!/bin/sh
# Avisos de tareas en segundo plano PERSONAL -> sip-gateway (05-11). Root, en Neo, desde el checkout
# ~usuario/sip-inventario YA ACTUALIZADO (git pull). Ver README.md de esta carpeta.
# Pasos: copia previa -> buzón /var/lib/sip-avisos/personal -> plugin sip-transcribir 1.1 (reinicia la WebUI)
# -> API de PERSONAL con el buzón -> sip-gateway con el buzón -> verificar.
# Ejecutar sin turnos en curso en sip-gateway (recrearlo corta la espera de una respuesta).
# Rollback: sh $B/rollback.sh
set -eu
R=/home/usuario/sip-inventario
G=$R/sip-config
GW=/home/usuario/sip-fase7-gateway
H=${DOCKER_DATA}/docker_root/volumes/hermes_hermes-home/_data
B=/root/sip-agent-backups/$(date +%F)/avisos
[ ! -e "$B" ] || { echo "ERROR: ya existe $B" >&2; exit 1; }
grep -q SIP_AVISOS_DIR "$G/personal-api/docker-compose.yml" && grep -q sip-avisos "$G/gateway/docker-compose.yml" \
  || { echo "ERROR: el checkout no tiene los compose con el buzón (¿git pull?)" >&2; exit 1; }
grep -q 'version: 1.1.0' "$G/hermes/plugins/sip-transcribir/plugin.yaml"

install -d -m 700 "$B"
cp -p "$GW/docker-compose.yml" "$GW/sip_gateway.py" "$B/"
tar -C "$H" -czf "$B/plugins-transcribir.tgz" profiles/personal/plugins/sip-transcribir plugins/sip-transcribir
# Compose anterior de la API desde git: el padre del último commit que cambió el fichero
f=sip-config/personal-api/docker-compose.yml
c=$(git -c safe.directory=$R -C $R log -1 --format=%H -- $f)
git -c safe.directory=$R -C $R show "$c~1:$f" > "$B/docker-compose.api.yml"
! grep -q SIP_AVISOS_DIR "$B/docker-compose.api.yml" || { echo "ERROR: no encuentro el compose anterior de la API" >&2; exit 1; }
cp "$G/personal-api/config.api.yaml" "$B/" 2>/dev/null || true
cat > "$B/rollback.sh" <<EOF
#!/bin/sh
# Vuelve a la situación anterior al buzón. El checkout sigue con los ficheros nuevos.
set -eu
cp -p $B/docker-compose.yml $B/sip_gateway.py $GW/
(cd $GW && docker compose up -d --force-recreate)
tar -C $H -xzf $B/plugins-transcribir.tgz
cp $B/docker-compose.api.yml $G/personal-api/docker-compose.api.rollback.yml
(cd $G/personal-api && docker compose -f docker-compose.api.rollback.yml up -d --force-recreate hermes-personal-api)
docker restart hermes-webui
rm -rf /var/lib/sip-avisos
echo "Vuelta atrás aplicada (la API corre con docker-compose.api.rollback.yml; bórralo al volver al checkout)."
EOF
echo "copia en $B"

# Buzón: lo crea y borra el gateway (978, dueño); la API (1000:1000) escribe por el grupo. Sticky: nadie más borra.
install -d -m 755 /var/lib/sip-avisos
install -d -o 978 -g 1000 -m 1770 /var/lib/sip-avisos/personal
(cd "$G/personal-api" && docker compose config -q) && (cd "$G/gateway" && docker compose config -q)

# Plugin (perfiles personal y default de la WebUI; mismo volumen que la API)
(cd "$G/hermes/plugins" && sh apply-transcribir.sh)

(cd "$G/personal-api" && docker compose up -d --force-recreate hermes-personal-api)
for i in $(seq 40); do
  [ "$(docker inspect -f '{{.State.Health.Status}}' hermes-personal-api)" = healthy ] && break; sleep 3
done

install -o usuario -g usuario -m 644 "$G/gateway/docker-compose.yml" "$G/gateway/sip_gateway.py" "$GW/"
(cd "$GW" && docker compose up -d --force-recreate)

echo "== verificación"
docker exec -w /opt/hermes hermes-personal-api /app/venv/bin/python -W ignore -c '
from hermes_cli.plugins import discover_plugins
discover_plugins()
from hermes_cli.config import load_config
from hermes_cli.tools_config import _get_platform_tools
from model_tools import get_tool_definitions
ts = sorted(_get_platform_tools(load_config(), "api_server"))
n = [x["function"]["name"] for x in get_tool_definitions(enabled_toolsets=ts, quiet_mode=True)]
assert "audio_transcribir" in n and "tarea_resultado" in n, n
print("  API: audio_transcribir y tarea_resultado presentes;", len(n), "herramientas")'
docker exec hermes-personal-api sh -c 'test "$SIP_AVISOS_DIR" = /avisos && touch /avisos/.p && rm /avisos/.p && echo "  API: escribe en el buzón"'
docker exec hermes-webui sh -c 'test ! -e /avisos && test -z "${SIP_AVISOS_DIR:-}" && echo "  WebUI: sin buzón (correcto)"'
# Un aviso con formato incorrecto: el gateway debe borrarlo y registrarlo como descartado
docker exec hermes-personal-api sh -c 'echo "{\"prueba\": 1}" > /avisos/000000000000.json'
ok=0
for i in $(seq 15); do
  [ ! -e /var/lib/sip-avisos/personal/000000000000.json ] && { ok=1; break; }; sleep 3
done
docker logs --since 2m sip-gateway 2>&1 | grep -E "arrancado|aviso" | cut -c1-120
[ $ok = 1 ] && echo "  gateway: lee y vacía el buzón" || { echo "RESULTADO: FALLO el gateway no vacía el buzón" >&2; exit 1; }
echo "RESULTADO: OK (rollback: sh $B/rollback.sh)"
