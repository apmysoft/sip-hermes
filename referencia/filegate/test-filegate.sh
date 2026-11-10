#!/usr/bin/env bash
# ============================================================================
# test-filegate.sh — suite de Fase 1B. Corre ANTE CADA cambio de filegate
# (v2.4 G.1: fuzzing de rutas + PEP por token + cuarentena/restore +
# rate-limit de versiones + idempotencia). Sin root; NO toca PARA.
# Requisito: socat, openssl, rsync.
# ============================================================================
set -uo pipefail

T="$(mktemp -d /tmp/filegate-test.XXXXXX)"
SRC_DIR="$(cd "$(dirname "$0")" && pwd)"
export FILEGATE_PARA_ROOT="$T/para"
export FILEGATE_EXTRA_ROOT="$T/extra"
export FILEGATE_TOKENS="$T/tokens"
export FILEGATE_POLICY="$T/policy.conf"
export FILEGATE_LOG="$T/audit.log"
export FILEGATE_MAX_VERSIONS_PER_HOUR=10
mkdir -p "$T/para/00_entrada" "$T/para/01_proyectos" "$T/para/02_areas" \
         "$T/tokens" "$T/extra/_staging" "$T/extra/_cuarentena" "$T/extra/_journal"
cp "$SRC_DIR/policy.conf" "$T/policy.conf"
cp "$SRC_DIR/filegate-client.sh" "$T/client"
for z in research personal coding admin; do
    openssl rand -hex 20 | tr -d '\n' > "$T/tokens/$z.tok"
done

SOCK="$T/sock"
socat UNIX-LISTEN:"$SOCK",fork EXEC:"$SRC_DIR/filegate.sh" &
SOCAT_PID=$!
trap 'kill $SOCAT_PID 2>/dev/null; rm -rf "$T"' EXIT
sleep 0.4

PASS=0; FAIL=0; RC=0
req() { local zf="$T/tokens/$1.tok"; shift
        OUT="$(bash "$T/client" "$SOCK" "$zf" "$@")"; RC=$?; }
check() { if eval "$2"; then PASS=$((PASS+1)); printf 'PASS  %s\n' "$1"
         else FAIL=$((FAIL+1)); printf 'FAIL  %s\n     out=%q rc=%d\n' "$1" "$OUT" "${RC:-9}"; fi; }

echo "== autenticacion =="
echo "dummy" > "$T/tokens/dummy.tok"
req dummy log 2>/dev/null;       check "token invalido rechazado"     '[[ "$OUT" == ERROR* ]]'
req research move "$T/para/00_entrada"; check "move sin dst rechazado" '[[ "$OUT" == ERROR* ]]'

echo "== PEP por zona =="
echo hi > "$T/para/00_entrada/factura.txt"
req research move "$T/para/00_entrada/factura.txt" "$T/para/02_areas/factura.txt"
                                 check "research NO mueve fuera de su alcance" '[[ "$OUT" == ERROR* ]]'
[ -f "$T/para/00_entrada/factura.txt" ]
                                 check "  y el origen sigue intacto"  '[ $? -eq 0 ]'
req personal  move "$T/para/00_entrada/factura.txt" "$T/para/01_proyectos/factura.txt"
                                 check "personal mueve dentro de PARA" '[[ "$OUT" == OK* ]]'
[ -f "$T/para/01_proyectos/factura.txt" ]
                                 check "  y el fichero llego"         '[ $? -eq 0 ]'
echo x > "$T/blob"
req coding    write "$T/para/02_areas/x.txt" "$T/blob"
                                 check "coding NO escribe en 02_areas" '[[ "$OUT" == ERROR* ]]'
[ ! -e "$T/para/02_areas/x.txt" ]
                                 check "  nada se escribio"           '[ $? -eq 0 ]'
req research  write "$T/para/00_entrada/nuevo.txt" "$T/blob"
                                 check "research SI escribe en 00_entrada" '[[ "$OUT" == OK* ]]'
req research  write "$T/para/01_proyectos/no.txt" "$T/blob"
                                 check "research NO escribe en 01_proyectos" '[[ "$OUT" == ERROR* ]]'

echo "== fuzzing de rutas =="
req admin move "$T/para/01_proyectos/../../../etc/passwd" "$T/extra/_staging/p"
                                 check "traversal ../ rechazado"      '[[ "$OUT" == ERROR* ]]'
