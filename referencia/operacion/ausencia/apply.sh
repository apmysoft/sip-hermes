#!/bin/sh
# Instala sip-ausencia y el WOL que la respeta (root, en Neo), y lo prueba: on → petición del plugin
# (debe dar "ausencia") y explícita (debe despertar o dar already_awake) → off.
# Copia previa: /root/sip-agent-backups/<fecha>/ausencia/sip-wol-halo.py.
# Rollback: install -m 0755 <copia> /usr/local/sbin/sip-wol-halo.py; sip-ausencia off;
# rm /usr/local/sbin/sip-ausencia.
set -eu
cd "$(dirname "$0")"
B=/root/sip-agent-backups/$(date +%F)/ausencia
W=${DOCKER_DATA}/hermes/workspace/_wol
install -d -m 0700 "$B"
[ -e "$B/sip-wol-halo.py" ] || cp -p /usr/local/sbin/sip-wol-halo.py "$B/"
install -o root -g root -m 0755 ../../wol/sip-wol-halo.py /usr/local/sbin/sip-wol-halo.py
install -o root -g root -m 0755 sip-ausencia /usr/local/sbin/sip-ausencia
[ -e /var/lib/sip-ausencia/activa ] && { echo "ausencia ya activa: no se prueba"; exit 1; }

resultado() {  # $1 = id de la petición; la escribe el agente de PERSONAL, como el plugin
    docker exec -u 1000 hermes-webui sh -c "echo {} > /workspace/_wol/requests/$1.json"
    for _ in $(seq 60); do
        [ -e "$W/results/$1.json" ] && { cat "$W/results/$1.json"; rm -f "$W/results/$1.json"; return; }
        sleep 2
    done
    echo "sin respuesta"
}
comprobar() {  # $1 = id, $2 = estados aceptados (regex), $3 = texto
    r=$(resultado "$1"); echo "$3: $r"
    echo "$r" | grep -qE "\"($2)\"" || { echo "FALLO: $3"; exit 1; }
}
/usr/local/sbin/sip-ausencia on
/usr/local/sbin/sip-ausencia estado
comprobar plugin-prueba-ausencia 'ausencia' "plugin en ausencia"
comprobar explicita-prueba-ausencia 'awake|already_awake' "explícita en ausencia"
/usr/local/sbin/sip-ausencia off
/usr/local/sbin/sip-ausencia estado
test ! -e /var/lib/sip-ausencia/activa
comprobar plugin-prueba-normal 'awake|already_awake' "plugin sin ausencia"
echo "RESULTADO: OK"
