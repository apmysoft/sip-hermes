#!/bin/sh
# Prueba de las 11 operaciones de sip-medios con datos SINTÉTICOS (06-11). Sin root.
# Uso: sh probar-api.sh [URL]   (por defecto, por llama-swap: http://${HALO_TAILNET_IP}:11434/upstream/medios)
set -u
U=${1:-http://${HALO_TAILNET_IP}:11434/upstream/medios}
T=$(mktemp -d); cd "$T"; f=0
ok() { echo "OK    $1"; }; ko() { echo "FALLO $1: $(head -c 200 r.out 2>/dev/null)"; f=$((f+1)); }
pide() { op=$1; shift; c=$(curl -s -o r.out -w '%{http_code}' --max-time 1800 "$@" "$U/op/$op"); [ "$c" = 200 ]; }
/opt/sip-piper/decir "Prueba sintética del servicio de medios. Después hay una pausa larga." voz.wav
ffmpeg -loglevel error -f lavfi -i "anullsrc=r=22050:cl=mono" -t 3 s.wav
ffmpeg -loglevel error -i voz.wav -i s.wav -i voz.wav -filter_complex "[0][1][2]concat=n=3:v=0:a=1" pausa.wav
ffmpeg -loglevel error -f lavfi -i "color=red:s=320x240:d=2" -f lavfi -i "color=blue:s=320x240:d=2" -i voz.wav \
  -filter_complex "[0][1]concat=n=2:v=1:a=0[v]" -map "[v]" -map 2:a -shortest video.mp4
python3 -c "from PIL import Image, ImageDraw; im=Image.new('RGB',(256,256),(30,120,200)); ImageDraw.Draw(im).ellipse((64,64,192,192),fill=(240,200,40)); im.save('img.png')"
printf '= Factura de prueba\n#table(columns: 2, [Concepto], [Importe], [Luz], [42,10 €])\n' > f.typ && typst compile f.typ f.pdf
pdftoppm -r 150 -png f.pdf pag && python3 -c "from PIL import Image; Image.open('pag-1.png').convert('RGB').save('esc.pdf')"
pide ruido -F file=@voz.wav && ok ruido || ko ruido
pide silencios -F file=@pausa.wav && ok silencios || ko silencios
pide separar -F file=@voz.wav -F pista=voz && ok separar || ko separar
pide escenas -F file=@video.mp4 && grep -q "Scene" r.out && ok escenas || ko escenas
pide subtitulos -F file=@video.mp4 -F idioma=es && grep -q -- "-->" r.out && ok subtitulos || ko subtitulos
pide fondo -F file=@img.png && ok fondo || ko fondo
pide voz -F "texto=Hola, esto es una prueba." && ok voz || ko voz
pide ocr -F file=@esc.pdf -F salida=texto && grep -qi factura r.out && ok ocr || ko ocr
pide docling -F file=@f.pdf && grep -q "42,10" r.out && ok docling || ko docling
pide documento -F "texto=# Informe
Texto de **prueba**." -F formato=pdf && head -c 4 r.out | grep -q "%PDF" && ok documento || ko documento
pide diagrama -F "texto=flowchart LR
 A-->B" -F tipo=mermaid && grep -q "<svg" r.out && ok diagrama || ko diagrama
c=$(curl -s -o r.out -w '%{http_code}' -F "texto=x" "$U/op/rm-rf"); [ "$c" = 404 ] && ok "operación desconocida -> 404" || ko "operación desconocida ($c)"
c=$(curl -s -o r.out -w '%{http_code}' -F file=@img.png "$U/op/ruido"); [ "$c" = 400 ] && ok "tipo no admitido -> 400" || ko "tipo no admitido ($c)"
cd /; rm -rf "$T"; echo "fallos: $f"
