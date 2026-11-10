#!/bin/sh
# Piper (voz sintética local, CPU) en HALO (05-11; PROPUESTA-HERRAMIENTAS §2.4). Root, en HALO.
# Solo la herramienta de línea de órdenes y dos voces en español (sha256 de la API de Hugging Face);
# sin servicio ni puerto. Hermes no lo usa todavía (voz de salida: bloque aparte).
# Uso: /opt/sip-piper/decir "texto" salida.wav [davefx|sharvard]
# Rollback: rm -rf /opt/sip-piper
set -eu
VER=1.8.0
O=/opt/sip-piper
install -d -m 755 "$O" "$O/voces"
[ -x "$O/venv/bin/piper" ] || python3 -m venv "$O/venv"
"$O/venv/bin/pip" install -q --no-cache-dir "piper-tts==$VER"
for v in davefx/medium/es_ES-davefx-medium sharvard/medium/es_ES-sharvard-medium; do
  n=$(basename "$v")
  for ext in onnx onnx.json; do
    [ -s "$O/voces/$n.$ext" ] && continue
    curl -sSfL -o "$O/voces/$n.$ext.part" "https://huggingface.co/rhasspy/piper-voices/resolve/main/es/es_ES/$v.$ext"
    if [ "$ext" = onnx ]; then
      sha=$(curl -sL "https://huggingface.co/api/models/rhasspy/piper-voices/tree/main/es/es_ES/$(dirname "$v")" | python3 -c "import json,sys;print([f['lfs']['oid'] for f in json.load(sys.stdin) if f['path'].endswith('$n.onnx')][0])")
      echo "$sha  $O/voces/$n.$ext.part" | sha256sum -c --quiet -
    fi
    mv "$O/voces/$n.$ext.part" "$O/voces/$n.$ext"
  done
done
cat > "$O/decir" <<'SH'
#!/bin/sh
# decir "texto" salida.wav [davefx|sharvard]
set -eu
V=${3:-davefx}
printf '%s' "$1" | /opt/sip-piper/venv/bin/piper -m "/opt/sip-piper/voces/es_ES-$V-medium.onnx" -f "$2" >/dev/null 2>&1
SH
chmod 755 "$O/decir"
chmod -R a+rX "$O"
"$O/venv/bin/pip" show piper-tts | grep -E "^Version"
