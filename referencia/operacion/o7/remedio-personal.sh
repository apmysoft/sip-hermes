#!/bin/bash
# Remedio del hallazgo O7 del 03-11-2026 (decisión del usuario del 03-11). Root en Neo, desde ~/sip-inventario.
#
# 1. Archiva el perfil `research` de PERSONAL (previo a la Fase 7) y redacta su clave.
# 2. Revoca sk-research (solo la usaba ese perfil; RESEARCH usa sk-research-cloud).
# 3. Rota sk-coding: clave nueva con los mismos límites, .env de CODING, reinicio de hermes-coding*,
#    y borrado de la vieja.
# 4. Saca sip-litellm de la red `sip`: PERSONAL deja de llegar al proxy (v2.4: sin proxy en PERSONAL).
# 5. Repite la búsqueda O7 de la auditoría, sin aviso.
#
# Ningún valor de clave se imprime. Copia previa en $B.
# Rollback:
#   - perfil: mv $V/_archivo/research-2026-11-03 $V/profiles/research (con la clave redactada: el perfil
#     ya no tiene acceso, a propósito);
#   - red: install -m 0644 $B/docker-compose.yml /opt/sip-litellm/ && (cd /opt/sip-litellm &&
#     docker compose up -d --wait --no-deps litellm);
#   - claves: las borradas no se recuperan; si CODING falla, crear otra con este mismo script (paso 3).
set -euo pipefail

R=$(cd "$(dirname "$0")/../.." && pwd)
B=/root/sip-agent-backups/2026-11-03/o7-remedio
V=${DOCKER_DATA}/docker_root/volumes/hermes_hermes-home/_data
C=${DOCKER_DATA}/docker_root/volumes/sip-coding_home/_data

install -d -m 0700 "$B"
[ -e "$B/docker-compose.yml" ] || cp -p /opt/sip-litellm/docker-compose.yml "$B/"
[ -e "$B/sip-litellm-keys.json" ] || cp -p /root/sip-litellm-keys.json "$B/"
[ -e "$B/coding.env" ] || cp -p "$C/.env" "$B/coding.env"
if [ -d "$V/profiles/research" ] && [ ! -e "$B/perfil-research.tar" ]; then
  tar -C "$V/profiles" --numeric-owner -cf "$B/perfil-research.tar" research
  chmod 0600 "$B/perfil-research.tar"
fi

# 1. Perfil research de PERSONAL
[ "$(cat "$V/active_profile")" != research ]
if [ -d "$V/profiles/research" ]; then
  mv "$V/profiles/research" "$V/_archivo/research-2026-11-03"
fi
sed -i 's/^LITELLM_API_KEY=.*/LITELLM_API_KEY=REDACTED/' "$V/_archivo/research-2026-11-03/.env"
echo "perfil research archivado en _archivo/research-2026-11-03 (clave redactada)"

# 2 y 3. Claves
python3 -I - "$C/.env" <<'EOF'
import json, os, sys, urllib.error, urllib.request
P = "http://${NEO_TAILNET_IP}:4000"
KEYS = "/root/sip-litellm-keys.json"
env = dict(l.rstrip("\n").split("=", 1) for l in open("/root/sip-litellm.env") if "=" in l and not l.startswith("#"))
master = env["LITELLM_MASTER_KEY"]

