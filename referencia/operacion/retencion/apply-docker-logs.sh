#!/bin/sh
# Logs de Docker acotados (M.12, 03-11) en el resto de SIP: recrea cada proyecto con su compose nuevo
# (logging json-file 10m x 5). PERSONAL y CODING ya se hicieron con operacion/o4/aplicar.sh.
# En Neo como usuario (sudo -n). Uso: sh apply-docker-logs.sh <dir con runner.yml research.yml gateway.yml litellm.yml>
# Antes de recrear: archiva el log actual de cada contenedor (se pierde al recrear) y copia el compose en
# /root/sip-agent-backups/<fecha>/docker-logs/. Rollback: copiar el compose de vuelta y `docker compose up -d`.
# Se para en el primer proyecto que falle.
set -eu
N=$(cd "$1" && pwd)
B=/root/sip-agent-backups/$(date +%F)/docker-logs
sudo -n install -d -m 0700 "$B"

proyecto() {  # $1 nombre, $2 compose desplegado, $3.. contenedores
    nombre=$1; destino=$2; shift 2
    echo "== $nombre"
    for c in "$@"; do
        lp=$(docker inspect -f '{{.LogPath}}' "$c")
        sudo -n sh -c "gzip -c '$lp' > '$B/$c.json.log.gz'" && echo "  log de $c archivado"
    done
    sudo -n cp -p "$destino" "$B/$nombre-docker-compose.yml"
    sudo -n install -m 0644 -o "$(stat -c %U "$destino")" -g "$(stat -c %G "$destino")" "$N/$nombre.yml" "$destino"
    d=$(dirname "$destino")
    (cd "$d" && sudo -n docker compose config -q)
    (cd "$d" && sudo -n docker compose up -d 2>&1 | grep -vE 'level=warning' | sed 's/^/  /')
    for _ in $(seq 36); do
        ok=1
        for c in "$@"; do
            s=$(docker inspect -f '{{.State.Status}}{{if .State.Health}} {{.State.Health.Status}}{{end}}' "$c")
            case "$s" in "running healthy"|running) ;; *) ok=0 ;; esac
        done
        [ "$ok" = 1 ] && break
        sleep 5
    done
    for c in "$@"; do
        echo "  $c: $(docker inspect -f '{{.State.Status}}{{if .State.Health}} {{.State.Health.Status}}{{end}} | logs {{.HostConfig.LogConfig.Type}} {{index .HostConfig.LogConfig.Config "max-size"}}x{{index .HostConfig.LogConfig.Config "max-file"}}' "$c")"
        [ "$(docker inspect -f '{{index .HostConfig.LogConfig.Config "max-size"}}' "$c")" = 10m ] || { echo "FALLO: $c sin límite"; exit 1; }
    done
    [ "$ok" = 1 ] || { echo "FALLO: $nombre no arranca sano"; exit 1; }
}

proyecto runner "$HOME/sip-inventario/sip-config/sandbox-runner/docker-compose.yml" hermes-sandbox-runner
proyecto research "$HOME/sip-fase7-research/docker-compose.yml" hermes-research
proyecto gateway "$HOME/sip-fase7-gateway/docker-compose.yml" sip-gateway
proyecto litellm /opt/sip-litellm/docker-compose.yml sip-litellm-db sip-litellm
r=$(curl -s -m 5 -o /dev/null -w '%{http_code}' http://${NEO_TAILNET_IP}:4000/health/liveliness)
echo "LiteLLM liveliness → $r"
[ "$r" = 200 ] || { echo "RESULTADO: FALLO"; exit 1; }
echo "RESULTADO: OK"
