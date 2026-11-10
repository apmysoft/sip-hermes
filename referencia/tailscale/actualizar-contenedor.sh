#!/bin/sh
# Contenedor tailscale de Neo 1.102.2 -> 1.104.4 (05-11, pedido del usuario). Root, en Neo.
# El acceso SSH a Neo va por la tailnet: este script se lanza desacoplado (systemd-run) y deja programada
# una vuelta atrás automática a los 5 min (unidad sip-ts-revert). Si tras la actualización se vuelve a
# entrar por SSH y todo está bien, se cancela con: systemctl stop sip-ts-revert.timer
# Lanzar:  systemd-run --unit sip-ts-update --collect sh /root/sip-ts/actualizar-contenedor.sh
# Log:     /root/sip-agent-backups/<fecha>/tailscale-1.104/log
# Rollback manual: sh $B/rollback.sh
set -eu
D=${DOCKER_DATA}/stacks/tailscale
B=/root/sip-agent-backups/$(date +%F)/tailscale-1.104
NUEVA='tailscale/tailscale@sha256:ed6480b33c6eb67c9cbd203ed42b9fb57e361986725b6856def71b7a3d9e276c'  # v1.104.4 (stable)
VIEJA='tailscale/tailscale@sha256:321ce041508c19079b57a28b6666c8d81ab0b08accc0a2585b3ab663d557ac24'  # v1.102.2

grep -q "image: $VIEJA" "$D/compose.yaml" || { echo "ERROR: compose distinto del esperado" >&2; exit 1; }
[ ! -e "$B" ] || { echo "ERROR: ya existe $B" >&2; exit 1; }
install -d -m 700 "$B"
exec >"$B/log" 2>&1
date '+%F %T inicio'
cp -p "$D/compose.yaml" "$B/compose.yaml"
docker exec tailscale tailscale serve status --json > "$B/serve-pre.json"
# El estado contiene la clave del nodo: se copia a la carpeta 0700 de copias (ROTACION.md), no se lee.
cp -a "$D/tailscale/state" "$B/state"
cat > "$B/rollback.sh" <<EOF
#!/bin/sh
cd $D && cp -p $B/compose.yaml $D/compose.yaml && docker compose up -d
echo "\$(date '+%F %T') rollback aplicado" >> $B/log
EOF
docker pull -q "$NUEVA"

# Vuelta atrás automática si nadie la cancela en 5 min
systemd-run --unit sip-ts-revert --collect --on-active=300 sh "$B/rollback.sh"

sed -i "s|image: $VIEJA|image: $NUEVA  # v1.104.4 (05-11)|" "$D/compose.yaml"
cd "$D" && docker compose config -q && docker compose up -d
for i in $(seq 30); do
  docker exec tailscale tailscale status --json 2>/dev/null | python3 -c 'import json,sys;sys.exit(0 if json.load(sys.stdin)["BackendState"]=="Running" else 1)' && break
  sleep 2
done
docker exec tailscale tailscale version | head -1
docker exec tailscale tailscale status --json | python3 -c 'import json,sys;print("backend:",json.load(sys.stdin)["BackendState"])'
docker exec tailscale tailscale serve status --json > "$B/serve-post.json"
cmp -s "$B/serve-pre.json" "$B/serve-post.json" && echo "serve: igual" || echo "serve: DISTINTO"
date '+%F %T fin (revert pendiente: systemctl stop sip-ts-revert.timer)'
