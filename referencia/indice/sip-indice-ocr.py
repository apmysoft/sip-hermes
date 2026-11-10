#!/usr/bin/env python3
"""OCR del índice de PARA en HALO (09-11, decisión del usuario). Host de Neo, usuario sip-indice, 02:00-06:00.

Toma los PDF que sip-indice dejó como «pendiente-ocr», despierta HALO si hace falta (WOL por el emisor único de
Neo, con su cupo) y los envía uno a uno a sip-medios (operación fija `ocr`, salida=texto) por llama-swap. El
texto se guarda en el índice. A HALO solo viaja el PDF, siempre con el nombre `documento.pdf`.
No empieza un documento nuevo a partir de --hasta (por defecto 05:50); el servicio tiene un tope duro a las 06:00.
Con el modo ausencia activo no despierta a HALO. PRIVACIDAD: el registro solo lleva recuentos y tiempos.
Uso: sip-indice-ocr.py [--hasta HH:MM] [--max-docs N]
"""
import argparse
import http.client
import json
import os
import socket
import sqlite3
import sys
import time
import uuid

DB = os.environ.get("SIP_INDICE_DB", "/var/lib/sip-indice/indice.db")
HALO = os.environ.get("SIP_HALO_HOST", "${HALO_TAILNET_IP}")
PUERTO = int(os.environ.get("SIP_HALO_PUERTO", "11434"))
RUTA_OCR = os.environ.get("SIP_MEDIOS_OCR", "/upstream/medios/op/ocr")
WOL = os.environ.get("SIP_INDICE_WOL", "/var/lib/sip-indice-wol")
AUSENCIA = os.environ.get("SIP_AUSENCIA", "/var/lib/sip-ausencia/activa")
MAX_BYTES = 250 * 1024 * 1024        # límite de sip-medios
MAX_TEXTO = 400_000                  # como sip-indice


def log(m):
    print(time.strftime("%H:%M:%S"), m, flush=True)


def halo_up():
    try:
        with socket.create_connection((HALO, PUERTO), timeout=3):
            return True
    except OSError:
        return False


def despertar():
    """Pide el WOL al emisor de Neo y espera su resultado. True si HALO responde."""
    if halo_up():
        return True
    rid = f"indice-{int(time.time())}-{os.getpid()}"
    tmp = os.path.join(WOL, "requests", f".{rid}.tmp")
    with open(tmp, "w") as f:
        f.write("{}\n")
    os.replace(tmp, os.path.join(WOL, "requests", f"{rid}.json"))
    res = os.path.join(WOL, "results", f"{rid}.json")
    fin = time.time() + 300
    while time.time() < fin:
        if os.path.exists(res):
            try:
                with open(res) as f:
                    estado = json.load(f).get("status")
            except (OSError, ValueError):
                estado = "ilegible"
            log(f"WOL: {estado}")
            break
        time.sleep(3)
    for _ in range(40):  # el servicio de modelos puede tardar algo más que el puerto
        if halo_up():
            return True
        time.sleep(3)
    return False


def ocr_en_halo(ruta, timeout):
    """(código HTTP, texto). El PDF se envía como documento.pdf (el nombre real no sale de Neo)."""
    fr = uuid.uuid4().hex
    campos = f'--{fr}\r\nContent-Disposition: form-data; name="salida"\r\n\r\ntexto\r\n'.encode()
    cab = (f'--{fr}\r\nContent-Disposition: form-data; name="file"; filename="documento.pdf"\r\n'
           "Content-Type: application/pdf\r\n\r\n").encode()
    pie, fin = b"\r\n", f"--{fr}--\r\n".encode()
    tam = os.path.getsize(ruta)
    c = http.client.HTTPConnection(HALO, PUERTO, timeout=timeout)
    try:
        c.putrequest("POST", RUTA_OCR)
        c.putheader("Content-Type", f"multipart/form-data; boundary={fr}")
        c.putheader("Content-Length", str(len(campos) + len(cab) + tam + len(pie) + len(fin)))
        c.endheaders()
        c.send(campos)
        c.send(cab)
        with open(ruta, "rb") as f:
            while True:
                b = f.read(1 << 20)
                if not b:
                    break
                c.send(b)
        c.send(pie)
        c.send(fin)
        r = c.getresponse()
        return r.status, r.read().decode("utf-8", "replace")
    finally:
        c.close()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--hasta", default="05:50", help="no empezar documentos nuevos a partir de esta hora")
    ap.add_argument("--max-docs", type=int, default=0, help="0 = sin límite (para pruebas)")
    a = ap.parse_args()
    hh, mm = (int(x) for x in a.hasta.split(":"))
    ahora = time.localtime()
    limite = time.mktime((ahora.tm_year, ahora.tm_mon, ahora.tm_mday, hh, mm, 0, 0, 0, -1))
    if limite <= time.time():
        limite += 86400
    if os.path.exists(AUSENCIA):
        log("modo ausencia activo: no se despierta a HALO")
        return 0
    db = sqlite3.connect(DB, timeout=120)
    db.execute("pragma journal_mode=delete")
    pendientes = db.execute("select ruta, tam, mtime from docs where estado = 'pendiente-ocr' and ext = '.pdf' "
                            "order by tam").fetchall()
    n = {"pendientes": len(pendientes), "hechos": 0, "fallidos": 0, "cambiados": 0, "grandes": 0}
    if not pendientes:
        log("nada pendiente de OCR")
        return 0
    if not despertar():
        log(f"HALO no responde: OCR aplazado ({len(pendientes)} pendientes)")
        return 0
    t0 = time.time()
    for ruta, tam, mtime in pendientes:
        if time.time() >= limite or (a.max_docs and n["hechos"] + n["fallidos"] >= a.max_docs):
            break
        try:
            st = os.stat(ruta)
        except OSError:
            n["cambiados"] += 1  # ya no existe: lo retira sip-indice
            continue
        if st.st_size != tam or st.st_mtime_ns != mtime:
            n["cambiados"] += 1  # cambió: sip-indice lo reprocesará
            continue
        if tam > MAX_BYTES:
            metodo, texto = "ocr-demasiado-grande", ""
            n["grandes"] += 1
        else:
            restante = max(120, min(1800, limite + 600 - time.time()))
            try:
                codigo, texto = ocr_en_halo(ruta, restante)
            except (OSError, http.client.HTTPException):
                if not halo_up():
                    log("HALO dejó de responder: se para")
                    break
                codigo, texto = 0, ""
            if codigo == 200:
                metodo = "ocr-halo"
                n["hechos"] += 1
            else:
                metodo, texto = "ocr-halo-fallido", ""
                n["fallidos"] += 1
        texto = " ".join(texto.split())[:MAX_TEXTO]
        with db:
            if texto:
                db.execute("delete from fts where ruta = ?", (ruta,))
                db.execute("insert into fts(ruta, nombre, texto) values (?,?,?)",
                           (ruta, os.path.basename(ruta).replace("_", " "), texto))
            db.execute("update docs set estado = ?, metodo = ?, indexado = ? where ruta = ?",
                       (metodo, metodo, int(time.time()), ruta))
    db.close()
    restan = n["pendientes"] - n["hechos"] - n["fallidos"] - n["grandes"] - n["cambiados"]
    log(" ".join(f"{k}={v}" for k, v in n.items()) + f" restan={restan} {time.time() - t0:.0f}s")
    return 0


if __name__ == "__main__":
    sys.exit(main())
