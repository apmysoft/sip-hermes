#!/bin/sh
# Parches de seguridad automáticos en Neo (root). Copia previa en $B.
# Rollback: apt-get purge unattended-upgrades python3-distro-info;
#   rm /etc/apt/apt.conf.d/52sip-unattended-upgrades /etc/apt/apt.conf.d/20auto-upgrades
set -eu
cd "$(dirname "$0")"
B=/root/sip-agent-backups/$(date +%F)/fase9-actualizaciones-$(date +%H%M%S)
install -d -m 700 "$B"
cp -a /etc/apt/apt.conf.d "$B/"

DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends unattended-upgrades
install -o root -g root -m 0644 52sip-unattended-upgrades 20auto-upgrades /etc/apt/apt.conf.d/

# Verificación: la configuración efectiva solo admite noble-security y excluye lo previsto.
apt-config dump | grep -E '^Unattended-Upgrade::(Allowed-Origins|Origins-Pattern|Package-Blacklist|Automatic-Reboot)'
apt-config dump | grep -q 'Allowed-Origins::' && { echo "FALLO: quedan Allowed-Origins"; exit 1; }
LC_ALL=C unattended-upgrade --dry-run --debug 2>&1 | grep -E 'Allowed origins|Initial blacklist|Packages that will be upgraded|No packages found' || true
echo "RESULTADO: OK. Copia previa en $B"
