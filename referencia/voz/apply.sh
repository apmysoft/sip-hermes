#!/bin/sh
# Notas de voz por Telegram (05-11). Root, en Neo, desde sip-config/voz del checkout.
# Usuario sip-voz (sin login, en sip-wol para pedir el despertar de HALO), buzón /var/lib/sip-voz
# (dueño 978 = sip-gateway, grupo sip-voz, 2770), puente sip-voz-bridge (.path) y gateway con /voz.
# Rollback: systemctl disable --now sip-voz-bridge.path; rm /etc/systemd/system/sip-voz-bridge.*;
#   rm /usr/local/sbin/sip-voz-bridge.py; cp $B/{docker-compose.yml,sip_gateway.py} ~usuario/sip-fase7-gateway/;
#   (cd ~usuario/sip-fase7-gateway && docker compose up -d --force-recreate); rm -rf /var/lib/sip-voz; userdel sip-voz.
set -eu
cd "$(dirname "$0")"
G=/home/usuario/sip-fase7-gateway
B=/root/sip-agent-backups/$(date +%F)/voz
install -d -m 700 "$B"
cp -p "$G/docker-compose.yml" "$G/sip_gateway.py" "$B/"
getent group sip-voz >/dev/null || groupadd --system sip-voz
id sip-voz >/dev/null 2>&1 || useradd --system --gid sip-voz --groups sip-wol --home-dir /nonexistent --shell /usr/sbin/nologin sip-voz
install -d -m 2770 -o 978 -g sip-voz /var/lib/sip-voz /var/lib/sip-voz/requests /var/lib/sip-voz/results
install -o root -g root -m 755 sip-voz-bridge.py /usr/local/sbin/sip-voz-bridge.py
install -o root -g root -m 644 sip-voz-bridge.path sip-voz-bridge.service /etc/systemd/system/
systemctl daemon-reload
systemctl enable --now sip-voz-bridge.path
install -o usuario -g usuario -m 644 ../gateway/sip_gateway.py "$G/sip_gateway.py"
install -o usuario -g usuario -m 664 ../gateway/docker-compose.yml "$G/docker-compose.yml"
(cd "$G" && docker compose config -q && docker compose up -d --force-recreate)
sleep 5
docker logs --since 20s sip-gateway 2>&1 | grep -E "arrancado|Error|Traceback" | cut -c1-120
docker exec sip-gateway sh -c 'test -w /voz/requests && test -w /voz/results && echo "gateway: /voz escribible"'
echo "path: $(systemctl is-active sip-voz-bridge.path)"
