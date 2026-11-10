#!/bin/sh
# Herramientas de medios, documentos y texto en HALO (06-11, PROPUESTA-HERRAMIENTAS §1-§2). Root, en HALO.
# Todo en /opt/sip-medios (root, lectura para todos), salvo los paquetes de apt y typst en /usr/local/bin.
# Uso: sudo sh install-halo.sh && sh probar.sh   ·   Entorno: . /opt/sip-medios/entorno
# Por defecto todo va en CPU: la GPU solo por el planificador (llama-swap), para no chocar con el modelo de texto.
# Rollback: rm -rf /opt/sip-medios /usr/local/bin/typst; apt remove los paquetes de abajo.
set -eu
cd "$(dirname "$0")"
O=/opt/sip-medios
DEBIAN_FRONTEND=noninteractive apt-get install -y -qq pandoc graphviz libimage-exiftool-perl espeak-ng \
  tesseract-ocr tesseract-ocr-spa tesseract-ocr-eng ocrmypdf qpdf poppler-utils >/dev/null
install -d -m 755 "$O" "$O/bin" "$O/npm" "$O/modelos"
install -m 644 entorno "$O/entorno"
T=$(mktemp -d)
# Typst (digest publicado en el release)
curl -sSfL -o "$T/typst.tar.xz" https://github.com/typst/typst/releases/download/v0.15.1/typst-x86_64-unknown-linux-musl.tar.xz
echo "a6d077d0a95eed5a2eba715b2dae06be954f624ccbf85758a03f389ded33118c  $T/typst.tar.xz" | sha256sum -c --quiet -
tar -C "$T" -xJf "$T/typst.tar.xz"; install -m 755 "$T"/typst-x86_64-unknown-linux-musl/typst /usr/local/bin/typst
# DeepFilterNet (binario estático; el release de 2023 no publica sha256: registrado el 06-11)
curl -sSfL -o "$T/deep-filter" https://github.com/Rikorose/DeepFilterNet/releases/download/v0.5.6/deep-filter-0.5.6-x86_64-unknown-linux-musl
echo "70775e251eee44c0f2451a1e833326cf8bcbbe304d3e7cd12851e6fce72ef7da  $T/deep-filter" | sha256sum -c --quiet -
install -m 755 "$T/deep-filter" "$O/bin/deep-filter"
rm -rf "$T"
# Marp y Mermaid (node 18 del sistema: mermaid-cli 11.x; la 12 pide node 22)
(cd "$O/npm" && HOME=/root PUPPETEER_CACHE_DIR="$O/npm/.puppeteer" npm install --prefix "$O/npm" --no-fund \
  --no-audit --loglevel=error @marp-team/marp-cli@4.5.1 @mermaid-js/mermaid-cli@11.17.1)
# Python: PyTorch ROCm (misma versión que ComfyUI) y herramientas
[ -x "$O/venv/bin/python" ] || python3 -m venv "$O/venv"
"$O/venv/bin/pip" install -q --no-cache-dir --index-url https://download.pytorch.org/whl/rocm7.2 \
  "torch==2.14.1+rocm7.2" "torchaudio==2.11.0+rocm7.2" "torchvision==0.29.1+rocm7.2"
"$O/venv/bin/pip" install -q --no-cache-dir "rembg[cpu,cli]==2.0.86" "scenedetect[opencv-headless]==0.7.2" \
  "demucs==4.1.0" "kokoro==0.9.4" "docling==2.148.0" "soundfile==0.14.0"
# Modelos (primer uso, como root, a $O/modelos). HF_HUB_OFFLINE del entorno se quita solo aquí.
. "$O/entorno"; export HF_HUB_OFFLINE=0 HOME=/root
T=$(mktemp -d); cd "$T"
/opt/sip-piper/decir "Prueba sintética." v.wav
demucs -d cpu --two-stems=vocals -o dm v.wav >/dev/null 2>&1
python3 -c "from PIL import Image; Image.new('RGB',(64,64),(9,9,9)).save('i.png')"; rembg i -m birefnet-general i.png o.png >/dev/null 2>&1
python3 -c "from kokoro import KPipeline; KPipeline(lang_code='e', repo_id='hexgrad/Kokoro-82M', device='cpu')('Hola.', voice='ef_dora').__next__()" >/dev/null 2>&1
printf '= P\n' > p.typ && typst compile p.typ p.pdf && docling --to md --device cpu --output d p.pdf >/dev/null 2>&1
cd /; rm -rf "$T"
chmod -R a+rX "$O"
echo "instalado; prueba: sh probar.sh"
