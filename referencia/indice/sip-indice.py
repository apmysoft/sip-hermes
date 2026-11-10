#!/usr/bin/env python3
"""Índice de texto completo de PARA (05-11; PROPUESTA-HERRAMIENTAS §1.1-1.2). Host de Neo, usuario sip-indice.

Solo lectura de PARA. Extrae texto de documentos y lo guarda en SQLite FTS5 (/var/lib/sip-indice/indice.db),
que PERSONAL consulta en solo lectura (documentos_buscar_texto). Incremental: solo ficheros nuevos o con
tamaño/fecha distintos; borra del índice lo que ya no existe. PDF sin capa de texto -> OCR (ocrmypdf
--sidecar, spa+eng) sobre una copia temporal; el texto OCR se guarda en el índice, el original no se toca.
PRIVACIDAD: el registro solo lleva recuentos y tiempos, nunca rutas ni contenido.
09-11: los PDF de más de --max-paginas-pdf páginas (libros) se registran solo por su nombre, sin texto; los
borrados se retiran cada noche (el recorrido es siempre completo; no se retira nada de una carpeta de primer nivel
ausente o ilegible ni de una subcarpeta en la que no se pudo entrar) y la base se compacta (VACUUM) si más del
20 % es espacio libre.
09-11 (tarde): con --sin-ocr no hace OCR local; los escaneados quedan «pendiente-ocr» y no se reprocesan cada noche:
los pasa sip-indice-ocr.py a HALO (02:00-06:00).
Uso: sip-indice.py [--max-minutos N] [--max-ocr-paginas N] [--max-paginas-pdf N] [--sin-ocr]
"""
import argparse
import email
import email.policy
import html
import os
import re
import sqlite3
import subprocess
import sys
import tempfile
import time
import zipfile
from xml.etree import ElementTree

RAIZ = os.environ.get("SIP_PARA_RAIZ_PRUEBA", "${PARA_ROOT}")  # la variable solo para pruebas sintéticas
CARPETAS = ["00_entrada", "01_proyectos", "02_areas", "03_recursos", "04_archivo"]
DB = os.environ.get("SIP_INDICE_DB", "/var/lib/sip-indice/indice.db")
MAX_BYTES = 200 * 1024 * 1024       # documentos más grandes no se indexan
MAX_TEXTO = 400_000                 # caracteres por documento
TEXTO_PLANO = {".txt", ".md", ".csv", ".tsv", ".json", ".log", ".ini", ".yaml", ".yml", ".xml", ".srt", ".vtt"}
OFFICE = {".docx", ".xlsx", ".pptx", ".odt", ".ods", ".odp"}
TIPOS = TEXTO_PLANO | OFFICE | {".pdf", ".html", ".htm", ".eml", ".rtf"}
EXCLUIR_DIRS = {".git", "node_modules", "__pycache__", ".Trash-1000", "@eaDir", "#recycle"}


def log(m):
    print(time.strftime("%H:%M:%S"), m, flush=True)


def abrir_db():
    os.makedirs(os.path.dirname(DB), exist_ok=True)
    c = sqlite3.connect(DB, timeout=60)
    c.execute("pragma journal_mode=delete")  # PERSONAL la lee desde un montaje de solo lectura (WAL exige -shm escribible)
    c.executescript("""
      create table if not exists docs(ruta text primary key, tam integer, mtime integer, ext text,
                                      estado text, metodo text, indexado integer);
      create virtual table if not exists fts using fts5(ruta unindexed, nombre, texto,
                                      tokenize='unicode61 remove_diacritics 2');
      create table if not exists meta(k text primary key, v text);
    """)
    return c


def run(cmd, timeout=120):
    p = subprocess.run(cmd, capture_output=True, timeout=timeout, stdin=subprocess.DEVNULL)
    return p.returncode, p.stdout.decode("utf-8", "replace")


def xml_texto(data):
    try:
        return " ".join(t.strip() for t in ElementTree.fromstring(data).itertext() if t.strip())
    except ElementTree.ParseError:
        return ""


def office(ruta, ext):
    partes = []
    with zipfile.ZipFile(ruta) as z:
        nombres = z.namelist()
        if ext in (".odt", ".ods", ".odp"):
            elegidos = [n for n in nombres if n == "content.xml"]
        elif ext == ".docx":
            elegidos = [n for n in nombres if re.match(r"word/(document|header\d*|footer\d*|footnotes)\.xml$", n)]
        elif ext == ".xlsx":
            elegidos = [n for n in nombres if n == "xl/sharedStrings.xml" or re.match(r"xl/worksheets/sheet\d+\.xml$", n)]
        else:
            elegidos = sorted(n for n in nombres if re.match(r"ppt/slides/slide\d+\.xml$", n))
        total = 0
        for n in elegidos:
            info = z.getinfo(n)
            if info.file_size > 50 * 1024 * 1024:  # bomba zip
                continue
            total += info.file_size
            if total > 200 * 1024 * 1024:
                break
            partes.append(xml_texto(z.read(n)))
    return " ".join(partes)