def call(path, key, body=None):
    req = urllib.request.Request(P + path, json.dumps(body).encode() if body else None,
                                 {"Authorization": "Bearer " + key, "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return r.status, json.load(r)
    except urllib.error.HTTPError as e:
        return e.code, {}

def write_keys(items):
    tmp = KEYS + ".tmp"
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as f:
        json.dump(items, f, indent=2)
    os.replace(tmp, KEYS)

items = json.load(open(KEYS))
zones = {i["zone"]: i["key"] for i in items}

if "research" in zones:
    s, _ = call("/key/delete", master, {"keys": [zones["research"]]})
    assert s == 200, f"key/delete research {s}"
    items = [i for i in items if i["zone"] != "research"]
    write_keys(items)
    old_research = zones["research"]
else:
    old_research = None
print("sk-research revocada")

envp = sys.argv[1]
lines = open(envp).read().splitlines(keepends=True)
actual = [l.split("=", 1)[1].strip() for l in lines if l.startswith("LITELLM_API_KEY=")]
assert len(actual) == 1, "LITELLM_API_KEY no única en el .env de CODING"
vieja = zones["coding"]
if actual[0] == vieja:
    s, d = call("/key/info?key=" + vieja, master)
    assert s == 200, f"key/info coding {s}"
    i = d["info"]
    s, d = call("/key/generate", master, {
        "key_alias": "sk-coding-20261103", "models": i["models"], "rpm_limit": i["rpm_limit"],
        "tpm_limit": i["tpm_limit"], "max_budget": i["max_budget"], "budget_duration": i["budget_duration"]})
    assert s == 200, f"key/generate {s}"
    nueva = d["key"]
    st = os.stat(envp)
    tmp = envp + ".tmp"
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as f:
        f.write("".join("LITELLM_API_KEY=" + nueva + "\n" if l.startswith("LITELLM_API_KEY=") else l
                        for l in lines))
    os.chown(tmp, st.st_uid, st.st_gid)
    os.replace(tmp, envp)
    for it in items:
        if it["zone"] == "coding":
            it["key"] = nueva
    write_keys(items + [{"zone": "coding-vieja", "key": vieja}])
    print("sk-coding nueva creada (alias sk-coding-20261103) y escrita en el .env de CODING")
else:
    print("el .env de CODING ya tiene otra clave: rotación ya hecha")

if old_research:
    s, _ = call("/v1/models", old_research)
    assert s in (400, 401, 403), f"sk-research vieja sigue viva: {s}"
    print("sk-research vieja ->", s)
EOF

docker restart hermes-coding hermes-coding-api >/dev/null
for c in hermes-coding hermes-coding-api; do
  for _ in $(seq 60); do
    [ "$(docker inspect -f '{{.State.Health.Status}}' "$c")" = healthy ] && break
    sleep 2
  done
  [ "$(docker inspect -f '{{.State.Health.Status}}' "$c")" = healthy ]
done
echo "hermes-coding y hermes-coding-api healthy"

# La clave nueva funciona desde CODING (leída del .env del propio contenedor)
docker exec -u 993 hermes-coding /app/venv/bin/python -c '
import json, urllib.request
k = [l.split("=", 1)[1].strip() for l in open("/home/hermeswebui/.hermes/.env") if l.startswith("LITELLM_API_KEY=")][0]
r = urllib.request.Request("http://sip-litellm:4000/v1/models", headers={"Authorization": "Bearer " + k})
print("CODING -> LiteLLM con la clave nueva:", sorted(m["id"] for m in json.load(urllib.request.urlopen(r, timeout=10))["data"]))'

# Borrar la vieja solo cuando la nueva funciona
python3 -I - <<'EOF'
import json, os, urllib.error, urllib.request
P = "http://${NEO_TAILNET_IP}:4000"
KEYS = "/root/sip-litellm-keys.json"
env = dict(l.rstrip("\n").split("=", 1) for l in open("/root/sip-litellm.env") if "=" in l and not l.startswith("#"))
items = json.load(open(KEYS))
vieja = [i["key"] for i in items if i["zone"] == "coding-vieja"]
def call(path, key, body=None):
    req = urllib.request.Request(P + path, json.dumps(body).encode() if body else None,
                                 {"Authorization": "Bearer " + key, "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return r.status
    except urllib.error.HTTPError as e:
        return e.code
if vieja:
    assert call("/key/delete", env["LITELLM_MASTER_KEY"], {"keys": vieja}) == 200, "key/delete coding vieja"
    s = call("/v1/models", vieja[0])
    assert s in (400, 401, 403), f"sk-coding vieja sigue viva: {s}"
    items = [i for i in items if i["zone"] != "coding-vieja"]
    fd = os.open(KEYS + ".tmp", os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as f:
        json.dump(items, f, indent=2)
    os.replace(KEYS + ".tmp", KEYS)
    print("sk-coding vieja borrada ->", s)
print("zonas en", KEYS, [i["zone"] for i in items])
EOF

# 4. LiteLLM fuera de la red sip
install -m 0644 "$R/litellm/docker-compose.yml" /opt/sip-litellm/docker-compose.yml
(cd /opt/sip-litellm && docker compose up -d --wait --no-deps litellm)
redes=$(docker inspect sip-litellm -f '{{range $k, $v := .NetworkSettings.Networks}}{{$k}} {{end}}')
echo "sip-litellm en: $redes"
case " $redes " in *" sip "*) echo "FALLO: sigue en sip"; exit 1 ;; esac

docker exec hermes-webui /app/venv/bin/python -c '
import socket
for h in ("sip-litellm", "172.29.0.4", "${NEO_TAILNET_IP}", "10.20.0.10", "10.23.0.10"):
    try:
        socket.create_connection((h, 4000), 3)
        raise SystemExit("FALLO: PERSONAL llega a " + h)
    except OSError as e:
        print("PERSONAL ->", h, type(e).__name__)'
docker exec -u 993 hermes-coding /app/venv/bin/python -c '
import urllib.request; print("CODING -> LiteLLM:", urllib.request.urlopen("http://sip-litellm:4000/health/liveliness", timeout=5).status)'
docker exec hermes-research /opt/hermes/.venv/bin/python -c '
import urllib.request; print("RESEARCH -> LiteLLM:", urllib.request.urlopen("http://10.20.0.10:4000/health/liveliness", timeout=5).status)'

# 5. O7 de nuevo
python3 -I /usr/local/sbin/sip-auditoria.py --sin-aviso | grep -A3 '^O7' || true
echo "RESULTADO: OK. Copia previa en $B"
