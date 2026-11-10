#!/usr/bin/env bash
# ============================================================================
# filegate.sh — SIP filesystem broker · Fase 1B · v1.1 (bash + rsync)
#
# Unica identidad con escritura real sobre PARA. Las zonas hablan con el a
# traves de /run/filegate.sock (systemd socket-activation, Accept=yes) o de
# un socket de test con socat. Protocolo: UNA linea de cabecera (token,
# op_id, comando, args en base64); para `write` el contenido se transmite
# DESPUES de recibir "READY" (evita el buffering read+cat sobre el mismo fd).
#
# v2.4 aplicado: PEP por token · validacion de rutas (../, symlinks fuera,
# allowlist de raices) · SIN /delete · cuarentena con TTL · log append-only
# (G.1) · idempotencia por operation ID (G.4) · rate-limit de versiones
# (M.16) · fail-closed siempre.
# ============================================================================
set -euo pipefail
umask 077

PARA_ROOT="${FILEGATE_PARA_ROOT:-${PARA_ROOT}}"
EXTRA_ROOT="${FILEGATE_EXTRA_ROOT:-${STAGING_ROOT}}"
STAGING="$EXTRA_ROOT/_staging"
QUAR_ROOT="$EXTRA_ROOT/_cuarentena"
JOURNAL="${FILEGATE_JOURNAL:-$EXTRA_ROOT/_journal}"
TOKENS_DIR="${FILEGATE_TOKENS:-/etc/filegate/tokens}"
POLICY="${FILEGATE_POLICY:-/etc/filegate/policy.conf}"
LOG="${FILEGATE_LOG:-/var/log/filegate/audit.log}"
MAX_VERSIONS_PER_HOUR="${FILEGATE_MAX_VERSIONS_PER_HOUR:-10}"
MODE_NEW="${FILEGATE_FILE_MODE:-0660}"   # owner rw, group(usuario) rw, others nada
MODE_DIR="${FILEGATE_DIR_MODE:-0770}"    # idem para directorios que cree

ZONE=""; OPID=""; CMD=""; SRC_LOG=""; DST_LOG=""; MOTIVE=""; RESPONSE=""

audit() { # args: zona op_id op src dst decision resultado motivo
    local line
    line="$(printf '%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s' "$(date -Is)" "$@")"
    mkdir -p "$(dirname "$LOG")" 2>/dev/null || true
    ( flock -w 5 9; printf '%s\n' "$line" >> "$LOG" ) 9>"$LOG.lock" 2>/dev/null \
        || printf '%s\n' "$line" >> "$LOG" 2>/dev/null || true
}

die() {
    audit "$ZONE" "$OPID" "$CMD" "$SRC_LOG" "$DST_LOG" "REJECT" "ERROR" "$1"
    printf 'ERROR %s\n' "$1"
    exit 1
}

ok() { audit "$ZONE" "$OPID" "$CMD" "$SRC_LOG" "$DST_LOG" "ALLOW" "OK" "$MOTIVE"; printf 'OK %s\n' "$1"; }

b64d() { printf '%s' "$1" | base64 -d 2>/dev/null; }

