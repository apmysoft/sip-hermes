#!/bin/bash
# Guarda una clave de proveedor en el env de LiteLLM sin mostrarla ni dejarla en el
# historial. Uso, en Neo: sudo bash set-provider-key.sh GEMINI_API_KEY|KIMI_API_KEY
# No reinicia nada: el agente aplica la configuración y prueba la clave después.
set -euo pipefail

ENV_FILE="${SIP_ENV_FILE:-/root/sip-litellm.env}"

case "${1:-}" in
  GEMINI_API_KEY|KIMI_API_KEY) NAME="$1" ;;
  *) echo "Uso: $0 GEMINI_API_KEY|KIMI_API_KEY" >&2; exit 2 ;;
esac

[ -f "$ENV_FILE" ] || { echo "ERROR: no existe $ENV_FILE" >&2; exit 1; }

IFS= read -rsp "Pega $NAME (no se mostrará) y pulsa Intro: " VALUE
echo

# Compose interpreta los $ del env_file; las claves válidas no llevan $ ni espacios.
case "$VALUE" in
  "") echo "ERROR: clave vacía; no cambio nada." >&2; exit 1 ;;
  *[[:space:]]*|*\$*) echo "ERROR: la clave tiene espacios o \$; no cambio nada." >&2; exit 1 ;;
esac
if [ "$NAME" = KIMI_API_KEY ] && [ "${VALUE#sk-kimi-}" = "$VALUE" ]; then
  echo "ERROR: una clave de Kimi Code empieza por sk-kimi-; no cambio nada." >&2; exit 1
fi

TMP="$(mktemp "$ENV_FILE.XXXXXX")"
trap 'rm -f "$TMP"' EXIT
grep -v "^$NAME=" "$ENV_FILE" > "$TMP" || true
printf '%s=%s\n' "$NAME" "$VALUE" >> "$TMP"
chmod 600 "$TMP"
chown --reference="$ENV_FILE" "$TMP"
mv "$TMP" "$ENV_FILE"
unset VALUE

echo "OK: $NAME guardada en $ENV_FILE ($(stat -c '%a %U:%G' "$ENV_FILE"))."
