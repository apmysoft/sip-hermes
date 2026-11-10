#!/bin/sh
# CODING a Hermes v0.22.7 / WebUI v0.52.544 (05-11). Root, en Neo, desde sip-config/coding de una copia del
# checkout (necesita ../hermes/endurecer-config.py). Despliega en ~usuario/sip-fase7-coding.
# Imagen: hermes-webui-sip:cand-v0.52.544-a0.22.7 (sip-config/hermes/candidato-v0.22.7), probada con copia
# del volumen (probar-coding.sh, probar-migracion.sh). Pasos: copia del volumen con los dos contenedores
# parados -> endurecer + migrar config (v44 -> v52) -> WebUI -> regenerar config.api.yaml -> API -> verificar.
# El volumen incluye las claves SSH del worker: la copia queda en $B (root 0700/0600).
# Rollback: sh $B/rollback.sh
set -eu
cd "$(dirname "$0")"
R=/home/usuario/sip-fase7-coding
V=sip-coding_home
CAND=hermes-webui-sip:cand-v0.52.544-a0.22.7
TAG=hermes-webui-sip:v0.52.544-a0.22.7
VIEJA=hermes-webui-sip:ssh-sandbox-test
B=/root/sip-agent-backups/$(date +%F)/coding-0.22.7
[ ! -e "$B" ] || { echo "ERROR: ya existe $B" >&2; exit 1; }
docker image inspect "$VIEJA" >/dev/null
docker tag "$CAND" "$TAG"
install -d -m 700 "$B"
cp -p "$R/docker-compose.yml" "$R/config.api.yaml" "$B/"
cp -p ../hermes/endurecer-config.py "$B/endurecer-config.py"

(cd "$R" && docker compose stop hermes-coding-api hermes-coding)
docker run --rm --network none -v "$V:/s:ro" -v "$B:/b" busybox:1.36.1 tar -C /s -czf /b/home.tgz .
chmod 600 "$B/home.tgz"
cat > "$B/rollback.sh" <<EOF
#!/bin/sh
set -eu
cd $R && docker compose stop hermes-coding-api hermes-coding
docker run --rm --network none -v $V:/d -v $B:/b:ro busybox:1.36.1 sh -c 'find /d -mindepth 1 -delete; tar -C /d -xzf /b/home.tgz'
install -o usuario -g usuario -m 664 $B/docker-compose.yml $R/docker-compose.yml
install -o root -g root -m 644 $B/config.api.yaml $R/config.api.yaml
cd $R && docker compose up -d --force-recreate
EOF
echo "copia: $(du -h "$B/home.tgz" | cut -f1) en $B"

# Endurecer y migrar la config del perfil (como 993, sin red)
docker run --rm --network none -v "$V:/h" -v "$B/endurecer-config.py:/e.py:ro" --user 993:983 \
  -e HOME=/tmp -e HERMES_HOME=/h -e HERMES_DISABLE_LAZY_INSTALLS=1 --entrypoint sh "$TAG" -c \
  '/app/venv/bin/python /e.py /h/config.yaml && /app/venv/bin/hermes config migrate </dev/null >/tmp/m.log 2>&1; echo "migrate rc=$?"; grep -E "^_config_version" /h/config.yaml'

install -o usuario -g usuario -m 664 docker-compose.yml "$R/docker-compose.yml"
(cd "$R" && docker compose config -q && docker compose up -d --force-recreate --no-deps hermes-coding)
ok=0
for i in $(seq 60); do
  docker exec hermes-coding curl -sf -o /dev/null http://127.0.0.1:8787/health 2>/dev/null && { ok=1; break; }; sleep 3
done
[ $ok = 1 ] || { echo "RESULTADO: FALLO la WebUI no responde (rollback: sh $B/rollback.sh)" >&2; exit 1; }
docker logs hermes-coding 2>&1 | grep -E "reusing|critical imports|!!" | cut -c1-140

# config.api.yaml desde la config migrada (make-api-config.sh exige la lista exacta de api_server)
sh "$R/make-api-config.sh" >/dev/null
grep -q '^_config_version: 52' "$R/config.api.yaml" && grep -q 'connections' "$R/config.api.yaml" \
  && grep -A2 'disabled_toolsets' "$R/config.api.yaml" | head -3
(cd "$R" && docker compose up -d --force-recreate --no-deps hermes-coding-api)
for i in $(seq 40); do
  [ "$(docker inspect -f '{{.State.Health.Status}}' hermes-coding-api 2>/dev/null)" = healthy ] && break; sleep 3
done

docker exec -u 993 -e HOME=/home/hermeswebui -w /opt/hermes-agent hermes-coding /app/venv/bin/python -W ignore -c '
from hermes_cli.config import load_config
from hermes_cli.tools_config import _get_platform_tools
c = load_config()
for p in ("cli", "api_server"):
    t = sorted(_get_platform_tools(c, p)); print(p, t)
    assert "connections" not in t
assert sorted(_get_platform_tools(c, "api_server")) == sorted(["terminal", "file", "todo", "memory", "session_search", "skills"])
for k in (("nous","guest"),("auth","adopt_external_logins"),("tools","connectors","enabled"),("security","allow_lazy_installs")):
    d = c
    for x in k: d = d.get(x, {})
    assert d is False, k
print("endurecimiento OK")'
docker exec -u 993 -e HOME=/home/hermeswebui hermes-coding sh -c 'HERMES_HOME=/home/hermeswebui/.hermes /app/venv/bin/hermes plugins list 2>&1 | grep -E "^│ sip-" | cut -c1-40'
code=$(docker exec sip-gateway python3 -c 'import urllib.request;print(urllib.request.urlopen("http://10.24.0.10:8642/health",timeout=5).status)' 2>/dev/null || echo fallo)
echo "sip-gateway -> coding /health: $code; api: $(docker inspect -f '{{.State.Health.Status}}' hermes-coding-api)"
[ "$code" = 200 ] && echo "RESULTADO: OK (rollback: sh $B/rollback.sh)" || { echo "RESULTADO: REVISAR (rollback: sh $B/rollback.sh)" >&2; exit 1; }
