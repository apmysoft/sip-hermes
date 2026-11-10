#!/usr/bin/env python3
"""Garantías de PARA (05-11; PROPUESTA-HERRAMIENTAS §1.4). Host de Neo, solo lectura. PREPARADO, SIN DESPLEGAR.

- Catálogo de huellas (BLAKE2b) en /var/lib/sip-garantias/catalogo.db. Ficheros nuevos o con tamaño/fecha
  distintos se reprocesan; además se re-verifica cada noche una porción de los ya conocidos (tope de GB), de
  modo que todo PARA se recomprueba periódicamente. Mismo tamaño y fecha pero huella distinta = posible
  corrupción silenciosa (bit rot): se avisa.
- Integridad por tipo: PDF (qpdf --check), ZIP/Office (zipfile.testzip), JPEG (marcas SOI/EOI).
- Duplicados exactos (misma huella, > 1 MB): solo informe; nunca se borra nada.
Informe con rutas en /var/lib/sip-garantias/informes/ (root y usuario); a Telegram solo recuentos.
PRIVACIDAD: el registro solo lleva recuentos y tiempos.
09-11: cada noche (02:15) y por prioridad (decisión del usuario): los ficheros nuevos se procesan primero los
documentos y la ofimática, después las fotos, los libros y cómics, el audio y otros, los comprimidos y al final el
vídeo; dentro de cada grupo, de menor a mayor. Así lo irreemplazable tiene huella en pocas noches.
Uso: sip-garantias.py [--max-gb N] [--max-minutos N]
"""
import argparse
import hashlib
import os
import sqlite3
import subprocess
import sys
import time
import zipfile

RAIZ = os.environ.get("SIP_PARA_RAIZ_PRUEBA", "${PARA_ROOT}")
CARPETAS = ["00_entrada", "01_proyectos", "02_areas", "03_recursos", "04_archivo"]
BASE = os.environ.get("SIP_GARANTIAS_DIR", "/var/lib/sip-garantias")
OUTBOX = os.environ.get("SIP_NOTIFY_OUTBOX", "/var/lib/sip-notify/outbox")
PRIORIDAD = {}  # extensión -> grupo (0 = primero); el resto, grupo 3
for _g, _exts in enumerate([
        ".pdf .doc .docx .odt .xls .xlsx .ods .ppt .pptx .odp .txt .md .rtf .eml .msg .csv",
        ".jpg .jpeg .png .heic .heif .tif .tiff .raw .cr2 .nef .arw .dng .webp",
        ".epub .mobi .azw .azw3 .fb2 .djvu .cbz .cbr",
        ".mp3 .m4a .flac .ogg .wav .opus",
        ".zip .rar .7z .tar .gz",
        ".mp4 .mkv .avi .mov .m4v .webm .ts .iso"]):
    for _e in _exts.split():
        PRIORIDAD[_e] = _g if _g < 3 else _g + 1  # audio=4, comprimidos=5, vídeo=6; «otros» = 3
ZIPS = {".zip", ".docx", ".xlsx", ".pptx", ".odt", ".ods", ".odp", ".epub"}


def log(m):
    print(time.strftime("%H:%M:%S"), m, flush=True)


def huella(ruta):
    h = hashlib.blake2b(digest_size=32)
    with open(ruta, "rb") as f:
        for b in iter(lambda: f.read(1 << 22), b""):
            h.update(b)
    return h.hexdigest()


