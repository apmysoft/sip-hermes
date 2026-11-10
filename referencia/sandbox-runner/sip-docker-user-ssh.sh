#!/bin/sh
# Reaplica en DOCKER-USER la excepcion del backend SSH del runner sandbox.
#
# Contexto (Bloque 4a): el SYN sip->sandbox:2222 lo acepta inet sip-zones
# (priority -50), pero Docker lo mataria despues en su cadena DOCKER-INTERNAL
# (priority 0: "saddr != 172.30/24 oifname br-sandbox drop", porque el filtro
# corre antes del masquerade y el origen aun es 172.29.x). Un ACCEPT en
# DOCKER-USER (cadena vacia que Docker ejecuta primero en filter FORWARD y que
# no vacia nunca) termina el hook y salta DOCKER-INTERNAL.
#
# La regla es runtime: no sobrevive a un reboot del host. Esta unidad la
# reinserta tras docker.service (la cadena la crea dockerd). Idempotente.
set -eu

RULE_IN='iptables -t filter -C DOCKER-USER -s 172.29.0.0/24 -d 172.30.0.0/24 -p tcp --dport 2222 -j ACCEPT'
RULE_ADD='iptables -t filter -I DOCKER-USER 1 -s 172.29.0.0/24 -d 172.30.0.0/24 -p tcp --dport 2222 -j ACCEPT'

if $RULE_IN 2>/dev/null; then
    echo "sip-docker-user-ssh: regla ya presente"
    exit 0
fi

$RULE_ADD
echo "sip-docker-user-ssh: regla insertada"
