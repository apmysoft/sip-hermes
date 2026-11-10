#!/bin/sh
# llama.cpp + llama-swap en HALO (05-11): sustituto de Ollama, como en Neo (sip-config/llm-neo/).
# Instala usuario, directorios y binarios verificados por sha256. NO arranca nada ni toca Ollama.
# Uso: sudo sh install-halo.sh <dir con los .tar.gz descargados>
# Rollback: systemctl disable --now llama-swap; userdel sip-llm; rm -rf /var/lib/sip-llm (ver README).
set -eu
D=${1:?dir con las descargas}
L=/var/lib/sip-llm
B=b12110   # = v0.9.0 estable de llama.cpp (nightly-tag.txt)
S=270      # llama-swap
cd "$D"
sha256sum -c - <<EOF
664b5c218ec9a38d1e7b543bae7407dc62a4051ba09ddc51bd29f68ee77da674  llama-$B-bin-ubuntu-rocm-10.0-x64.tar.gz
a5d741940956ec62e8783aee7e5a4c7c761af867d6f027c3277a51e1a3ac59b0  llama-$B-bin-ubuntu-vulkan-x64.tar.gz
b7f89c944e83e30c438846f8c513b9e64fb7bdcec1e3f47ed8be31a94d688a09  llama-swap_${S}_linux_amd64.tar.gz
EOF
id sip-llm >/dev/null 2>&1 || useradd --system --home-dir $L --no-create-home --shell /usr/sbin/nologin sip-llm
usermod -aG render,video sip-llm
install -d -o root -g sip-llm -m 750 $L $L/bin $L/models
install -d -o sip-llm -g sip-llm -m 750 $L/staging $L/cache
for v in vulkan rocm; do
  rm -rf "$L/llama-$B-$v"; install -d -o root -g root -m 755 "$L/llama-$B-$v"
  tar -xzf "llama-$B-bin-ubuntu-$v$( [ $v = rocm ] && echo -10.0 )-x64.tar.gz" -C "$L/llama-$B-$v" --strip-components=1 --no-same-owner
done
tar -xzf "llama-swap_${S}_linux_amd64.tar.gz" -C $L/bin llama-swap --no-same-owner
chown root:root $L/bin/llama-swap; chmod 755 $L/bin/llama-swap
chmod 755 $L $L/bin   # los binarios los ejecuta sip-llm; models/ sigue 750
echo "== verificación"
$L/bin/llama-swap --version 2>&1 | head -1
for v in vulkan rocm; do printf "%s: " $v; sudo -u sip-llm $L/llama-$B-$v/llama-server --version 2>&1 | grep -E "^version" ; done
sudo -u sip-llm $L/llama-$B-vulkan/llama-server --list-devices 2>&1 | grep -E "Vulkan0|RADV" | head -1