def integridad(ruta, ext):
    """None si está bien o no se sabe comprobar; texto con el problema si no."""
    try:
        if ext == ".pdf":
            p = subprocess.run(["qpdf", "--check", ruta], capture_output=True, timeout=300, stdin=subprocess.DEVNULL)
            return None if p.returncode in (0, 3) else "PDF dañado (qpdf)"  # 3 = avisos, legible
        if ext in ZIPS:
            with zipfile.ZipFile(ruta) as z:
                return None if z.testzip() is None else "ZIP con un miembro dañado"
        if ext in (".jpg", ".jpeg"):
            with open(ruta, "rb") as f:
                ini = f.read(2)
                f.seek(-2, os.SEEK_END)
                fin = f.read(2)
            return None if ini == b"\xff\xd8" and fin == b"\xff\xd9" else "JPEG truncado o no válido"
    except zipfile.BadZipFile:
        return "ZIP no válido"
    except (OSError, subprocess.TimeoutExpired):
        return None
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--max-gb", type=float, default=150.0)
    ap.add_argument("--max-minutos", type=int, default=240)
    a = ap.parse_args()
    if not os.path.ismount(RAIZ) and "SIP_PARA_RAIZ_PRUEBA" not in os.environ:
        log("PARA sin montar")
        return 1
    os.makedirs(os.path.join(BASE, "informes"), exist_ok=True)
    db = sqlite3.connect(os.path.join(BASE, "catalogo.db"))
    db.executescript("""create table if not exists f(ruta text primary key, tam integer, mtime integer,
                        huella text, comprobado integer, problema text);""")
    conocidos = {r[0]: r[1:] for r in db.execute("select ruta, tam, mtime, huella, comprobado from f")}
    presupuesto = a.max_gb * 1e9
    fin = time.monotonic() + a.max_minutos * 60
    n = dict(ficheros=0, nuevos=0, cambiados=0, reverificados=0, corrupcion=0, danados=0, pendientes=0,
             nombre_no_utf8=0)
    fallidos = set()  # carpetas que no se pudieron leer: no se retira del catálogo nada de ellas (09-11)
    alertas, vistos, revisar, nuevos = [], set(), [], []
    for c in CARPETAS:
        base = os.path.join(RAIZ, c)
        if not (os.path.isdir(base) and os.access(base, os.R_OK | os.X_OK)):
            fallidos.add(base)
            continue
        for dp, dn, fn in os.walk(base, onerror=lambda e: fallidos.add(e.filename)):
            dn[:] = [d for d in dn if not d.startswith(".")]
            for nombre in fn:
                ruta = os.path.join(dp, nombre)
                try:  # nombres que no son UTF-8: SQLite no los admite; se cuentan y se saltan (09-11)
                    ruta.encode("utf-8")
                except UnicodeEncodeError:
                    n["nombre_no_utf8"] += 1
                    continue
                try:
                    st = os.stat(ruta)
                except OSError:
                    continue
                vistos.add(ruta)
                n["ficheros"] += 1
                k = conocidos.get(ruta)
                if k and k[0] == st.st_size and k[1] == st.st_mtime_ns:
                    revisar.append((k[3] or 0, ruta, st, k[2]))
                    continue
                ext = os.path.splitext(nombre)[1].lower()
                nuevos.append((PRIORIDAD.get(ext, 3), st.st_size, ruta, st, k, ext))
    # Ficheros nuevos o cambiados, por prioridad y de menor a mayor (09-11)
    for _, _, ruta, st, k, ext in sorted(nuevos, key=lambda x: (x[0], x[1])):
        if presupuesto <= 0 or time.monotonic() > fin:
            n["pendientes"] += 1
            continue
        try:
            h = huella(ruta)
        except OSError:
            continue
        presupuesto -= st.st_size
        prob = integridad(ruta, ext)
        n["danados"] += prob is not None
        n["cambiados" if k else "nuevos"] += 1
        with db:
            db.execute("insert or replace into f values (?,?,?,?,?,?)",
                       (ruta, st.st_size, st.st_mtime_ns, h, int(time.time()), prob))
    # Re-verificación de los más antiguos con el presupuesto que quede
    for _, ruta, st, h_ant in sorted(revisar):
        if presupuesto <= 0 or time.monotonic() > fin:
            break
        try:
            h = huella(ruta)
        except OSError:
            continue
        presupuesto -= st.st_size
        n["reverificados"] += 1
        if h != h_ant:
            n["corrupcion"] += 1
            alertas.append(("CAMBIO SIN FECHA (posible corrupción)", ruta))
        with db:
            db.execute("update f set comprobado=?, huella=? where ruta=?", (int(time.time()), h_ant, ruta))
    with db:
        for ruta in set(conocidos) - vistos:
            if any(ruta == f or ruta.startswith(f.rstrip("/") + "/") for f in fallidos):
                continue  # carpeta ilegible: se conserva su huella de referencia
            db.execute("delete from f where ruta=?", (ruta,))
    if fallidos:
        log(f"{len(fallidos)} carpeta(s) ilegibles: se conservan sus huellas")
    danados = db.execute("select ruta, problema from f where problema is not null order by ruta").fetchall()
    dups = db.execute("select huella, tam, group_concat(ruta, char(10)) from f where tam > 1048576 and huella is not null "
                      "group by huella having count(*) > 1 order by tam desc").fetchall()
    desperdicio = sum(t * (len(r.split("\n")) - 1) for _, t, r in dups)
    inf = os.path.join(BASE, "informes", time.strftime("garantias-%Y%m%d.txt"))
    with open(inf, "w") as f:
        f.write(f"Garantías de PARA {time.strftime('%Y-%m-%d %H:%M')}\n{n}\n\n")
        for t, r in alertas:
            f.write(f"{t}: {r}\n")
        f.write(f"\nDañados ({len(danados)}):\n" + "".join(f"  {p}: {r}\n" for r, p in danados))
        f.write(f"\nDuplicados exactos > 1 MB ({len(dups)} grupos, {desperdicio / 1e9:.1f} GB repetidos):\n")
        for _, t, r in dups:
            f.write(f"  [{t / 1e6:.0f} MB]\n" + "".join(f"    {x}\n" for x in r.split("\n")))
    os.chmod(inf, 0o640)
    resumen = (f"Garantías de PARA: {n['ficheros']} ficheros, {n['nuevos']} nuevos, {n['reverificados']} reverificados; "
               f"{n['corrupcion']} posibles corrupciones, {len(danados)} dañados, {len(dups)} grupos de duplicados "
               f"({desperdicio / 1e9:.1f} GB). Detalle en Neo: {inf}")
    if n["corrupcion"] or n["danados"]:
        try:
            tmp = os.path.join(OUTBOX, ".garantias.tmp")
            with open(tmp, "w") as f:
                f.write(resumen + "\n")
            os.replace(tmp, os.path.join(OUTBOX, time.strftime("garantias-%Y%m%d-%H%M%S.txt")))
        except OSError:
            pass
    log(" ".join(f"{k}={v}" for k, v in n.items()) + f" danados_total={len(danados)} dups={len(dups)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
