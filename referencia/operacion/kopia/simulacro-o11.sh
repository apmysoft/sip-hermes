#!/bin/sh
# Simulacro O11, parte local (root, en Neo): descifra la última sip-estado, comprueba cada zona y arranca
# RESEARCH restaurado en un contenedor desechable sin red. No toca ningún volumen real: todo en un
# directorio temporal que se borra al final. La parte de Kopia (recuperar el fichero del repositorio) la
# hace el usuario desde KopiaUI.
# Uso: sh simulacro-o11.sh [fichero .tar.gz.age]   (por defecto, el más reciente de _copias-sip-estado)
set -eu
C="${PARA_ROOT}/01_proyectos/Implementación SIP + Hermes agent/_copias-sip-estado"
F=${1:-$(ls -1 "$C"/sip-estado-*.tar.gz.age | tail -1)}
PASS=$(cat /root/sip-hermes-backup.pass)
T=$(mktemp -d /var/tmp/sip-o11.XXXXXX)
trap 'docker rm -f sip-o11-research >/dev/null 2>&1 || true; rm -rf "$T"' EXIT
t0=$(date +%s)
echo "fichero: $(basename "$F")"
printf '%s\n' "$PASS" | script -qec "age -d -o '$T/e.tar.gz' '$F'" /dev/null >/dev/null 2>&1
tar -xzpf "$T/e.tar.gz" -C "$T"
rm -f "$T/e.tar.gz"
echo "descifrado y extraído en $(( $(date +%s) - t0 )) s"
for z in personal coding research; do
    d="$T/sip-estado/$z"
    n=0; malas=0
    for db in $(find "$d" -name '*.db' -type f); do
        n=$((n + 1))
        [ "$(sqlite3 "$db" 'PRAGMA integrity_check;')" = ok ] || malas=$((malas + 1))
    done
    python3 -c "import yaml,sys; yaml.safe_load(open(sys.argv[1]))" "$d/config.yaml"
    echo "$z: $(find "$d" -type f | wc -l) ficheros, $n bases ($malas con error), config.yaml válido, dueño $(stat -c %u:%g "$d")"
    [ "$malas" = 0 ]
done
ls "$T/sip-estado/litellm/"*.sql.gz.age >/dev/null && echo "litellm: copia cifrada presente"
ls "$T/sip-estado/flujos/"*.tar.gz.age >/dev/null && echo "sip-flujos: copia cifrada presente"
test -f "$T/sip-estado/filegate-log/audit.log" && echo "filegate: audit.log con $(wc -l < "$T/sip-estado/filegate-log/audit.log") líneas"
# RESEARCH restaurado, arrancado de verdad: misma imagen, sin red, su UID, el home restaurado.
img=$(docker inspect -f '{{.Config.Image}}' hermes-research)
docker run -d --name sip-o11-research --network none -u 995:985 -e HOME=/opt/data -e HERMES_HOME=/opt/data \
    -v "$T/sip-estado/research:/opt/data" --entrypoint sleep "$img" 300 >/dev/null
echo "RESEARCH restaurado: herramientas $(docker exec sip-o11-research hermes tools list --platform cli 2>&1 | grep '✓' | awk '{print $3}' | tr '\n' ' ')"
echo "RESEARCH restaurado: sesiones en state.db $(docker exec sip-o11-research python3 -c "import sqlite3;print(sqlite3.connect('/opt/data/state.db').execute('select count(*) from sessions').fetchone()[0])")"
echo "RTO de la parte local: $(( $(date +%s) - t0 )) s"
echo "RESULTADO: OK"
