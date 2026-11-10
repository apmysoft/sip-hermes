#!/usr/bin/env bash
# filegate-client.sh — cliente de referencia para las zonas (Fase 1B)
# Uso: filegate-client.sh <socket> <fichero-token> <op> [args...]
#   write: el ultimo arg es el fichero local cuyo contenido se transmite.
#   Los paths se pasan en CLARO; el cliente los base64-a (protocolo).
# v1.2: coproc — el READY se lee del socket, no del stdin del script.
set -uo pipefail

SOCK="${1:?socket}"; TOKF="${2:?token file}"; OP="${3:?op}"; shift 3
TOKEN="$(<"$TOKF")"
b64() { printf '%s' "$1" | base64 -w0; }

opid="op-$(cat /proc/sys/kernel/random/uuid)"
case "$OP" in
    move)       hdr="$(printf '%s %s move %s %s' "$TOKEN" "$opid" "$(b64 "${1:-}")" "$(b64 "${2:-}")")" ;;
    write)      hdr="$(printf '%s %s write %s' "$TOKEN" "$opid" "$(b64 "${1:-}")")" ;;
    mkdir)      hdr="$(printf '%s %s mkdir %s' "$TOKEN" "$opid" "$(b64 "${1:-}")")" ;;
    quarantine) hdr="$(printf '%s %s quarantine %s %s' "$TOKEN" "$opid" "$(b64 "${1:-}")" "$(b64 "${2:-sin motivo}")")" ;;
    restore)    hdr="$(printf '%s %s restore %s' "$TOKEN" "$opid" "${1:-}")" ;;
    plan)       hdr="$(printf '%s %s plan %s' "$TOKEN" "$opid" "$(b64 "${1:-}")")" ;;
    log)        hdr="$(printf '%s %s log' "$TOKEN" "$opid")" ;;
    *) echo "op desconocida" >&2; exit 2 ;;
esac

coproc FG { socat -t 10 - "UNIX-CONNECT:$SOCK"; }
printf '%s\n' "$hdr" >&"${FG[1]}"

if [ "$OP" = "write" ]; then
    IFS= read -r line <&"${FG[0]}"
    if [ "$line" != "READY" ]; then
        # el servidor rechazo antes de READY: devolver su mensaje tal cual
        printf '%s\n' "$line"
        cat <&"${FG[0]}"
        exit 1
    fi
    cat -- "${2:?fichero local requerido para write}" >&"${FG[1]}"
fi

exec {FG[1]}>&-          # cerrar escritura -> el servidor ve EOF en su cat
cat <&"${FG[0]}"         # respuesta final (OK/ERROR)
