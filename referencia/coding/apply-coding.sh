#!/bin/sh
# Crea la zona CODING (root, en Neo) copiando el perfil coding de hermes-webui a un volumen propio.
# Con docker-compose.yml junto al script. Requiere apply-firewall.sh de este directorio y LiteLLM en la
# red coding. No toca hermes-webui: su perfil coding queda como estaba.
# Rollback: docker compose down -v; setfacl -x u:993 en _wol, requests y results.
set -eu
cd "$(dirname "$0")"
B=/root/sip-agent-backups/$(date +%F)/fase7-coding
SRC=hermes_hermes-home
DST=sip-coding_home
W=${DOCKER_DATA}/hermes/workspace/_wol
PWF=/root/sip-coding-webui.env

docker inspect sip-litellm --format '{{(index .NetworkSettings.Networks "coding").IPAddress}}' | grep -qx 10.23.0.10
install -d -m 700 "$B"
docker run --rm --network none -v "$SRC:/s:ro" -v "$B:/b" busybox:1.36.1 \
  tar czf /b/perfil-coding-origen.tgz -C /s profiles/coding

if [ ! -f "$PWF" ]; then
  (umask 077; printf 'HERMES_WEBUI_PASSWORD=%s\n' "$(openssl rand -base64 24 | tr -d '/+=')" > "$PWF")
  echo "contraseña nueva en $PWF"
fi

setfacl -m u:993:rx "$W"
setfacl -m u:993:rwx "$W/requests" "$W/results"

docker compose config -q
docker compose up -d --no-start
# Copia del perfil sin skills de PERSONAL ni de pruebas, y solo la clave SSH del worker de HALO.
docker run --rm --network none -v "$SRC:/s:ro" -v "$DST:/d" busybox:1.36.1 sh -c '
  set -e
  [ -f /d/config.yaml ] && { echo "el volumen ya tiene datos; no copio"; exit 0; }
  cp -a /s/profiles/coding/. /d/
  rm -rf /d/skills/gestor-entrada /d/skills/sip-*sync* /d/*.lock
  mkdir -p /d/ssh
  cp -a /s/ssh/id_ed25519_halo_worker /s/ssh/id_ed25519_halo_worker.pub /s/ssh/known_hosts /d/ssh/
  chown -R 993:983 /d; chmod 700 /d /d/ssh; chmod 600 /d/ssh/id_ed25519_halo_worker /d/.env'
docker compose up -d
for i in $(seq 40); do
  c=$(curl -s -o /dev/null -w '%{http_code}' http://${NEO_TAILNET_IP}:8788/health || true)
  [ "$c" = 200 ] && break; sleep 3
done
echo "health $c"
docker exec hermes-coding sh -c 'id hermeswebui; ls /home/hermeswebui/.hermes/ssh'
echo "Copia previa en $B"
