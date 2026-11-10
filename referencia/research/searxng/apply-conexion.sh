#!/bin/sh
# APLICADO el 06-11 con el visto bueno del usuario. Antes: PREPARADO, NO APLICADO (06-11): conecta RESEARCH con SearXNG local. Requiere el visto bueno del usuario
# porque añade una excepción a nftables (regla 6): RESEARCH (10.20.0.0/24) -> 10.20.0.20:8080, nada más.
# Root, en Neo, desde este directorio. SearXNG ya está desplegado (docker-compose.yml, ~/sip-research-searxng).
# Rollback: sh $B/rollback.sh
set -eu
cd "$(dirname "$0")"
R=/home/usuario/sip-fase7-research
# La config que usa el contenedor está en su volumen; $R/config.yaml es solo la semilla inicial (incidencia 06-11).
V=${DOCKER_DATA}/docker_root/volumes/sip-research_hermes-research-home/_data/config.yaml
B=/root/sip-agent-backups/$(date +%F)/searxng-conexion
[ ! -e "$B" ] || { echo "ERROR: ya existe $B" >&2; exit 1; }
docker ps --filter name=sip-searxng --format '{{.Status}}' | grep -q '^Up' || { echo "ERROR: sip-searxng no está en marcha" >&2; exit 1; }
nft -c -f nftables-sip.candidate.nft
# La candidata se hizo sobre las reglas vigentes del 06-11: si han cambiado, no se aplica a ciegas.
diff /etc/nftables-sip.nft nftables-sip.candidate.nft | grep -E '^[<>]' | grep -vE '10\.20\.0\.20|SearXNG' && \
  { echo "ERROR: /etc/nftables-sip.nft ha cambiado desde la candidata; rehazla" >&2; exit 1; } || true
install -d -m 700 "$B"
cp -p /etc/nftables-sip.nft "$B/nftables-sip.nft-pre"; cp -p "$V" "$B/config.volumen.yaml"; cp -p "$R/docker-compose.yml" "$B/"
cat > "$B/rollback.sh" <<X
#!/bin/sh
cp -p $B/nftables-sip.nft-pre /etc/nftables-sip.nft; systemctl restart nft-sip-zones
cat $B/config.volumen.yaml > $V; cp -p $B/docker-compose.yml $R/; (cd $R && docker compose up -d --force-recreate)
X
install -o root -g root -m 644 nftables-sip.candidate.nft /etc/nftables-sip.nft
systemctl restart nft-sip-zones
# RESEARCH: SearXNG por SEARXNG_URL (Hermes lo detecta solo) y toolset `search` (solo web_search; para leer
# páginas ya está el navegador). Escritura en el mismo fichero: conserva dueño y modo.
grep -q '^    - search$' "$V" || sed -i 's/^    - entrada$/    - entrada\n    - search/' "$V"
grep -q 'SEARXNG_URL' "$R/docker-compose.yml" || \
  sed -i 's|^      - API_SERVER_ENABLED=true$|      - SEARXNG_URL=http://10.20.0.20:8080  # SearXNG local (06-11)\n      - API_SERVER_ENABLED=true|' "$R/docker-compose.yml"
(cd "$R" && docker compose config -q && docker compose up -d --force-recreate) >/dev/null
sleep 10
echo "== verificación"
docker exec hermes-research python3 -c "
import json,urllib.request
d=json.load(urllib.request.urlopen('http://10.20.0.20:8080/search?q=prueba&format=json',timeout=30))
print('  RESEARCH -> SearXNG:', len(d['results']), 'resultados')"
docker exec hermes-research python3 -c "
import urllib.request
try: urllib.request.urlopen('http://10.20.0.1:22',timeout=5); print('  MAL: llega a otra IP privada')
except Exception as e: print('  sigue cerrado el resto de la red privada:', type(e).__name__)"
echo "RESULTADO: OK (rollback: sh $B/rollback.sh)"