ln -s /etc "$T/para/01_proyectos/escape" 2>/dev/null
req admin move "$T/para/01_proyectos/escape/passwd" "$T/extra/_staging/p"
                                 check "symlink fuera del arbol rechazado" '[[ "$OUT" == ERROR* ]]'
rm -f "$T/para/01_proyectos/escape"
SP="$T/para/01_proyectos/con espacios y-ñ.txt"; echo x > "$SP"
req admin move "$SP" "$T/extra/_staging/ok.txt"
                                 check "rutas con espacios/UTF-8 ok"  '[[ "$OUT" == OK* ]]'
[ -f "$T/extra/_staging/ok.txt" ]
                                 check "  y llego"                    '[ $? -eq 0 ]'

echo "== write + versiones + cuarentena =="
req personal write "$T/extra/_staging/blob.txt" "$T/blob"
                                 check "write en staging OK"          '[[ "$OUT" == OK* ]]'
cmp -s "$T/extra/_staging/blob.txt" "$T/blob"
                                 check "  contenido escrito intacto"  '[ $? -eq 0 ]'
req personal quarantine "$T/extra/_staging/blob.txt" "prueba"
                                 check "quarantine OK con uuid"       '[[ "$OUT" == OK\ quarantine_uuid=* ]]'
QU="${OUT#OK quarantine_uuid=}"
[ ! -e "$T/extra/_staging/blob.txt" ] && [ -n "$QU" ] && [ -d "$T/extra/_cuarentena" ]
                                 check "  origen movido a cuarentena" '[ $? -eq 0 ]'
req personal restore "$QU"
                                 check "restore devuelve el fichero"  '[[ "$OUT" == OK* ]]'
[ -f "$T/extra/_staging/blob.txt" ]
                                 check "  fichero restaurado"         '[ $? -eq 0 ]'

req admin write "$T/para/01_proyectos/ver.txt" "$T/blob"
                                 check "write admin en PARA OK (crea)" '[[ "$OUT" == OK* ]]'
LAST=""
for i in $(seq 2 12); do
    req admin write "$T/para/01_proyectos/ver.txt" "$T/blob"; LAST="$OUT"
done
                                 check "rate-limit 10 versiones/hora (11a rechazada)" '[[ "$LAST" == ERROR* ]]'
NMAN=$(find "$T/extra/_cuarentena" -name manifest 2>/dev/null | wc -l)
[ "$NMAN" -ge 10 ]
                                 check "  versiones anteriores en cuarentena ($NMAN)" '[ $? -eq 0 ]'

echo "== idempotencia (G.4) =="
TOKENP="$(cat "$T/tokens/personal.tok")"; OPID="test-op-1"
printf 'x' > "$T/para/00_entrada/a.txt"
H="$TOKENP $OPID move $(printf '%s' "$T/para/00_entrada/a.txt" | base64 -w0) $(printf '%s' "$T/para/01_proyectos/a.txt" | base64 -w0)"
OUT1="$(printf '%s\n' "$H" | socat -t 5 - "UNIX-CONNECT:$SOCK")"
OUT2="$(printf '%s\n' "$H" | socat -t 5 - "UNIX-CONNECT:$SOCK")"
printf 'y' > "$T/para/00_entrada/b.txt"
H3="$TOKENP $OPID move $(printf '%s' "$T/para/00_entrada/b.txt" | base64 -w0) $(printf '%s' "$T/para/01_proyectos/b.txt" | base64 -w0)"
OUT3="$(printf '%s\n' "$H3" | socat -t 5 - "UNIX-CONNECT:$SOCK")"
[[ "$OUT1" == OK* && "$OUT2" == OK\ idempotent-replay* ]]
                                 check "op_id repetido = replay, no re-ejecucion" '[ $? -eq 0 ]'
[[ "$OUT3" == OK\ idempotent-replay* ]] && [ ! -e "$T/para/01_proyectos/b.txt" ]
                                 check "  reintento con otros args NO re-ejecuta" '[ $? -eq 0 ]'

echo "== log append-only (campos G.1) =="
[ -s "$T/audit.log" ] && awk -F'\t' 'NF<9{e=1}END{exit e}' "$T/audit.log"
                                 check "log con campos completos"     '[ $? -eq 0 ]'
grep -q $'\tREJECT\t' "$T/audit.log" && grep -q $'\tALLOW\t' "$T/audit.log"
                                 check "  log mezcla ALLOW y REJECT"  '[ $? -eq 0 ]'

echo
printf 'RESULTADO: %d PASS · %d FAIL\n' "$PASS" "$FAIL"
[ "$FAIL" -eq 0 ]
