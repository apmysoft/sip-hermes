#!/opt/sip-medios/venv/bin/python
"""sip-medios: herramientas de medios, documentos y texto de HALO por HTTP (06-11). Usuario sip-medios.

Solo 127.0.0.1:8190. Lo arranca llama-swap bajo demanda (modelo `medios`, grupo de CPU) y se llega por
http://${HALO_TAILNET_IP}:11434/upstream/medios/. Operaciones FIJAS, sin intérprete de órdenes: cada una es una
lista de argumentos con rutas propias en un directorio temporal. Todo en CPU (la GPU, por el planificador).

  POST /op/<operacion>   multipart: `file` (si la operación lo usa), `texto` (si lo usa) y opciones
  GET  /                 lista de operaciones (también es la comprobación de salud de llama-swap)

Respuesta: el fichero resultado (cabecera X-Sip-Fichero con el nombre sugerido) o JSON {"error": ...}.
"""
import cgi
import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

PUERTO = int(os.environ.get("SIP_MEDIOS_PUERTO", "8190"))
MAX_BYTES = 250 * 1024 * 1024
WHISPER = "http://${HALO_TAILNET_IP}:8178/inference"
ENTORNO = {**os.environ, "PATH": "/opt/sip-medios/bin:/opt/sip-medios/venv/bin:/opt/sip-medios/npm/node_modules/.bin:"
           "/usr/local/bin:/usr/bin:/bin", "HF_HOME": "/opt/sip-medios/modelos/hf", "U2NET_HOME": "/opt/sip-medios/modelos/u2net",
           "TORCH_HOME": "/opt/sip-medios/modelos/torch", "PUPPETEER_CACHE_DIR": "/opt/sip-medios/npm/.puppeteer",
           "HF_HUB_OFFLINE": "1", "OMP_NUM_THREADS": "8", "HOME": "/tmp", "XDG_CACHE_HOME": "/tmp/cache"}
_turno = threading.Semaphore(2)  # como mucho 2 operaciones a la vez (CPU compartida con el worker)

AUDIO = {".mp3", ".m4a", ".aac", ".wav", ".flac", ".ogg", ".opus", ".oga", ".webm", ".mp4", ".mkv", ".mov", ".avi", ".m4v"}
VIDEO = {".mp4", ".mkv", ".mov", ".avi", ".m4v", ".webm"}
IMAGEN = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tif", ".tiff"}
PDF = {".pdf"}
DOC = {".pdf", ".docx", ".pptx", ".xlsx", ".html", ".htm", ".md", ".png", ".jpg", ".jpeg"}


def ffmpeg(*a):
    return ["ffmpeg", "-nostdin", "-loglevel", "error", "-y", *a]


def op_ruido(d, e, o):
    run(["deep-filter", "-o", d, e], 900)
    return os.path.join(d, os.path.basename(e)), ".wav"


def op_silencios(d, e, o):
    s = os.path.join(d, "salida.wav")
    run(ffmpeg("-i", e, "-af", "silenceremove=stop_periods=-1:stop_duration=0.7:stop_threshold=-45dB", s), 900)
    return s, ".wav"


def op_separar(d, e, o):
    run(["demucs", "-d", "cpu", "--two-stems=vocals", "-o", d, e], 3600)
    base = os.path.splitext(os.path.basename(e))[0]
    return os.path.join(d, "htdemucs", base, "no_vocals.wav" if o.get("pista") == "musica" else "vocals.wav"), ".wav"


def op_escenas(d, e, o):
    run(["scenedetect", "-i", e, "-o", d, "detect-content", "list-scenes", "-f", "escenas.csv"], 1800)
    return os.path.join(d, "escenas.csv"), ".csv"


def _srt(d, e, idioma):
    wav = os.path.join(d, "audio.wav")
    run(ffmpeg("-i", e, "-vn", "-ac", "1", "-ar", "16000", wav), 900)
    srt = os.path.join(d, "subtitulos.srt")
    run(["curl", "-sSf", "--max-time", "3600", "-F", f"file=@{wav}", "-F", "response_format=srt",
         "-F", f"language={idioma}", "-o", srt, WHISPER], 3700)
    return srt


def op_subtitulos(d, e, o):
    srt = _srt(d, e, o.get("idioma") or "auto")
    if o.get("incrustar") != "si" or os.path.splitext(e)[1].lower() not in VIDEO:
        return srt, ".srt"
    s = os.path.join(d, "subtitulado.mp4")
    run(ffmpeg("-i", e, "-vf", f"subtitles={srt}", "-c:a", "copy", s), 3600)
    return s, ".mp4"


