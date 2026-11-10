#!/bin/bash
# Guarda el token del bot y el UID permitido sin mostrarlos ni dejarlos en el historial,
# y los prueba enviando un mensaje. Uso, en Neo: sudo bash set-telegram.sh
# Antes: abrir el chat del bot en Telegram y pulsar Iniciar, o el bot no puede escribirte.
# No reinicia nada ni conecta ningún gateway.
set -euo pipefail

ENV_FILE="${SIP_ENV_FILE:-/root/sip-telegram.env}"

IFS= read -rsp "Pega el token de @BotFather (no se mostrará) y pulsa Intro: " TOKEN
echo
[[ "$TOKEN" =~ ^[0-9]+:[A-Za-z0-9_-]{30,}$ ]] || { echo "ERROR: no parece un token de bot; no cambio nada." >&2; exit 1; }
IFS= read -rp "Tu UID numérico de @userinfobot: " UID_TG
[[ "$UID_TG" =~ ^[0-9]{5,15}$ ]] || { echo "ERROR: el UID son solo cifras; no cambio nada." >&2; exit 1; }

# El token va por stdin a curl para que no aparezca en la lista de procesos.
api() { printf 'url = "https://api.telegram.org/bot%s/%s"\n' "$TOKEN" "$1" | curl -sS -m 15 -K - "${@:2}"; }

ME="$(api getMe)"
echo "$ME" | grep -q '"ok":true' || { echo "ERROR: Telegram rechaza el token; no cambio nada." >&2; exit 1; }
echo "Bot: @$(echo "$ME" | sed -n 's/.*"username":"\([^"]*\)".*/\1/p')"

SENT="$(api sendMessage --data-urlencode "chat_id=$UID_TG" --data-urlencode "text=SIP: prueba de canal desde Neo")"
echo "$SENT" | grep -q '"ok":true' || { echo "ERROR: no pude escribirte. ¿Pulsaste Iniciar en el chat del bot? ¿UID correcto? No cambio nada." >&2; exit 1; }

umask 077
TMP="$(mktemp "$ENV_FILE.XXXXXX")"
trap 'rm -f "$TMP"' EXIT
printf 'TELEGRAM_BOT_TOKEN=%s\nTELEGRAM_ALLOWED_USERS=%s\n' "$TOKEN" "$UID_TG" > "$TMP"
chown root:root "$TMP"
mv "$TMP" "$ENV_FILE"
unset TOKEN

echo "OK: mensaje enviado y datos guardados en $ENV_FILE ($(stat -c '%a %U:%G' "$ENV_FILE"))."
