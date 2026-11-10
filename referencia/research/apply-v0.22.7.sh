#!/bin/sh
# RESEARCH a Hermes v0.22.7 (05-11). Root, en Neo, desde este directorio (sip-config/research del checkout).
# Imagen Dockerfile (agente v0.22.7 + agent-browser + yt-dlp), config.yaml y plugins (sip-navegador nuevo) al
# volumen, compose a ~usuario/sip-fase7-research. No toca firewall, redes ni filegate.
# La config migra a v52 en el primer arranque. Copia completa del volumen antes de nada.
# Rollback: sh $B/rollback.sh  (restaura volumen, compose e imagen anterior)
set -eu
cd "$(dirname "$0")"
R=/home/usuario/sip-fase7-research
V=sip-research_hermes-research-home
TAG=hermes-research:0.22.7-ab0.26.0-ytdlp2026.10.26
VIEJA=hermes-research:0.26.0-a2026.9.14-ytdlp2026.10.26
B=/root/sip-agent-backups/$(date +%F)/research-0.22.7
[ ! -e "$B" ] || { echo "ERROR: ya existe $B" >&2; exit 1; }
docker image inspect "$VIEJA" >/dev/null   # la vuelta atrás la necesita
install -d -m 700 "$B"
docker build -q -t "$TAG" . >/dev/null
docker run --rm --network none --entrypoint sh "$TAG" -c 'hermes --version >/tmp/v 2>&1; head -1 /tmp/v; agent-browser --version; PYTHONPATH=/opt/yt-dlp python3 -m yt_dlp --version'

cp -p "$R/docker-compose.yml" "$B/docker-compose.yml"
(cd "$R" && docker compose stop hermes-research)
docker run --rm --network none -v "$V:/s:ro" -v "$B:/b" busybox:1.36.1 tar -C /s -czf /b/home.tgz .
chmod 600 "$B/home.tgz"
cat > "$B/rollback.sh" <<EOF
#!/bin/sh
set -eu
cd $R && docker compose stop hermes-research
docker run --rm --network none -v $V:/d -v $B:/b:ro busybox:1.36.1 sh -c 'find /d -mindepth 1 -delete; tar -C /d -xzf /b/home.tgz'
install -o usuario -g usuario -m 644 $B/docker-compose.yml $R/docker-compose.yml
cd $R && docker compose up -d --force-recreate
EOF
echo "copia: $(du -h "$B/home.tgz" | cut -f1) en $B"

# Config y plugins al volumen (el filtro antiguo se retira: su gancho era de browser_navigate)
docker run --rm --network none -v "$V:/d" -v "$PWD/config.yaml:/c:ro" -v "$PWD/plugins:/p:ro" busybox:1.36.1 \
  sh -c 'cp /c /d/config.yaml; mkdir -p /d/plugins; cp -r /p/. /d/plugins/; rm -rf /d/plugins/sip-browser-guard
         find /d/plugins -name __pycache__ -exec rm -rf {} +
         chown -R 995:985 /d/config.yaml /d/plugins; chmod 600 /d/config.yaml'
install -o usuario -g usuario -m 644 docker-compose.yml "$R/docker-compose.yml"
(cd "$R" && docker compose config -q && docker compose up -d --force-recreate)

for i in $(seq 40); do
  docker exec hermes-research python3 -c 'import urllib.request;urllib.request.urlopen("http://10.22.0.10:8642/health",timeout=3)' 2>/dev/null && break; sleep 3
done
docker exec hermes-research sh -c 'hermes --version >/tmp/v 2>&1; head -1 /tmp/v; grep -E "^_config_version" /opt/data/config.yaml'
docker exec -w /opt/hermes hermes-research python3 -W ignore -c '
import sys; sys.path.insert(0,"/opt/hermes")
from hermes_cli.plugins import discover_plugins
discover_plugins()
from hermes_cli.config import load_config
from model_tools import get_tool_definitions
cfg=load_config()
for plat in ("cli","api_server"):
    n=sorted(x["function"]["name"] for x in get_tool_definitions(enabled_toolsets=cfg["platform_toolsets"][plat],quiet_mode=True))
    print(plat, n)
    assert "navegador_abrir" in n and "entrada_guardar" in n and "medios_descargar" in n
    assert not [t for t in n if t in ("terminal","browser_exec","write_file","read_file","execute_code","tool_search")]'
code=$(docker exec sip-gateway python3 -c 'import urllib.request;print(urllib.request.urlopen("http://10.22.0.10:8642/health",timeout=5).status)' 2>/dev/null || echo fallo)
echo "sip-gateway -> research /health: $code"
[ "$code" = 200 ] && echo "RESULTADO: OK (rollback: sh $B/rollback.sh)" || { echo "RESULTADO: REVISAR (rollback: sh $B/rollback.sh)" >&2; exit 1; }