# --- Validacion y canonizacion de rutas --------------------------------------
canon() { # $1 = base64 de ruta absoluta -> stdout ruta canonica; rc!=0 si invalida
    local dec out
    dec="$(b64d "$1")" || return 1
    [ -n "$dec" ] || return 1
    case "$dec" in /*) ;; *) return 1;; esac
    case "/$dec/" in *"/../"*|*"/./"*) return 1;; esac
    case "$dec" in *$'\n'*|*$'\t'*) return 1;; esac
    out="$(realpath -m -- "$dec" 2>/dev/null)" || return 1
    [ -n "$out" ] || return 1
    printf '%s' "$out"
}

root_path() {
    case "$1" in
        PARA)      printf '%s' "$PARA_ROOT";;
        ENTRADA)   printf '%s/00_entrada' "$PARA_ROOT";;
        PROYECTOS) printf '%s/01_proyectos' "$PARA_ROOT";;
        RECURSOS)  printf '%s/03_recursos' "$PARA_ROOT";;
        STAGING)   printf '%s' "$STAGING";;
        QUAR)      printf '%s' "$QUAR_ROOT";;
        *) return 1;;
    esac
}

within() { [ "$1" = "$2" ] || [[ "$1" == "$2"/* ]]; }

allowed() { # $1 zona, $2 op, $3 path canonica -> rc 0 si la politica lo permite
    local z o r rp p="$3"
    [ -r "$POLICY" ] || return 1
    while IFS='|' read -r z o r; do
        case "$z" in ''|\#*) continue;; esac
        [ "$z" = "$1" ] && [ "$o" = "$2" ] || continue
        [ "$r" = "*" ] && return 0
        rp="$(root_path "$r")" || continue
        within "$p" "$rp" && return 0
    done < "$POLICY"
    return 1
}

require_allowed() {
    allowed "$ZONE" "$1" "$2" || die "PEP: $ZONE no puede $1 en $2"
}

# --- Cuarentena / versiones --------------------------------------------------
uuid() { cat /proc/sys/kernel/random/uuid; }

do_quarantine_store() { # $1 origen existente, $2 motivo -> stdout uuid
    local src="$1" reason="$2" qd qu payload h
    qd="$QUAR_ROOT/$(date +%F)"; mkdir -p "$qd"
    qu="$(uuid)"
    mkdir -p "$qd/$qu"
    payload="$qd/$qu/$(basename -- "$src")"
    h="$(sha256sum -- "$src" | cut -d' ' -f1)"
    mv -- "$src" "$payload"
    {
        printf 'uuid=%s\n' "$qu"
        printf 'orig=%s\n' "$src"
        printf 'reason=%s\n' "$reason"
        printf 'zone=%s\n' "$ZONE"
        printf 'ts=%s\n' "$(date -Is)"
        printf 'sha256=%s\n' "$h"
    } > "$qd/$qu/manifest"
    printf '%s' "$qu"
}

version_check_and_store() { # $1 = path existente que sera sobreescrito
    local p="$1" idx now t c
    idx="$JOURNAL/vers-$(printf '%s' "$p" | sha256sum | cut -c1-16)"
    mkdir -p "$JOURNAL"
    now="$(date +%s)"; c=0
    if [ -f "$idx" ]; then
        : > "$idx.tmp"
        while IFS= read -r t; do
            if [ $(( now - t )) -le 3600 ]; then printf '%s\n' "$t" >> "$idx.tmp"; c=$((c+1)); fi
        done < "$idx"
        mv "$idx.tmp" "$idx"
    fi
    if [ "$c" -ge "$MAX_VERSIONS_PER_HOUR" ]; then
        die "rate-limit: $MAX_VERSIONS_PER_HOUR versiones/hora alcanzadas en $p"
    fi
    printf '%s\n' "$now" >> "$idx"
    do_quarantine_store "$p" "write-version (version anterior)" > /dev/null
}

# --- Operaciones -------------------------------------------------------------
cmd_move() { # src dst
    local src dst
    src="$(canon "${1:?}")" || die "src invalida"
    dst="$(canon "${2:?}")" || die "dst invalida"
    require_allowed move-src "$src"
    require_allowed move-dst "$dst"
    [ -e "$src" ] || die "src no existe"
    if [ -e "$dst" ]; then die "dst ya existe"; fi
    mkdir -p "$(dirname "$dst")"
    if [ "$(stat -c %d -- "$src")" = "$(stat -c %d -- "$(dirname "$dst")")" ]; then
        mv -- "$src" "$dst"
    else
        rsync -a --remove-source-files -- "$src" "$dst" || die "rsync fallo"
        rmdir -- "$src" 2>/dev/null || true
    fi
    SRC_LOG="$src"; DST_LOG="$dst"; MOTIVE="move"
}

cmd_write() { # path (contenido por stdin tras READY)
    local p tmpdir
    p="$(canon "${1:?}")" || die "path invalida"
    require_allowed write "$p"
    [ -d "$(dirname "$p")" ] || die "dir destino no existe"
    if [ -L "$p" ]; then die "dst es symlink"; fi
    printf 'READY\n'
    tmpdir="$(mktemp -d "$(dirname "$p")/.filegate.XXXXXX")"
    if ! cat > "$tmpdir/blob"; then rm -rf "$tmpdir"; die "lectura de contenido fallo"; fi
    if [ -e "$p" ]; then
        version_check_and_store "$p"
    fi
    chmod "$MODE_NEW" "$tmpdir/blob"
    mv -- "$tmpdir/blob" "$p"
    rmdir "$tmpdir" 2>/dev/null || true
    DST_LOG="$p"; MOTIVE="write"
}

cmd_mkdir() { # path
    local p
    p="$(canon "${1:?}")" || die "path invalida"
    require_allowed mkdir "$p"
    if [ -L "$p" ]; then die "dst es symlink"; fi
    mkdir -p -m "$MODE_DIR" -- "$p" || die "mkdir fallo"
    DST_LOG="$p"; MOTIVE="mkdir"
}

cmd_quarantine() { # src reason(b64, opcional)
    local src reason q
    src="$(canon "${1:?}")" || die "src invalida"
    reason="$(b64d "${2:-}" 2>/dev/null || true)"; reason="${reason:-sin motivo}"
    require_allowed quarantine-src "$src"
    [ -e "$src" ] || die "src no existe"
    q="$(do_quarantine_store "$src" "$reason")"
    SRC_LOG="$src"; MOTIVE="quarantine uuid=$q"
    printf 'OK quarantine_uuid=%s\n' "$q"
    audit "$ZONE" "$OPID" "$CMD" "$src" "" "ALLOW" "OK" "$MOTIVE"
    exit 0
}

cmd_restore() { # uuid
    local qu man orig zone_m payload canon_orig
    qu="${1:?}"
    case "$qu" in *[!a-fA-F0-9-]*|"") die "uuid invalido";; esac
    man="$(find "$QUAR_ROOT" -maxdepth 3 -name manifest -path "*/$qu/manifest" -print -quit 2>/dev/null)"
    [ -n "$man" ] || die "uuid no encontrado en cuarentena"
    orig="$(sed -n 's/^orig=//p' "$man")"
    zone_m="$(sed -n 's/^zone=//p' "$man")"
    [ "$zone_m" = "$ZONE" ] || [ "$ZONE" = "admin" ] || die "la cuarentena pertenece a otra zona"
    payload="$(find "$(dirname "$man")" -mindepth 1 -maxdepth 1 ! -name manifest -print -quit)"
    [ -n "$payload" ] || die "payload ausente"
    canon_orig="$(realpath -m -- "$orig")"
    if ! allowed "$ZONE" move-dst "$canon_orig"; then
        require_allowed restore "$canon_orig"
    fi
    if [ -e "$orig" ]; then die "el destino ya existe; no se sobreescribe"; fi
    mkdir -p "$(dirname "$orig")"
    mv -- "$payload" "$orig"
    rm -f -- "$man"; rmdir "$(dirname "$man")" 2>/dev/null || true
    DST_LOG="$orig"; MOTIVE="restore uuid=$qu"
}