def pdf(ruta, presupuesto):
    rc2, info = run(["pdfinfo", ruta], timeout=30)
    m = re.search(r"^Pages:\s+(\d+)", info, re.M)
    paginas = int(m.group(1)) if m else 1
    if paginas > presupuesto["max_paginas"]:  # libro: solo el nombre (se busca por título)
        return "", "libro", 0
    rc, txt = run(["pdftotext", "-q", "-enc", "UTF-8", ruta, "-"], timeout=180)
    if len(re.sub(r"\s", "", txt)) >= 40 * max(paginas, 1) / 4:  # tiene capa de texto suficiente
        return txt, "pdftotext", 0
    if paginas > presupuesto["ocr"] or paginas > 200:
        return txt, "pendiente-ocr", 0
    with tempfile.TemporaryDirectory() as t:
        side = os.path.join(t, "s.txt")
        rc, _ = run(["ocrmypdf", "-q", "-l", "spa+eng", "--skip-text", "--sidecar", side, "--output-type", "none",
                     "--jobs", "2", ruta, "-"], timeout=60 * max(paginas, 1))
        if rc == 0 and os.path.exists(side):
            with open(side, encoding="utf-8", errors="replace") as f:
                return f.read(), "ocr", paginas
    return txt, "ocr-fallido", paginas


def extraer(ruta, ext, presupuesto):
    if ext in TEXTO_PLANO:
        with open(ruta, "rb") as f:
            return f.read(MAX_TEXTO * 2).decode("utf-8", "replace"), "texto", 0
    if ext in OFFICE:
        return office(ruta, ext), "office", 0
    if ext == ".pdf":
        return pdf(ruta, presupuesto)
    if ext in (".html", ".htm"):
        with open(ruta, "rb") as f:
            h = f.read(MAX_TEXTO * 4).decode("utf-8", "replace")
        h = re.sub(r"(?is)<(script|style).*?</\1>", " ", h)
        return html.unescape(re.sub(r"<[^>]+>", " ", h)), "html", 0
    if ext == ".eml":
        with open(ruta, "rb") as f:
            msg = email.message_from_binary_file(f, policy=email.policy.default)
        cab = " ".join(str(msg.get(k, "")) for k in ("From", "To", "Subject", "Date"))
        cuerpo = msg.get_body(preferencelist=("plain", "html"))
        texto = ""
        if cuerpo is not None:
            datos = cuerpo.get_payload(decode=True) or b""
            try:
                texto = datos.decode(cuerpo.get_content_charset() or "utf-8", "replace")
            except LookupError:
                texto = datos.decode("utf-8", "replace")
            if cuerpo.get_content_subtype() == "html":
                texto = html.unescape(re.sub(r"<[^>]+>", " ", re.sub(r"(?is)<(script|style).*?</\1>", " ", texto)))
        return cab + " " + texto, "eml", 0
    if ext == ".rtf":
        with open(ruta, "rb") as f:
            r = f.read(MAX_TEXTO * 2).decode("latin-1", "replace")
        return re.sub(r"\\[a-z]+-?\d* ?|[{}]", " ", r), "rtf", 0
    return "", "sin-extractor", 0


