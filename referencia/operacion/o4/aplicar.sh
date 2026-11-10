#!/bin/sh
# Arreglo de O4 + límites de logs (03-11), en Neo como usuario (usa docker y sudo -n). Requisito: el usuario
# ya ejecutó fijar-password-webui.sh personal y coding (si falta un password_hash, no se toca nada).
# Recrea hermes-webui y perm-guardian (proyecto hermes) y hermes-coding y hermes-coding-api (sip-coding)
# sin HERMES_WEBUI_PASSWORD y con logs json-file 10m x 5.
# Copia previa: /root/sip-agent-backups/<fecha>/o4/. Rollback: copiar de vuelta los dos compose y
# `docker compose ... up -d` en cada directorio; la variable vuelve y manda sobre password_hash.
# Uso: sh aplicar.sh <dir con los compose nuevos: hermes-docker-compose.yml y coding-docker-compose.yml>
set -eu
N=$(cd "$1" && pwd)
H=$HOME/sip-inventario/sip-config/hermes
C=$HOME/sip-fase7-coding
B=/root/sip-agent-backups/$(date +%F)/o4

for z in "hermes-webui 1000" "hermes-coding 993"; do
    set -- $z
    docker exec -u "$2" -w /app "$1" /app/venv/bin/python -c '
import sys; sys.path.insert(0, "/app")
from api.config import load_settings
sys.exit(0 if load_settings().get("password_hash") else 1)' 2>/dev/null ||
        { echo "$1 sin password_hash: ejecuta antes fijar-password-webui.sh"; exit 1; }
    echo "$1: password_hash presente"
done

sudo -n install -d -m 0700 "$B"
sudo -n cp -p "$H/docker-compose.yml" "$B/hermes-docker-compose.yml"
sudo -n cp -p "$C/docker-compose.yml" "$B/coding-docker-compose.yml"
cp "$N/hermes-docker-compose.yml" "$H/docker-compose.yml"
cp "$N/coding-docker-compose.yml" "$C/docker-compose.yml"
(cd "$H" && docker compose -f docker-compose.yml -f compose.ssh-sandbox.yml config -q)
(cd "$C" && sudo -n docker compose config -q)  # env_file en /root

(cd "$H" && docker compose -f docker-compose.yml -f compose.ssh-sandbox.yml up -d)
(cd "$C" && sudo -n docker compose up -d)
for _ in $(seq 40); do
    n=$(docker inspect -f '{{if .State.Health}}{{.State.Health.Status}}{{end}}' hermes-webui hermes-coding hermes-coding-api | grep -c '^healthy$' || true)
    [ "$n" = 3 ] && break
    sleep 5
done
fallo=0
for c in hermes-webui hermes-coding hermes-coding-api hermes-perm-guardian; do
    env=$(docker inspect -f '{{range .Config.Env}}{{println .}}{{end}}' "$c" | grep -c '^HERMES_WEBUI_PASSWORD=' || true)
    log=$(docker inspect -f '{{.HostConfig.LogConfig.Type}} {{index .HostConfig.LogConfig.Config "max-size"}}x{{index .HostConfig.LogConfig.Config "max-file"}}' "$c")
    st=$(docker inspect -f '{{.State.Status}} {{if .State.Health}}{{.State.Health.Status}}{{end}}' "$c")
    echo "$c: $st | logs $log | variable en el entorno: $env"
    [ "$env" = 0 ] || fallo=1
done
for p in 8787 8788; do
    r=$(curl -s -m 5 -o /dev/null -w '%{http_code}' "http://${NEO_TAILNET_IP}:$p/api/settings")
    echo "WebUI :$p sin sesión → $r (debe ser 401)"
    [ "$r" = 401 ] || fallo=1
done
[ "$fallo" = 0 ] && echo "RESULTADO: OK (falta que el usuario entre con la contraseña nueva)" || { echo "RESULTADO: FALLO"; exit 1; }
