#!/bin/sh
# Instala whisper-server (whisper.cpp v1.9.5, CPU) en HALO como servicio sip-whisper. Root, en HALO, desde
# este directorio. Paquetes nuevos: cmake, ffmpeg (apt). Rollback: systemctl disable --now sip-whisper;
#   rm /etc/systemd/system/sip-whisper.service; rm -rf /opt/sip-whisper; userdel sip-whisper;
#   apt remove cmake ffmpeg (si no se usan para otra cosa).
set -eu
cd "$(dirname "$0")"
VER=v1.9.5
MODEL=ggml-large-v3-turbo-q5_0.bin
MODEL_SHA=394221709cd5ad1f40c46e6031ca61bce88931e6e088c188294c6d5a55ffa7e2
O=/opt/sip-whisper
DEBIAN_FRONTEND=noninteractive apt-get install -y -qq cmake ffmpeg >/dev/null
id sip-whisper >/dev/null 2>&1 || useradd --system --home-dir /nonexistent --shell /usr/sbin/nologin sip-whisper
install -d -m 755 "$O" "$O/bin" "$O/models"
if [ ! -x "$O/bin/whisper-server" ]; then
  T=$(mktemp -d)
  git clone -q --depth 1 --branch "$VER" https://github.com/ggml-org/whisper.cpp "$T/src"
  git -C "$T/src" rev-parse HEAD > "$O/COMMIT"
  cmake -S "$T/src" -B "$T/build" -DCMAKE_BUILD_TYPE=Release -DGGML_NATIVE=ON -DBUILD_SHARED_LIBS=OFF \
        -DWHISPER_BUILD_TESTS=OFF >/dev/null
  cmake --build "$T/build" -j 16 --target whisper-server >/dev/null
  install -m 755 "$T/build/bin/whisper-server" "$O/bin/whisper-server"
  rm -rf "$T"
fi
if ! echo "$MODEL_SHA  $O/models/$MODEL" | sha256sum -c --status - 2>/dev/null; then
  curl -sSfL -o "$O/models/$MODEL.part" "https://huggingface.co/ggerganov/whisper.cpp/resolve/main/$MODEL"
  echo "$MODEL_SHA  $O/models/$MODEL.part" | sha256sum -c --quiet -
  mv "$O/models/$MODEL.part" "$O/models/$MODEL"
fi
chmod -R a+rX "$O"
install -m 644 sip-whisper.service /etc/systemd/system/sip-whisper.service
systemctl daemon-reload
systemctl enable --now sip-whisper.service
for i in $(seq 60); do curl -s -o /dev/null --max-time 2 http://${HALO_TAILNET_IP}:8178/ && break; sleep 2; done
echo "versión $VER commit $(cat $O/COMMIT | cut -c1-12); estado: $(systemctl is-active sip-whisper)"
ss -lnt | grep 8178
