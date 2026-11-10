#!/bin/sh
# whisper-server con Vulkan (GPU) en HALO, junto al de CPU (05-11, planificador de GPU). Root, en HALO, desde este
# directorio. Misma versión (v1.9.5, commit comprobado) y mismo modelo que sip-whisper (install-halo.sh).
# Solo deja el binario /opt/sip-whisper/bin/whisper-server-vulkan; la unidad la instala ../gpu-halo/apply.sh.
# Paquetes nuevos (apt): libvulkan-dev, glslc, spirv-headers (solo para compilar).
# Rollback: rm /opt/sip-whisper/bin/whisper-server-vulkan /opt/sip-whisper/COMMIT-vulkan; apt remove libvulkan-dev glslc spirv-headers.
set -eu
cd "$(dirname "$0")"
VER=v1.9.5
COMMIT=d1be6fde11ac6e0407606b4e42fe72d34add8037
O=/opt/sip-whisper
DEBIAN_FRONTEND=noninteractive apt-get install -y -qq libvulkan-dev glslc spirv-headers >/dev/null
if [ ! -x "$O/bin/whisper-server-vulkan" ]; then
  T=$(mktemp -d)
  git clone -q --depth 1 --branch "$VER" https://github.com/ggml-org/whisper.cpp "$T/src"
  [ "$(git -C "$T/src" rev-parse HEAD)" = "$COMMIT" ] || { echo "ERROR: commit de $VER distinto" >&2; exit 1; }
  cmake -S "$T/src" -B "$T/build" -DCMAKE_BUILD_TYPE=Release -DGGML_VULKAN=ON -DGGML_NATIVE=ON \
        -DBUILD_SHARED_LIBS=OFF -DWHISPER_BUILD_TESTS=OFF >/dev/null
  cmake --build "$T/build" -j 16 --target whisper-server >/dev/null
  install -m 755 "$T/build/bin/whisper-server" "$O/bin/whisper-server-vulkan"
  echo "$COMMIT" > "$O/COMMIT-vulkan"
  rm -rf "$T"
fi
"$O/bin/whisper-server-vulkan" --help 2>&1 | grep -qi "inference-path" && echo "OK whisper-server-vulkan $VER ($(cut -c1-12 "$O/COMMIT-vulkan"))"