def op_fondo(d, e, o):
    s = os.path.join(d, "sin-fondo.png")
    run(["rembg", "i", "-m", "birefnet-general", e, s], 600)
    return s, ".png"


def op_voz(d, e, o):
    texto = o["texto"]
    s = os.path.join(d, "voz.wav")
    codigo = ("import sys, numpy as np, soundfile as sf\nfrom kokoro import KPipeline\n"
              "p = KPipeline(lang_code='e', repo_id='hexgrad/Kokoro-82M', device='cpu')\n"
              "t = open(sys.argv[1], encoding='utf-8').read()\n"
              "a = np.concatenate([x[2] for x in p(t, voice=sys.argv[3])])\nsf.write(sys.argv[2], a, 24000)\n")
    tx = os.path.join(d, "texto.txt")
    open(tx, "w", encoding="utf-8").write(texto)
    voz = o.get("voz") if o.get("voz") in ("ef_dora", "em_alex", "em_santa") else "ef_dora"
    run([sys.executable, "-c", codigo, tx, s, voz], 900)
    return s, ".wav"


def op_ocr(d, e, o):
    s = os.path.join(d, "ocr.pdf")
    # 10-11: 12 hilos (antes todos, 32): un PDF grande agotaba los 12 GB del servicio (OOM en la ventana del índice).
    run(["ocrmypdf", "-q", "-l", "spa+eng", "--skip-text", "--jobs", "12", "--output-type", "pdf", e, s], 1800)
    if o.get("salida") == "texto":
        t = os.path.join(d, "ocr.txt")
        run(["pdftotext", "-layout", s, t], 300)
        return t, ".txt"
    return s, ".pdf"


def op_docling(d, e, o):
    run(["docling", "--to", "md", "--device", "cpu", "--output", d, e], 1800)
    return os.path.join(d, os.path.splitext(os.path.basename(e))[0] + ".md"), ".md"


def op_documento(d, e, o):
    """Markdown (campo texto) -> pdf (pandoc -> typst), docx, odt, html o pptx; presentación -> pdf con Marp."""
    md = os.path.join(d, "doc.md")
    open(md, "w", encoding="utf-8").write(o["texto"])
    formato = o.get("formato") or "pdf"
    if formato == "presentacion":
        s = os.path.join(d, "presentacion.pdf")
        run(["marp", "--no-stdin", "--pdf", md, "-o", s], 300, entorno_extra={"HOME": d})
        return s, ".pdf"
    if formato == "pdf":
        # Sin -s: la plantilla de typst de pandoc 3.1.3 no compila con typst 0.15; preámbulo propio.
        cuerpo = os.path.join(d, "cuerpo.typ")
        run(["pandoc", md, "-t", "typst", "-o", cuerpo], 120)
        typ = os.path.join(d, "doc.typ")
        with open(typ, "w", encoding="utf-8") as f:
            f.write('#set page(paper: "a4", margin: 2.2cm)\n#set text(lang: "es", size: 11pt)\n'
                    '#set par(justify: true)\n#include "cuerpo.typ"\n')
        s = os.path.join(d, "doc.pdf")
        run(["typst", "compile", typ, s], 300)
        return s, ".pdf"
    if formato not in ("docx", "odt", "html", "pptx"):
        raise ValueError("formato: pdf, docx, odt, html, pptx o presentacion")
    s = os.path.join(d, f"doc.{formato}")
    run(["pandoc", md, "-s", "-o", s], 120)
    return s, "." + formato


def op_diagrama(d, e, o):
    tipo = o.get("tipo") or "mermaid"
    fmt = "png" if o.get("formato") == "png" else "svg"
    s = os.path.join(d, f"diagrama.{fmt}")
    if tipo == "graphviz":
        src = os.path.join(d, "d.dot")
        open(src, "w", encoding="utf-8").write(o["texto"])
        run(["dot", f"-T{fmt}", src, "-o", s], 120)
    elif tipo == "mermaid":
        src = os.path.join(d, "d.mmd")
        open(src, "w", encoding="utf-8").write(o["texto"])
        pp = os.path.join(d, "pp.json")
        open(pp, "w").write('{"args":["--no-sandbox"]}')
        run(["mmdc", "-p", pp, "-i", src, "-o", s], 180, entorno_extra={"HOME": d})
    else:
        raise ValueError("tipo: mermaid o graphviz")
    return s, "." + fmt


