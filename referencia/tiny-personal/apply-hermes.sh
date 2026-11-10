#!/bin/sh
# Parte D del respaldo de PERSONAL con el tiny de Neo (v2.4 §H.3, aprobada el 06-11): tiny como PRIMER fallback (Hermes solo cambia una vez de proveedor por turno)
# en el perfil personal de la WebUI y en config.api.yaml de la API. Requiere apply.sh (B y C) aplicado.
# Root, en Neo, desde este directorio. Rollback: sh $B/rollback.sh
set -eu
cd "$(dirname "$0")"
V=${DOCKER_DATA}/docker_root/volumes/hermes_hermes-home/_data/profiles/personal/config.yaml
A=/home/usuario/sip-inventario/sip-config/personal-api/config.api.yaml
B=/root/sip-agent-backups/$(date +%F)/tiny-personal/d
[ ! -e "$B" ] || { echo "ERROR: ya existe $B" >&2; exit 1; }
systemctl is-active -q sip-tiny-personal.socket || { echo "ERROR: falta sip-tiny-personal.socket (apply.sh)" >&2; exit 1; }
install -d -m 700 "$B"
cp -p "$V" "$B/config.personal.yaml"; cp -p "$A" "$B/config.api.yaml"
cat > "$B/rollback.sh" <<X
#!/bin/sh
cat $B/config.personal.yaml > $V; cat $B/config.api.yaml > $A
docker restart hermes-personal-api hermes-webui
X
for f in "$V" "$A"; do python3 editar-config-fallback.py "$f"; done
docker restart hermes-personal-api hermes-webui >/dev/null
sleep 15
echo "== verificación"
docker exec hermes-personal-api sh -c 'grep -c "custom:tiny_neo" /opt/data/config.yaml' | sed 's/^/  API ve la entrada: /'
docker exec hermes-webui sh -c 'grep -c "custom:tiny_neo" /home/hermeswebui/.hermes/profiles/personal/config.yaml' | sed 's/^/  WebUI ve la entrada: /'
docker ps --filter name=hermes-personal-api --filter name=hermes-webui --format '  {{.Names}} {{.Status}}'
echo "RESULTADO: OK (rollback: sh $B/rollback.sh)"
