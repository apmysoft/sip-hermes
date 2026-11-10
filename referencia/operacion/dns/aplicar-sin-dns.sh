#!/bin/sh
# Quita el DNS externo a PERSONAL (hermes-webui) y CODING (hermes-coding, hermes-coding-api) (03-11).
# En Neo como usuario, desde ~/sip-inventario ya actualizado (usa docker y sudo -n).
#
# Hallazgo: el DNS interno de Docker (127.0.0.11) reenvía los nombres externos desde el propio host a
# 1.1.1.1, sin pasar por nftables: un canal de fuga por DNS. Con `dns:` = pasarela del bridge, el reenvío
# sale del contenedor hacia Neo y la cadena `input` lo descarta (sip-drop-in). Sin cambios en nftables.
#
# Recrea los tres contenedores (unos 30 s sin WebUI). Copia previa: /root/sip-agent-backups/<fecha>/dns/.
# Rollback: copiar de vuelta los dos compose y `docker compose ... up -d` en cada directorio.
set -eu
R=$HOME/sip-inventario/sip-config
H=$R/hermes
C=$HOME/sip-fase7-coding
B=/root/sip-agent-backups/$(date +%F)/dns

sudo -n install -d -m 0700 "$B"
[ -e "$B/coding-docker-compose.yml" ] || sudo -n cp -p "$C/docker-compose.yml" "$B/coding-docker-compose.yml"
[ -e "$B/hermes-docker-compose.yml" ] || git -C "$R/.." show 05ccf83:sip-config/hermes/docker-compose.yml |
  sudo -n tee "$B/hermes-docker-compose.yml" >/dev/null
cp "$R/coding/docker-compose.yml" "$C/docker-compose.yml"
(cd "$H" && docker compose -f docker-compose.yml -f compose.ssh-sandbox.yml config -q)
(cd "$C" && sudo -n docker compose config -q)

(cd "$H" && docker compose -f docker-compose.yml -f compose.ssh-sandbox.yml up -d hermes-webui)
(cd "$C" && sudo -n docker compose up -d)
for _ in $(seq 40); do
    n=$(docker inspect -f '{{if .State.Health}}{{.State.Health.Status}}{{end}}' hermes-webui hermes-coding hermes-coding-api | grep -c '^healthy$' || true)
    [ "$n" = 3 ] && break
    sleep 5
done

prueba() {  # contenedor uid nombre-interno
    docker exec -u "$2" "$1" /app/venv/bin/python -c '
import socket, sys, time
t = time.time()
try:
    socket.getaddrinfo("prueba-dns-sip.example.com", 443)
    sys.exit("FALLO: resuelve nombres externos")
except socket.gaierror:
    pass
print("externo bloqueado en %.1f s" % (time.time() - t), end="; ")
print("interno", sys.argv[1], "->", socket.gethostbyname(sys.argv[1]))' "$3"
}
fallo=0
for z in "hermes-webui 1000 vaultwarden" "hermes-coding 993 sip-litellm" "hermes-coding-api 993 sip-litellm"; do
    set -- $z
    if out=$(prueba "$1" "$2" "$3" 2>&1); then echo "$1: $out"; else echo "$1: $out"; fallo=1; fi
done

# Lo que sí necesitan: HALO por IP, LiteLLM desde CODING, WebUI con login.
docker exec hermes-webui /app/venv/bin/python -c '
import urllib.request; print("PERSONAL -> Ollama HALO:", urllib.request.urlopen("http://${HALO_TAILNET_IP}:11434/api/version", timeout=5).status)' || fallo=1
docker exec -u 993 hermes-coding /app/venv/bin/python -c '
import urllib.request; print("CODING -> LiteLLM:", urllib.request.urlopen("http://sip-litellm:4000/health/liveliness", timeout=5).status)' || fallo=1
for p in 8787 8788; do
    r=$(curl -s -m 5 -o /dev/null -w '%{http_code}' "http://${NEO_TAILNET_IP}:$p/api/settings")
    echo "WebUI :$p sin sesión -> $r (debe ser 401)"
    [ "$r" = 401 ] || fallo=1
done
docker inspect -f '{{.Name}} {{.State.Health.Status}} dns={{.HostConfig.Dns}}' hermes-webui hermes-coding hermes-coding-api
[ "$fallo" = 0 ] && echo "RESULTADO: OK" || { echo "RESULTADO: FALLO"; exit 1; }
