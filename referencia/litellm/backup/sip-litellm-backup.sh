#!/bin/sh
# sip-litellm-backup.sh — copia cifrada con age de la DB de LiteLLM (metadatos
# de gasto y hashes de claves virtuales; v2.4 M.7). Verifica cada copia.
#
# Misma passphrase y mismo método que sip-hermes-backup-encrypted.sh: age exige
# TTY, script(1) aporta el pty y la passphrase viaja por pipe.
#
# Restauración:
#   1. age -d -o /tmp/litellm.sql.gz <fichero>.sql.gz.age   (pide la passphrase)
#   2. gzip -dc /tmp/litellm.sql.gz | docker exec -i sip-litellm-db psql -U litellm -d litellm
#   3. rm -f /tmp/litellm.sql.gz
set -eu

DEST=${SIP_LITELLM_BACKUP_DIR:-/var/backups/sip-litellm}
KEEP=${SIP_LITELLM_BACKUP_KEEP:-14}
PASS_FILE=${SIP_HERMES_BACKUP_PASS:-/root/sip-hermes-backup.pass}

[ -r "$PASS_FILE" ] || { echo "passphrase ausente: $PASS_FILE" >&2; exit 1; }
PASS=$(cat "$PASS_FILE")
[ -n "$PASS" ] || { echo "passphrase vacía" >&2; exit 1; }

umask 077
install -d -m 700 "$DEST"
TMP=$(mktemp -d /tmp/sip-litellm-backup.XXXXXX)
trap 'rm -rf "$TMP"' EXIT

OUT="$DEST/litellm-db-$(date +%Y%m%d-%H%M%S).sql.gz.age"
docker exec sip-litellm-db pg_dump -U litellm -d litellm | gzip > "$TMP/dump.sql.gz"

printf '%s\n%s\n' "$PASS" "$PASS" | \
  script -qec "age -p -o '$OUT' '$TMP/dump.sql.gz'" /dev/null >/dev/null 2>&1 || { rm -f "$OUT"; echo "cifrado fallido" >&2; exit 1; }

# Verificación: descifrar y comprobar que el volcado es completo
printf '%s\n' "$PASS" | \
  script -qec "age -d -o '$TMP/check.sql.gz' '$OUT'" /dev/null >/dev/null 2>&1 || { rm -f "$OUT"; echo "descifrado de verificación fallido" >&2; exit 1; }
gzip -t "$TMP/check.sql.gz"
gzip -dc "$TMP/check.sql.gz" | grep -q 'PostgreSQL database dump complete' || { rm -f "$OUT"; echo "volcado incompleto" >&2; exit 1; }

chmod 0600 "$OUT"

# Retención: solo se consideran los ficheros de este script
ls -1t "$DEST"/litellm-db-*.sql.gz.age | tail -n +"$((KEEP + 1))" | while read -r old; do
  rm -f -- "$old"
done

echo "OK: $OUT"
