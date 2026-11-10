#!/usr/bin/env bash
# Monta PARA en solo lectura en hermes-webui (PERSONAL) y lo verifica. Ejecutar en Neo desde este directorio.
# No lista ni lee contenido de PARA: solo comprueba montajes, modo y que escribir falla.
# Rollback: docker compose -f docker-compose.yml -f compose.ssh-sandbox.yml up -d hermes-webui
set -euo pipefail
cd "$(dirname "$0")"
F=(-f docker-compose.yml -f compose.ssh-sandbox.yml -f compose.para-ro.yml)
B=/root/sip-agent-backups/$(date +%F)/para-ro
sudo -n mkdir -p "$B"
docker inspect hermes-webui | sudo -n tee "$B/hermes-webui.inspect.json" >/dev/null
docker compose "${F[@]}" config -q
docker compose "${F[@]}" up -d hermes-webui
for i in $(seq 1 60); do
  [ "$(docker inspect -f '{{.State.Health.Status}}' hermes-webui)" = healthy ] && break; sleep 2
done
echo "salud: $(docker inspect -f '{{.State.Health.Status}}' hermes-webui)"
fallo=0
for d in 00_entrada 01_proyectos 02_areas 03_recursos 04_archivo; do
  rw=$(docker inspect -f "{{range .Mounts}}{{if eq .Destination \"/para/$d\"}}{{.RW}}{{end}}{{end}}" hermes-webui)
  lee=$(docker exec -u 1000 hermes-webui sh -c "test -r /para/$d && test -x /para/$d && echo si || echo no")
  esc=$(docker exec -u 1000 hermes-webui sh -c "touch /para/$d/.sip-escritura-prueba 2>&1 || true")
  case "$esc" in *"Read-only file system"*) esc=EROFS;; esac
  echo "$d: RW=$rw lectura=$lee escritura=$esc"
  [ "$rw" = false ] && [ "$lee" = si ] && [ "$esc" = EROFS ] || fallo=1
done
[ "$fallo" = 0 ] && echo "PARA ro: OK" || { echo "PARA ro: FALLO" >&2; exit 1; }
