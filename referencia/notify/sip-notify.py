#!/usr/bin/env python3
"""Canal de avisos del host a Telegram, sin LLM. Lo dispara sip-notify.path.

Cada fichero de la bandeja es un aviso de texto plano. Solo este servicio tiene el token
(LoadCredential) y salida a Telegram. Toda entrada se retira siempre de la bandeja, para no
provocar unit-start-limit-hit en la .path; si el envío falla, queda en el journal.

Temas del chat privado (pedido del usuario, 04-11): lo que espera algo del usuario va a «Peticiones»
(por el prefijo del fichero), los de sip-flujos a «Redacción» (09-11), el resto a «Avisos»; las zonas tienen su propio tema, que crea el gateway. Los temas se
crean la primera vez; si uno falla (p. ej. lo borró el usuario), el aviso sale sin tema y se recrean.
"""
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

OUTBOX = Path(os.environ.get("SIP_NOTIFY_OUTBOX", "/var/lib/sip-notify/outbox"))
STATE = Path(os.environ.get("SIP_NOTIFY_STATE", "/var/lib/sip-notify-state/sent.log"))
TEMAS = STATE.parent / "temas.json"
NOMBRES_TEMAS = ("Avisos", "Peticiones", "Redacción")
# Avisos de sip-flujos (formularios y resultados de los redactores) a su propio tema (pedido del usuario, 09-11).
REDACCION = ("flujos-",)
# Prefijos de los avisos que piden algo al usuario: código del gestor, curación de memoria, enchufe
# de HALO y mensajes de Claude cuando se para.
PETICIONES = ("gestor-", "memoria-", "wol-", "claude-", "stacks-")
MAX_PER_HOUR = 12  # un bucle de avisos no debe inundar el móvil
MAX_CHARS = 1000


def load_credentials():
    path = Path(os.environ["CREDENTIALS_DIRECTORY"]) / "telegram"
    env = dict(line.split("=", 1) for line in path.read_text().splitlines() if "=" in line)
    return env["TELEGRAM_BOT_TOKEN"], env["TELEGRAM_ALLOWED_USERS"].split(",")[0].strip()


def recent_sends(now):
    if not STATE.exists():
        return []
    return [t for t in (float(x) for x in STATE.read_text().split()) if now - t < 3600]


def tg(token, method, **params):
    data = urllib.parse.urlencode(params).encode()
    req = urllib.request.Request(f"https://api.telegram.org/bot{token}/{method}", data=data)
    with urllib.request.urlopen(req, timeout=15) as r:
        return json.load(r)


def temas(token, chat_id):
    """{nombre: message_thread_id}, creándolos si hace falta; {} si el chat no admite temas."""
    try:
        t = json.loads(TEMAS.read_text())
    except (OSError, ValueError):
        t = {}
    faltan = [n for n in NOMBRES_TEMAS if n not in t]
    if not faltan:
        return t
    try:  # solo los que faltan (09-11: «Redacción» se añade sin recrear los existentes)
        for n in faltan:
            t[n] = tg(token, "createForumTopic", chat_id=chat_id, name=n)["result"]["message_thread_id"]
    except Exception as exc:
        print(f"<4>Sin temas ({type(exc).__name__}); avisos en el chat general", flush=True)
        return t
    TEMAS.write_text(json.dumps(t))
    return t


def send(token, chat_id, text, hilo=None):
    if hilo:
        try:
            return tg(token, "sendMessage", chat_id=chat_id, text=text, message_thread_id=hilo).get("ok") is True
        except urllib.error.HTTPError:          # tema borrado: sin tema esta vez, se recrean la próxima
            TEMAS.unlink(missing_ok=True)
            print("<4>Tema no válido; enviado sin tema", flush=True)
    return tg(token, "sendMessage", chat_id=chat_id, text=text).get("ok") is True


def main():
    items = []
    for p in sorted(OUTBOX.iterdir()):
        if not p.name.startswith("."):
            items.append(p)
        elif time.time() - p.stat().st_mtime > 60:  # temporal huérfano: evita reactivar la .path sin fin
            p.unlink(missing_ok=True)
    if not items:
        return 0
    token, chat_id = load_credentials()
    hilos = temas(token, chat_id)
    for p in items:
        text = p.read_text(errors="replace").strip()[:MAX_CHARS] or "(aviso vacío)"
        p.unlink(missing_ok=True)
        now = time.time()
        sends = recent_sends(now)
        if len(sends) >= MAX_PER_HOUR:
            print(f"<4>Tope de {MAX_PER_HOUR} avisos/h; descartado: {p.name}", flush=True)
            continue
        try:
            tema = ("Peticiones" if p.name.startswith(PETICIONES) else
                    "Redacción" if p.name.startswith(REDACCION) else "Avisos")
            ok = send(token, chat_id, "SIP · " + text, hilos.get(tema))
        except Exception as exc:  # sin el token en el mensaje: urllib no lo incluye en la excepción
            print(f"<3>Fallo al enviar {p.name}: {type(exc).__name__}", flush=True)
            continue
        if ok:
            STATE.write_text("\n".join(str(t) for t in sends + [now]) + "\n")
        print(f"{p.name}: {'enviado' if ok else 'rechazado por Telegram'}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
