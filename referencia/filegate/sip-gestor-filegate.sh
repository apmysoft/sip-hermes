#!/usr/bin/env bash
# sip-gestor-filegate — wrapper del Gestor de Entrada (Fase 4, Nivel 1)
# Fija socket y token del gestor para que el sudoers solo autorice ESTE
# comando y sip-gestor no pueda sustituir el token (p. ej. por admin.tok).
# La autorización real sigue siendo el PEP de /etc/filegate/policy.conf.
# Uso (como sip-gestor): sudo -n /usr/local/bin/sip-gestor-filegate <op> [args...]
#   ops PEP del gestor: plan · move <src> <dst> · quarantine <src> <motivo> · restore <uuid>
set -euo pipefail
exec /usr/local/bin/filegate-client.sh \
    /run/filegate.sock \
    /etc/filegate/tokens/gestor.tok \
    "$@"
