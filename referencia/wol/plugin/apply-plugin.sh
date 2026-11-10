#!/bin/sh
# Instala sip-halo-wake en todos los perfiles de hermes-webui. Uso en Neo: sudo sh apply-plugin.sh
# (con sip-halo-wake/ junto al script).
# Rollback: restaurar config.yaml de $B en cada perfil, borrar plugins/sip-halo-wake y
#   docker restart hermes-webui.
set -eu
H=${DOCKER_DATA}/docker_root/volumes/hermes_hermes-home/_data
B=/root/sip-agent-backups/$(date +%F)/halo-wake
mkdir -p "$B"
for d in "$H" "$H"/profiles/*; do
  [ -f "$d/config.yaml" ] || continue
  n=$(basename "$d"); [ "$d" = "$H" ] && n=raiz
  cp -p "$d/config.yaml" "$B/$n.config.yaml"
  mkdir -p "$d/plugins"
  rm -rf "$d/plugins/sip-halo-wake"
  cp -r sip-halo-wake "$d/plugins/"
  chown -R 1000:1000 "$d/plugins"
  if ! grep -q '^plugins:' "$d/config.yaml"; then
    printf 'plugins:\n  enabled:\n    - sip-halo-wake\n' >> "$d/config.yaml"
  fi
  echo "instalado: $n"
done
docker restart hermes-webui >/dev/null
for i in $(seq 30); do
  curl -fsS -o /dev/null http://${NEO_TAILNET_IP}:8787/health 2>/dev/null && break; sleep 2
done
docker exec -u 1000 hermes-webui /app/venv/bin/python -c '
import glob, yaml
for f in ["/home/hermeswebui/.hermes/config.yaml"] + glob.glob("/home/hermeswebui/.hermes/profiles/*/config.yaml"):
    assert "sip-halo-wake" in yaml.safe_load(open(f))["plugins"]["enabled"], f
print("yaml ok")'
echo "copia en $B"
