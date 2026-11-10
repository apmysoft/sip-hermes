#!/bin/sh
# PERSONAL (hermes-webui + hermes-personal-api) a Hermes v0.22.7 / WebUI v0.52.544 (05-11). Root, en Neo,
# desde el checkout ~usuario/sip-inventario YA ACTUALIZADO (git pull): los compose de la WebUI y de la API
# corren desde ese checkout. Probado antes con copia del volumen (candidato-v0.22.7/probar-personal.sh).
# Pasos: copia del volumen con los dos parados -> endurecer + migrar perfiles -> WebUI -> regenerar
# config.api.yaml -> API (HERMES_HOME = subruta profiles/personal) -> verificar.
# PRIVACIDAD: no muestra contenido (ni respuestas del modelo, ni nombres de sesiones o documentos).
# Rollback: sh $B/rollback.sh
set -eu
G=/home/usuario/sip-inventario/sip-config
W=$G/hermes
P=$G/personal-api
V=hermes_hermes-home
TAG=hermes-webui-sip:v0.52.544-a0.22.7
B=/root/sip-agent-backups/$(date +%F)/personal-0.22.7
CW="docker compose -f docker-compose.yml -f compose.ssh-sandbox.yml -f compose.para-ro.yml"
[ ! -e "$B" ] || { echo "ERROR: ya existe $B" >&2; exit 1; }
docker image inspect "$TAG" hermes-webui-sip:para-lectura >/dev/null
grep -q "image: $TAG" "$W/compose.para-ro.yml" && grep -q "image: $TAG" "$P/docker-compose.yml" \
  || { echo "ERROR: el checkout no tiene los compose de 0.22.7 (¿git pull?)" >&2; exit 1; }
(cd "$W" && $CW config -q) && (cd "$P" && docker compose config -q)
install -d -m 700 "$B"
cp -p "$P/config.api.yaml" "$B/config.api.yaml"
# Compose anteriores (0.21.3) desde git: el padre del último commit que cambió cada fichero
R=/home/usuario/sip-inventario
for f in sip-config/hermes/compose.para-ro.yml:compose.para-ro.yml sip-config/personal-api/docker-compose.yml:docker-compose.api.yml; do
  c=$(git -c safe.directory=$R -C $R log -1 --format=%H -- "${f%%:*}")
  git -c safe.directory=$R -C $R show "$c~1:${f%%:*}" > "$B/${f##*:}"
  ! grep -q "$TAG" "$B/${f##*:}" || { echo "ERROR: la copia anterior de ${f%%:*} ya es de 0.22.7" >&2; exit 1; }
done

docker stop hermes-personal-api hermes-webui >/dev/null
docker run --rm --network none -v "$V:/s:ro" -v "$B:/b" busybox:1.36.1 tar -C /s -czf /b/home.tgz .
chmod 600 "$B/home.tgz"
cat > "$B/rollback.sh" <<EOF
#!/bin/sh
# Vuelve a 0.21.3 sin tocar el checkout: volumen de antes y los compose/config.api anteriores guardados aquí.
set -eu
docker stop hermes-personal-api hermes-webui || true
docker run --rm --network none -v $V:/d -v $B:/b:ro busybox:1.36.1 sh -c 'find /d -mindepth 1 -delete; tar -C /d -xzf /b/home.tgz'
cd $W && docker compose --project-directory $W -f docker-compose.yml -f compose.ssh-sandbox.yml -f $B/compose.para-ro.yml up -d --force-recreate --no-deps hermes-webui
cd $B && docker compose --project-directory $B -f $B/docker-compose.api.yml up -d --force-recreate hermes-personal-api
echo "Vuelta atrás aplicada. El checkout sigue con los compose de 0.22.7: no relanzar desde él sin revisarlos."
EOF
echo "copia: $(du -h "$B/home.tgz" | cut -f1) en $B"

