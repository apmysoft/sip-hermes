#!/bin/sh
# Estadística AGREGADA de PARA para decidir qué iría a Paperless y qué a la biblioteca (06-11). PREPARADO, NO
# EJECUTADO: lee metadatos de todo ${PARA_ROOT} (regla 4); lo lanza el usuario o lo autoriza.
# Salida: solo recuentos por carpeta de primer nivel, tipo, tamaño y páginas de PDF. Ningún nombre de fichero.
# Uso (Neo): sudo sh para-estadisticas.sh > /root/para-estadisticas.txt
set -eu
P=${PARA_ROOT}
for top in 00_entrada 01_proyectos 02_areas 03_recursos 04_archivo; do
  [ -d "$P/$top" ] || continue
  echo "== $top"
  find "$P/$top" -type f -printf '%s %f\n' 2>/dev/null | python3 -c '
import sys, collections, os
GRUPOS = {"pdf": "pdf", "epub": "ebook", "mobi": "ebook", "azw": "ebook", "azw3": "ebook", "fb2": "ebook", "djvu": "ebook",
          "cbz": "cómic", "cbr": "cómic", "doc": "ofimática", "docx": "ofimática", "odt": "ofimática", "xls": "ofimática",
          "xlsx": "ofimática", "ods": "ofimática", "ppt": "ofimática", "pptx": "ofimática", "txt": "texto", "md": "texto",
          "jpg": "imagen", "jpeg": "imagen", "png": "imagen", "heic": "imagen", "tif": "imagen", "tiff": "imagen",
          "mp3": "audio", "m4a": "audio", "flac": "audio", "ogg": "audio", "wav": "audio", "mp4": "vídeo", "mkv": "vídeo",
          "avi": "vídeo", "mov": "vídeo", "zip": "comprimido", "rar": "comprimido", "7z": "comprimido", "eml": "correo", "msg": "correo"}
n = collections.Counter(); b = collections.Counter()
for l in sys.stdin.buffer:  # bytes: hay nombres que no son UTF-8 (09-11); solo se usa la extensión
    t, nombre = l.rstrip(b"\n").split(b" ", 1)
    g = GRUPOS.get(os.path.splitext(nombre)[1].decode("utf-8", "replace").lower().lstrip("."), "otros")
    n[g] += 1; b[g] += int(t)
for g, c in n.most_common():
    print(f"  {g:11s} {c:7d} ficheros {b[g]/1e9:8.2f} GB")'
  # PDF por número de páginas (documento corto frente a libro), sin nombres
  find "$P/$top" -type f -iname '*.pdf' -print0 2>/dev/null | xargs -0 -r -n 1 pdfinfo 2>/dev/null \
    | awk '/^Pages:/ {p=$2; if (p<=5) a++; else if (p<=30) b++; else if (p<=100) c++; else d++}
           END {printf "  pdf por páginas: 1-5 %d · 6-30 %d · 31-100 %d · >100 %d\n", a, b, c, d}'
done