# operacion: (función, extensiones de entrada admitidas o None si no lleva fichero, usa campo texto)
OPS = {
    "ruido": (op_ruido, AUDIO, False), "silencios": (op_silencios, AUDIO, False),
    "separar": (op_separar, AUDIO, False), "escenas": (op_escenas, VIDEO, False),
    "subtitulos": (op_subtitulos, AUDIO | VIDEO, False), "fondo": (op_fondo, IMAGEN, False),
    "voz": (op_voz, None, True), "ocr": (op_ocr, PDF, False), "docling": (op_docling, DOC, False),
    "documento": (op_documento, None, True), "diagrama": (op_diagrama, None, True),
}
OPCIONES = {"pista", "idioma", "incrustar", "voz", "salida", "formato", "tipo"}


class Fallo(Exception):
    pass


def run(args, timeout, entorno_extra=None):
    r = subprocess.run(args, capture_output=True, text=True, timeout=timeout, env={**ENTORNO, **(entorno_extra or {})},
                       cwd="/tmp")
    if r.returncode != 0:
        salida = (r.stderr or r.stdout).strip().splitlines()
        raise Fallo(f"{os.path.basename(args[0])} terminó con código {r.returncode}"
                    + (f": {salida[-1][:300]}" if salida else ""))


class Manejador(BaseHTTPRequestHandler):
    server_version = "sip-medios/1.0"

    def log_message(self, fmt, *a):
        print("%s %s" % (self.address_string(), fmt % a), flush=True)

    def _json(self, code, datos):
        b = json.dumps(datos, ensure_ascii=False).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(b)))
        self.end_headers()
        self.wfile.write(b)

    def do_GET(self):
        self._json(200, {"operaciones": sorted(OPS)})

    def do_POST(self):
        if not self.path.startswith("/op/") or self.path[4:] not in OPS:
            return self._json(404, {"error": "operación desconocida", "operaciones": sorted(OPS)})
        nombre = self.path[4:]
        fn, exts, con_texto = OPS[nombre]
        largo = int(self.headers.get("Content-Length") or 0)
        if largo <= 0 or largo > MAX_BYTES:
            return self._json(413, {"error": "petición vacía o de más de 250 MB"})
        d = tempfile.mkdtemp(prefix="sip-medios-")
        try:
            form = cgi.FieldStorage(fp=self.rfile, headers=self.headers, environ={
                "REQUEST_METHOD": "POST", "CONTENT_TYPE": self.headers["Content-Type"], "CONTENT_LENGTH": str(largo)})
            o = {k: str(form.getfirst(k))[:40] for k in OPCIONES if form.getfirst(k) is not None}
            entrada = None
            if exts is not None:
                if "file" not in form or not getattr(form["file"], "filename", None):
                    return self._json(400, {"error": "falta el fichero (campo file)"})
                ext = os.path.splitext(form["file"].filename)[1].lower()
                if ext not in exts:
                    return self._json(400, {"error": f"tipo no admitido para {nombre}: {ext}", "admitidos": sorted(exts)})
                entrada = os.path.join(d, "entrada" + ext)
                with open(entrada, "wb") as f:
                    shutil.copyfileobj(form["file"].file, f)
            if con_texto:
                t = form.getfirst("texto")
                if not t or len(t) > 200_000:
                    return self._json(400, {"error": "falta el campo texto (o pasa de 200.000 caracteres)"})
                o["texto"] = t
            with _turno:
                salida, ext_s = fn(d, entrada, o)
            if not os.path.isfile(salida):
                return self._json(500, {"error": "la operación no produjo resultado"})
            tam = os.path.getsize(salida)
            self.send_response(200)
            self.send_header("Content-Type", "application/octet-stream")
            self.send_header("Content-Length", str(tam))
            self.send_header("X-Sip-Fichero", f"{nombre}{ext_s}")
            self.end_headers()
            with open(salida, "rb") as f:
                shutil.copyfileobj(f, self.wfile)
        except (Fallo, ValueError, KeyError) as e:
            self._json(422, {"error": str(e)[:400]})
        except subprocess.TimeoutExpired:
            self._json(504, {"error": "la operación tardó demasiado"})
        except Exception as e:  # noqa: BLE001
            self._json(500, {"error": f"fallo interno ({type(e).__name__})"})
        finally:
            shutil.rmtree(d, ignore_errors=True)


if __name__ == "__main__":
    ThreadingHTTPServer(("127.0.0.1", PUERTO), Manejador).serve_forever()