# Endurecer y migrar perfiles (como 1000, sin red)
docker run --rm --network none -v "$V:/h" -v "$G/hermes/endurecer-config.py:/e.py:ro" --user 1000:1000 \
  -e HOME=/tmp -e HERMES_DISABLE_LAZY_INSTALLS=1 --entrypoint sh "$TAG" -c '
  for s in "" /profiles/personal /profiles/sandbox /profiles/system; do
    [ -f /h$s/config.yaml ] || continue
    /app/venv/bin/python /e.py /h$s/config.yaml >/dev/null && HERMES_HOME=/h$s /app/venv/bin/hermes config migrate </dev/null >/dev/null 2>&1
    echo "  ${s:-raíz}: rc=$? $(grep -E "^_config_version" /h$s/config.yaml)"
  done'

(cd "$W" && $CW up -d --force-recreate --no-deps hermes-webui)
ok=0
for i in $(seq 60); do
  docker exec hermes-webui curl -sf -o /dev/null http://127.0.0.1:8787/health 2>/dev/null && { ok=1; break; }; sleep 3
done
[ $ok = 1 ] || { echo "RESULTADO: FALLO la WebUI no responde (rollback: sh $B/rollback.sh)" >&2; exit 1; }
docker logs hermes-webui 2>&1 | grep -E "reusing|critical imports|^!!" | cut -c1-140
for p in /api/sessions /; do
  echo "  WebUI sin sesión $p -> $(docker exec hermes-webui curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:8787$p)"
done
docker exec -u 1000 hermes-webui sh -c 'touch /para/00_entrada/.sip-ro-test 2>&1 | grep -q "Read-only" && echo "  PARA: solo lectura (EROFS)" || echo "  PARA: ESCRIBIBLE (MAL)"'

sh "$P/make-api-config.sh" >/dev/null
grep -q '^_config_version: 52' "$P/config.api.yaml" && grep -q -- '- connections' "$P/config.api.yaml"
(cd "$P" && docker compose up -d --force-recreate hermes-personal-api)
for i in $(seq 40); do
  [ "$(docker inspect -f '{{.State.Health.Status}}' hermes-personal-api 2>/dev/null)" = healthy ] && break
  [ "$(docker inspect -f '{{.State.Status}}' hermes-personal-api)" = running ] || { docker logs --tail 20 hermes-personal-api 2>&1 | cut -c1-200; break; }
  sleep 3
done
docker exec -w /opt/hermes hermes-personal-api /app/venv/bin/python -W ignore -c '
from hermes_cli.plugins import discover_plugins
discover_plugins()
from hermes_cli.config import load_config
from hermes_cli.tools_config import _get_platform_tools
from model_tools import get_tool_definitions
c = load_config()
ts = sorted(_get_platform_tools(c, "api_server")); print("  api_server", ts)
assert ts == ["documentos", "file", "memory", "session_search", "skills", "todo", "transcribir"]
n = [x["function"]["name"] for x in get_tool_definitions(enabled_toolsets=ts, quiet_mode=True)]
assert "audio_transcribir" in n and not [t for t in n if t in ("terminal","browser_exec","execute_code","manage_connections")]
for k in (("nous","guest"),("auth","adopt_external_logins"),("tools","connectors","enabled"),("security","allow_lazy_installs")):
    d = c
    for x in k: d = d.get(x, {})
    assert d is False, k
print("  herramientas y endurecimiento OK")'
docker exec sip-gateway python3 -c '
import urllib.request,json,os,re
print("  sip-gateway -> personal /health", urllib.request.urlopen("http://10.25.0.10:8642/health",timeout=5).status)
body=json.dumps({"model":"hermes-agent","messages":[{"role":"user","content":"Responde solo con la palabra OK, sin usar herramientas."}]}).encode()
r=urllib.request.Request("http://10.25.0.10:8642/v1/chat/completions",data=body,headers={"Authorization":"Bearer "+os.environ["PERSONAL_API_KEY"],"Content-Type":"application/json"})
txt=json.load(urllib.request.urlopen(r,timeout=300))["choices"][0]["message"]["content"]
ok=re.fullmatch(r"\W*ok\W*", txt.strip(), re.I) is not None
print("  turno por sip-gateway:", "OK" if ok else "respuesta distinta de OK (no se muestra)")
raise SystemExit(0 if ok else 1)'
echo "RESULTADO: OK (rollback: sh $B/rollback.sh)"