cmd_plan() { # pattern b64 (nombre simple, sin /)
    local pat z o r rp
    pat="$(b64d "${1:?}")" || die "patron invalido"
    case "$pat" in */*|*..*) die "patron no valido";; esac
    while IFS='|' read -r z o r; do
        case "$z" in ''|\#*) continue;; esac
        [ "$z" = "$ZONE" ] && [ "$o" = "plan" ] || continue
        rp="$(root_path "$r")" || continue
        [ -d "$rp" ] || continue
        find "$rp" -name "$pat" -print 2>/dev/null | while IFS= read -r line; do
            printf 'MATCH %s\n' "$line"
        done
    done < "$POLICY"
    MOTIVE="plan"; SRC_LOG="$pat"
}

cmd_log() {
    [ "$ZONE" = "admin" ] || die "log solo para admin"
    tail -n 50 "$LOG" 2>/dev/null || true
    MOTIVE="log"
}

# --- Idempotencia (G.4) -------------------------------------------------------
journal_replay_or_begin() {
    [ -d "$JOURNAL" ] || mkdir -p "$JOURNAL"
    local jf="$JOURNAL/$OPID.result"
    if [ -f "$jf" ]; then
        printf 'OK idempotent-replay\n'
        cat "$jf"
        exit 0
    fi
    trap 'rc=$?; if [ $rc -eq 0 ] && [ -n "${RESPONSE:-}" ]; then printf "%s\n" "$RESPONSE" > "$JOURNAL/$OPID.result" 2>/dev/null || true; fi' EXIT
}

# --- Main ---------------------------------------------------------------------
main() {
    local header token opid cmd a1 a2
    if ! IFS= read -r -t 30 header; then die "sin cabecera"; fi
    [ -n "$header" ] || die "cabecera vacia"
    read -r token opid cmd a1 a2 _ <<< "$header"
    [ -n "${token:-}" ] && [ -n "${cmd:-}" ] || die "cabecera incompleta"

    local f
    shopt -s nullglob
    for f in "$TOKENS_DIR"/*.tok; do
        if [ "$(<"$f")" = "$token" ]; then ZONE="$(basename "$f" .tok)"; break; fi
    done
    [ -n "$ZONE" ] || die "token invalido"

    OPID="${opid:--}"; CMD="$cmd"
    case "$OPID" in -|*[!a-zA-Z0-9_.-]*|"") OPID="op-$(uuid)";; esac
    journal_replay_or_begin

    case "$cmd" in
        move)       [ -n "${a1:-}" ] && [ -n "${a2:-}" ] || die "move necesita src y dst"
                    cmd_move "$a1" "$a2"; RESPONSE="moved" ;;
        write)      [ -n "${a1:-}" ] || die "write necesita path"
                    cmd_write "$a1"; RESPONSE="written" ;;
        mkdir)      [ -n "${a1:-}" ] || die "mkdir necesita path"
                    cmd_mkdir "$a1"; RESPONSE="created" ;;
        quarantine) [ -n "${a1:-}" ] || die "quarantine necesita src"
                    cmd_quarantine "$a1" "${a2:-}" ;;
        restore)    [ -n "${a1:-}" ] || die "restore necesita uuid"
                    cmd_restore "$a1"; RESPONSE="restored" ;;
        plan)       [ -n "${a1:-}" ] || die "plan necesita patron"
                    cmd_plan "$a1"; RESPONSE="planned" ;;
        log)        cmd_log; RESPONSE="logged" ;;
        *)          die "comando desconocido" ;;
    esac
    ok "$RESPONSE"
}

main "$@"
