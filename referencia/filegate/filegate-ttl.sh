#!/bin/sh
# filegate-ttl.sh — purga con retención de staging y cuarentena (Bloque 5).
#
# Alternativa a systemd-tmpfiles: tmpfiles rechaza ${STAGING_ROOT} por
# transición de propietario insegura (usuario -> filegate). Esta unidad hace lo
# mismo con find, como root, y loguea lo purgado. El _journal NUNCA se toca.
#
# Retenciones: _staging 30 días; _cuarentena 180 días (conservador: alberga
# copias pre-borrado con manifest + sha256). Ajustar STAGING_DAYS/QUAR_DAYS.
set -eu

BASE=${FILEGATE_BASE:-${STAGING_ROOT}}
STAGING_DAYS=${STAGING_DAYS:-30}
QUAR_DAYS=${QUAR_DAYS:-180}

purge() {
    dir=$1 days=$2
    [ -d "$dir" ] || return 0
    # -mindepth 1: nunca el propio directorio; solo ficheros más antiguos.
    find "$dir" -mindepth 1 -mtime +"$days" -print -delete 2>/dev/null | \
        while IFS= read -r f; do
            logger -t filegate-ttl "purga ($days días): $f"
            echo "purga ($days días): $f"
        done
}

purge "$BASE/_staging" "$STAGING_DAYS"
purge "$BASE/_cuarentena" "$QUAR_DAYS"
exit 0
