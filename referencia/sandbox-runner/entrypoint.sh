#!/bin/sh
# Arranque del runner sandbox: host keys persistentes en volumen, /run/sshd en
# tmpfs (contenedor read_only), ruta de vuelta a la red sip y sshd en primer
# plano con logs a stderr.
#
# La red sandbox es internal=true: Docker no instala ruta por defecto, así que
# el runner no podría responder a conexiones iniciadas desde la red sip (p. ej.
# el SSH de Hermes). Se añade una ruta explícita solo hacia 172.29/24 vía la
# puerta del bridge; el egress del runner sigue siendo cero: las redes
# internal no NATan hacia fuera y nftables hace drop del origen 172.30.
# Requiere NET_ADMIN (la única capability del contenedor; ver compose).
set -eu

mkdir -p /run/sshd

GATEWAY=$(ip route | awk "/default/ {print \$3; exit}")
if [ -n "$GATEWAY" ]; then
    ip route replace 172.29.0.0/24 via "$GATEWAY"
else
    # internal=true: sin ruta por defecto; la puerta es el primer usable de la subred
    ip route replace 172.29.0.0/24 via "${SB_GATEWAY:-172.30.0.1}"
fi

if [ ! -f /etc/ssh/hostkeys/ssh_host_ed25519_key ]; then
    echo "[entrypoint] generando host key ed25519 (primera vez)" >&2
    ssh-keygen -t ed25519 -N "" -f /etc/ssh/hostkeys/ssh_host_ed25519_key -q
fi
chmod 700 /etc/ssh/hostkeys
chmod 600 /etc/ssh/hostkeys/ssh_host_ed25519_key

# authorized_keys llega montado solo lectura (volumen runner-authkeys):
# root:root 644, correcto para StrictModes. No se toca (fs de solo lectura).
chown sandbox:sandbox /workspace 2>/dev/null || true

exec /usr/sbin/sshd -D -e -f /etc/ssh/sshd_config