def recorrer(fallidos):
    """Ficheros indexables. `fallidos` recibe las carpetas que no se pudieron leer (no se retira nada de ellas)."""
    for c in CARPETAS:
        base = os.path.join(RAIZ, c)
        if not (os.path.isdir(base) and os.access(base, os.R_OK | os.X_OK)):
            fallidos.add(base)
            continue
        for dirpath, dirnames, filenames in os.walk(base, onerror=lambda e: fallidos.add(e.filename)):
            dirnames[:] = [d for d in dirnames if d not in EXCLUIR_DIRS and not d.startswith(".")]
            for n in filenames:
                ext = os.path.splitext(n)[1].lower()
                if ext in TIPOS and not n.startswith("~$"):
                    yield os.path.join(dirpath, n), ext


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--max-minutos", type=int, default=150)
    ap.add_argument("--max-ocr-paginas", type=int, default=600)
    ap.add_argument("--max-paginas-pdf", type=int, default=100)
    ap.add_argument("--sin-ocr", action="store_true", help="sin OCR local: lo hace sip-indice-ocr en HALO")
    a = ap.parse_args()
    if not os.path.ismount(RAIZ) and "SIP_PARA_RAIZ_PRUEBA" not in os.environ:
        log("PARA sin montar; nada que hacer")
        return 1
    fin = time.monotonic() + a.max_minutos * 60
    presupuesto = {"ocr": 0 if a.sin_ocr else a.max_ocr_paginas, "max_paginas": a.max_paginas_pdf}
    db = abrir_db()
    conocidos = {r[0]: (r[1], r[2], r[3]) for r in db.execute("select ruta, tam, mtime, estado from docs")}
    vistos = set()
    n = {"nuevos": 0, "cambiados": 0, "iguales": 0, "errores": 0, "ilegibles": 0, "ocr_paginas": 0, "pendiente_ocr": 0,
         "libros": 0, "nombre_no_utf8": 0}
    t0 = time.time()
    cortado = False
    fallidos = set()
    for ruta, ext in recorrer(fallidos):
        try:  # nombres que no son UTF-8 (los hay en PARA): SQLite no los admite; se cuentan y se saltan
            ruta.encode("utf-8")
        except UnicodeEncodeError:
            n["nombre_no_utf8"] += 1
            continue
        vistos.add(ruta)
        try:
            st = os.stat(ruta)
        except OSError:
            n["ilegibles"] += 1
            continue
        k = conocidos.get(ruta)
        if k and k[0] == st.st_size and k[1] == st.st_mtime_ns and (k[2] != "pendiente-ocr" or a.sin_ocr):
            n["iguales"] += 1
            continue
        if time.monotonic() > fin:
            cortado = True
            continue
        if st.st_size > MAX_BYTES:
            texto, metodo, pags = "", "demasiado-grande", 0
        else:
            try:
                texto, metodo, pags = extraer(ruta, ext, presupuesto)
            except PermissionError:
                n["ilegibles"] += 1
                continue
            except Exception:
                texto, metodo, pags = "", "error", 0
                n["errores"] += 1
        presupuesto["ocr"] -= pags
        n["ocr_paginas"] += pags
        n["pendiente_ocr"] += metodo == "pendiente-ocr"
        n["libros"] += metodo == "libro"
        texto = re.sub(r"[ \t\r\f\v]+", " ", texto)[:MAX_TEXTO]
        n["cambiados" if k else "nuevos"] += 1
        with db:
            db.execute("delete from fts where ruta = ?", (ruta,))
            db.execute("insert into fts(ruta, nombre, texto) values (?,?,?)",
                       (ruta, os.path.basename(ruta).replace("_", " "), texto))
            db.execute("insert or replace into docs values (?,?,?,?,?,?,?)",
                       (ruta, st.st_size, st.st_mtime_ns, ext, metodo, metodo, int(time.time())))
    borrados = 0
    # El recorrido siempre es completo (al cortarse por tiempo solo deja de extraer). Lo que no se vio se retira,
    # salvo lo que cuelga de una carpeta que no se pudo leer (PARA medio montado, permisos): eso se conserva.
    conservados = 0
    for ruta in set(conocidos) - vistos:
        if any(ruta == f or ruta.startswith(f.rstrip("/") + "/") for f in fallidos):
            conservados += 1
            continue
        with db:
            db.execute("delete from fts where ruta = ?", (ruta,))
            db.execute("delete from docs where ruta = ?", (ruta,))
        borrados += 1
    if fallidos:
        log(f"{len(fallidos)} carpeta(s) ilegibles: se conservan {conservados} entradas suyas")
    total = db.execute("select count(*) from docs").fetchone()[0]
    with db:
        db.execute("insert or replace into meta values ('ultima', ?)", (time.strftime("%Y-%m-%d %H:%M"),))
        db.execute("insert or replace into meta values ('completo', ?)", ("no" if cortado else "si",))
    libres, paginas = db.execute("pragma freelist_count").fetchone()[0], db.execute("pragma page_count").fetchone()[0]
    compactada = paginas > 0 and libres / paginas > 0.2
    if compactada:  # devuelve al disco el espacio de lo borrado
        db.execute("vacuum")
    db.close()
    log(f"{'compactada ' if compactada else ''}total={total} " + " ".join(f"{k}={v}" for k, v in n.items()) + f" borrados={borrados} "
        f"{'CORTADO por tiempo (sigue la próxima vez)' if cortado else 'completo'} {time.time() - t0:.0f}s")
    return 0


if __name__ == "__main__":
    sys.exit(main())
