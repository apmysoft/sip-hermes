#!/usr/bin/env python3
"""Puente de notas de voz (05-11): sip-gateway deja el audio, el host lo transcribe con Whisper en HALO.

Lo dispara sip-voz-bridge.path (DirectoryNotEmpty=requests). Corre como sip-voz (sin privilegios).
sip-gateway no llega a HALO (su red solo sale a Telegram); el host sí (ACL tag:sip -> tag:halo:8178).
El audio nunca se interpreta aquí: se reenvía tal cual a whisper-server (--convert, en HALO).
Si HALO no responde, pide el despertar por el buzón de WOL (petición explícita del usuario) y espera.
No registra el texto; solo tamaños y tiempos. Toda petición se retira siempre (sin start-limit-hit).
"""
import http.client
import json
import os
import re
import time
import urllib.parse
import uuid

ROOT = os.environ.get("SIP_VOZ_ROOT", "/var/lib/sip-voz")
URL = os.environ.get("SIP_WHISPER_URL", "http://${HALO_TAILNET_IP}:8178/inference")
WOL_REQ = os.environ.get("SIP_WOL_REQUESTS", "${DOCKER_DATA}/hermes/workspace/_wol/requests")
MAX_BYTES = 25 * 1024 * 1024
TIMEOUT = 600
ESPERA_HALO = 240
NOMBRE = re.compile(r"^[0-9a-f]{32}\.audio$")


def log(m):
    print(time.strftime("%H:%M:%S"), m, flush=True)


def whisper_vivo():
    u = urllib.parse.urlsplit(URL)
    try:
        c = http.client.HTTPConnection(u.hostname, u.port or 80, timeout=4)
        c.request("GET", "/")
        c.getresponse().read()
        c.close()
        return True
    except OSError:
        return False


def despertar_halo(rid):
    try:
        fd = os.open(os.path.join(WOL_REQ, f".voz-{rid}.tmp"), os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o660)
        with os.fdopen(fd, "w") as f:
            json.dump({"origen": "nota de voz", "ts": int(time.time())}, f)
        os.replace(os.path.join(WOL_REQ, f".voz-{rid}.tmp"), os.path.join(WOL_REQ, f"voz-{rid}.json"))
        log("HALO no responde: despertar pedido")
    except OSError as e:
        log(f"no se pudo pedir el despertar: {type(e).__name__}")


def transcribir(fd, tam):
    u = urllib.parse.urlsplit(URL)
    frontera = uuid.uuid4().hex
    campos = b"".join(
        f'--{frontera}\r\nContent-Disposition: form-data; name="{k}"\r\n\r\n{v}\r\n'.encode()
        for k, v in (("response_format", "text"), ("language", "auto"), ("temperature", "0")))
    cab = (f'--{frontera}\r\nContent-Disposition: form-data; name="file"; filename="nota.ogg"\r\n'
           "Content-Type: application/octet-stream\r\n\r\n").encode()
    pie = f"\r\n--{frontera}--\r\n".encode()
    c = http.client.HTTPConnection(u.hostname, u.port or 80, timeout=TIMEOUT)
    c.putrequest("POST", u.path or "/inference")
    c.putheader("Content-Type", f"multipart/form-data; boundary={frontera}")
    c.putheader("Content-Length", str(len(campos) + len(cab) + tam + len(pie)))
    c.endheaders()
    c.send(campos)
    c.send(cab)
    with os.fdopen(os.dup(fd), "rb") as f:
        while True:
            b = f.read(1 << 20)
            if not b:
                break
            c.send(b)
    c.send(pie)
    r = c.getresponse()
    cuerpo = r.read().decode("utf-8", "replace")
    c.close()
    return r.status, cuerpo


def resultado(rid, datos):
    res = os.path.join(ROOT, "results")
    tmp = os.path.join(res, f".{rid}.tmp")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o644)
    with os.fdopen(fd, "w") as f:
        json.dump(datos, f, ensure_ascii=False)
    os.chmod(tmp, 0o644)  # el gateway (dueño de la carpeta, fuera del grupo) lo lee
    os.replace(tmp, os.path.join(res, f"{rid}.json"))


def procesar(nombre):
    req = os.path.join(ROOT, "requests", nombre)
    rid = nombre.split(".")[0]
    try:
        fd = os.open(req, os.O_RDONLY | os.O_NOFOLLOW)
    except OSError:
        return
    try:
        st = os.fstat(fd)
        if not (st.st_mode & 0o170000 == 0o100000) or st.st_size == 0 or st.st_size > MAX_BYTES:
            resultado(rid, {"ok": False, "error": "audio vacío o de más de 25 MB"})
            return
        if not whisper_vivo():
            despertar_halo(rid)
            t = time.time()
            while time.time() - t < ESPERA_HALO and not whisper_vivo():
                time.sleep(5)
        t0 = time.time()
        try:
            code, texto = transcribir(fd, st.st_size)
        except OSError as e:
            resultado(rid, {"ok": False, "error": f"Whisper no responde ({type(e).__name__}); HALO apagado o despertando"})
            log(f"fallo {type(e).__name__}")
            return
        texto = re.sub(r"\s+", " ", texto).strip()
        if code != 200 or not texto:
            resultado(rid, {"ok": False, "error": f"Whisper devolvió HTTP {code} o texto vacío"})
            log(f"HTTP {code}")
            return
        resultado(rid, {"ok": True, "texto": texto[:8000], "segundos": round(time.time() - t0)})
        log(f"ok {st.st_size // 1024} KiB en {time.time() - t0:.0f}s")
    finally:
        os.close(fd)
        try:
            os.unlink(req)
        except OSError:
            pass


def main():
    time.sleep(1)  # que el gateway termine el rename
    reqdir = os.path.join(ROOT, "requests")
    for n in sorted(os.listdir(reqdir)):
        p = os.path.join(reqdir, n)
        if NOMBRE.match(n):
            procesar(n)
        elif not n.startswith(".") or time.time() - os.lstat(p).st_mtime > 300:
            try:
                os.unlink(p)  # restos o nombres no válidos
            except OSError:
                pass
    res = os.path.join(ROOT, "results")
    for n in os.listdir(res):  # resultados no recogidos en 1 h
        p = os.path.join(res, n)
        try:
            if time.time() - os.lstat(p).st_mtime > 3600:
                os.unlink(p)
        except OSError:
            pass


if __name__ == "__main__":
    main()
