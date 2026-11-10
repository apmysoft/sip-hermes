#!/bin/sh
# LAN fuera de los puertos de Docker (05-11). Root, en Neo, desde este directorio.
# Fase 1 (este script): instala el candidato con reversión automática a los 5 min y deja el temporizador
# en marcha. Fase 2 (fuera): probar desde HALO por LAN (debe cerrar) y por tailnet (debe abrir); si todo
# va bien: systemctl stop sip-nft-rollback-lan.timer. Si no se para, vuelve solo el firewall anterior.
# Rollback manual: cp $B/nftables-sip.nft-pre /etc/nftables-sip.nft && systemctl restart nft-sip-zones
set -eu
cd "$(dirname "$0")"
B=/root/sip-agent-backups/$(date +%F)/lan-docker
UNIT=sip-nft-rollback-lan
nft -c -f nftables-sip.candidate.nft
install -d -m 700 "$B"
cp -p /etc/nftables-sip.nft "$B/nftables-sip.nft-pre"
nft list table inet sip-zones > "$B/sip-zones-vivo-pre.txt"
systemd-run --quiet --on-active=300 --unit="$UNIT" /bin/sh -c \
  "cp -p $B/nftables-sip.nft-pre /etc/nftables-sip.nft; systemctl restart nft-sip-zones"
install -o root -g root -m 644 nftables-sip.candidate.nft /etc/nftables-sip.nft
systemctl restart nft-sip-zones
nft list chain inet sip-zones forward | grep -c "sip-drop-lan-docker" >/dev/null
echo "Instalado. Reversión automática en 5 min salvo: systemctl stop $UNIT.timer"
