#!/bin/sh
# Prueba de las herramientas de medios de HALO con datos SINTÉTICOS (06-11). Todo en CPU (la GPU solo por el
# planificador). Los modelos ya están en /opt/sip-medios/modelos (install-halo.sh); cualquier usuario: sh probar.sh
set -u
. /opt/sip-medios/entorno
T=$(mktemp -d); cd "$T"
ok() { echo "OK   $1"; }; ko() { echo "FALLO $1"; fallos=$((fallos+1)); }
fallos=0
/opt/sip-piper/decir "Esto es una prueba sintética del sistema. Hay una pausa larga después de esta frase." voz.wav
ffmpeg -loglevel error -f lavfi -i "anullsrc=r=22050:cl=mono" -t 4 silencio.wav
ffmpeg -loglevel error -i voz.wav -i silencio.wav -i voz.wav -filter_complex "[0][1][2]concat=n=3:v=0:a=1" con-pausa.wav

# Ruido + DeepFilterNet
ffmpeg -loglevel error -i voz.wav -f lavfi -i "anoisesrc=color=white:amplitude=0.08:r=22050" -filter_complex \
  "[0][1]amix=inputs=2:duration=first" -ar 48000 ruido.wav
deep-filter -o df ruido.wav >/dev/null 2>&1 && [ -s df/ruido.wav ] && ok "deep-filter (quita ruido)" || ko deep-filter

# Demucs: voz sobre un tono
ffmpeg -loglevel error -i voz.wav -f lavfi -i "sine=frequency=220:sample_rate=22050" -filter_complex \
  "[0][1]amix=inputs=2:duration=first" mezcla.wav
demucs -d cpu --two-stems=vocals -o dm mezcla.wav >/dev/null 2>&1 && [ -s dm/htdemucs/mezcla/vocals.wav ] \
  && ok "demucs (separa voz)" || ko demucs

# Cortar silencios: ffmpeg silenceremove (auto-editor descartado el 06-11: SIGSEGV como usuario normal)
ffmpeg -loglevel error -i con-pausa.wav -af "silenceremove=stop_periods=-1:stop_duration=0.7:stop_threshold=-45dB" corto.wav
a=$(ffprobe -v error -show_entries format=duration -of csv=p=0 con-pausa.wav); b=$(ffprobe -v error -show_entries format=duration -of csv=p=0 corto.wav 2>/dev/null || echo 0)
python3 -c "import sys; sys.exit(0 if 0 < float('$b') < float('$a') - 2 else 1)" && ok "quitar silencios ($a s -> $b s)" || ko silencios

# PySceneDetect: vídeo de 3 colores
ffmpeg -loglevel error -f lavfi -i "color=red:s=320x240:d=2" -f lavfi -i "color=green:s=320x240:d=2" \
  -f lavfi -i "color=blue:s=320x240:d=2" -filter_complex "[0][1][2]concat=n=3:v=1:a=0" colores.mp4
n=$(scenedetect -i colores.mp4 detect-content list-scenes -n 2>/dev/null | grep -cE '^ [|] +[0-9]+ ')
[ "$n" -ge 3 ] && ok "scenedetect ($n escenas)" || ko "scenedetect ($n escenas)"

# rembg (BiRefNet): un círculo sobre fondo
python3 -c "
from PIL import Image, ImageDraw
im=Image.new('RGB',(512,512),(30,120,200)); ImageDraw.Draw(im).ellipse((128,128,384,384),fill=(240,200,40)); im.save('circulo.png')"
rembg i -m birefnet-general circulo.png sin-fondo.png >/dev/null 2>&1 && python3 -c "
from PIL import Image; a=Image.open('sin-fondo.png').getchannel('A'); import sys
sys.exit(0 if a.getpixel((5,5))<50 and a.getpixel((256,256))>200 else 1)" && ok "rembg birefnet (quita fondo)" || ko rembg

# Kokoro (voz natural, español)
python3 -c "
from kokoro import KPipeline; import soundfile as sf, numpy as np
p=KPipeline(lang_code='e', repo_id='hexgrad/Kokoro-82M', device='cpu')
a=np.concatenate([x[2] for x in p('Hola, esto es una prueba sintética de voz.', voice='ef_dora')])
sf.write('kokoro.wav', a, 24000)" >/dev/null 2>&1 && [ -s kokoro.wav ] && ok "kokoro (voz es)" || ko kokoro

# Docling: PDF con tabla -> Markdown
printf '= Factura de prueba\n#table(columns: 2, [Concepto], [Importe], [Luz], [42,10 €])\n' > f.typ
typst compile f.typ f.pdf && docling --to md --device cpu --output dl f.pdf >/dev/null 2>&1 && grep -q "42,10" dl/f.md \
  && ok "docling (PDF -> Markdown con tabla)" || ko docling

# OCRmyPDF: PDF de imagen -> PDF con texto
pdftoppm -r 150 -png f.pdf pag && img2pdf() { python3 -c "
from PIL import Image; Image.open('pag-1.png').convert('RGB').save('escaneado.pdf')"; }; img2pdf
ocrmypdf -q -l spa escaneado.pdf ocr.pdf >/dev/null 2>&1 && pdftotext ocr.pdf - | grep -qi "factura" \
  && ok "ocrmypdf (escaneado -> texto)" || ko ocrmypdf

# Subtítulos: Whisper (CPU) en SRT + ffmpeg
curl -s -F file=@voz.wav -F response_format=srt -F language=es http://${HALO_TAILNET_IP}:8178/inference > voz.srt
ffmpeg -loglevel error -f lavfi -i "color=black:s=640x360:d=6" -i voz.wav -vf "subtitles=voz.srt" -shortest sub.mp4 \
  && grep -q -- "-->" voz.srt && ok "subtítulos (Whisper SRT + ffmpeg)" || ko subtitulos

# exiftool
exiftool -q -Artist="SIP prueba" circulo.png >/dev/null 2>&1; exiftool -s3 -Artist circulo.png | grep -q "SIP prueba" \
  && ok "exiftool" || ko exiftool

cd /; rm -rf "$T"
echo "fallos: $fallos"
