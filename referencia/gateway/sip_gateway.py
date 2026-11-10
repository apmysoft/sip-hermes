#!/usr/bin/env python3
"""sip-gateway: enrutador de Telegram a las zonas SIP, sin LLM (v2.4, Fase 7).

Política determinista: solo el UID permitido y en chat privado; la zona la elige el comando
(/r, /c, /p), se recuerda y se indica en cada respuesta. Cada zona se llama por su API (Responses API
de Hermes) en su red internal, con su clave. El gateway no tiene modelo, terminal ni PARA.
No registra el texto de los mensajes, solo metadatos.

Temas (pedido del usuario, 04-11): cada zona tiene su tema en el chat privado, que el gateway crea la
primera vez. Lo escrito en el tema de una zona va a esa zona sin comando, y la respuesta sale siempre en
el tema de la zona. Si el tema ya no existe, se responde en el general y se recrea en el siguiente envío.

Notas de voz (05-11): una nota de voz o un audio se baja de Telegram y se deja en /voz/requests; el
puente del host (sip-voz-bridge) lo transcribe con Whisper en HALO. El gateway muestra lo entendido y lo
envía a la zona como texto. El gateway sigue sin llegar a HALO y no registra el texto transcrito.
"""
import json
import os
import queue
import re
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
ALLOWED = {int(u) for u in os.environ["TELEGRAM_ALLOWED_USERS"].split(",") if u.strip()}
STATE = Path(os.environ.get("SIP_GATEWAY_STATE", "/data/state.json"))

# comando -> zona. Una zona sin url existe en la política pero aún no está conectada.
ZONES = {
    "r": {"name": "RESEARCH", "url": "http://10.22.0.10:8642", "key": os.environ.get("RESEARCH_API_KEY")},
    "c": {"name": "CODING", "url": "http://10.24.0.10:8642", "key": os.environ.get("CODING_API_KEY")},
    "p": {"name": "PERSONAL", "url": "http://10.25.0.10:8642", "key": os.environ.get("PERSONAL_API_KEY")},
}
ZONE_TIMEOUT = 1800  # 05-11: 600 -> 1800; una transcripción larga (sip-transcribir admite 1 h) superaba 10 min
MAX_INPUT = 4000
VOZ = Path(os.environ.get("SIP_VOZ_DIR", "/voz"))
VOZ_MAX_BYTES = 20 * 1024 * 1024   # límite de descarga de la API de bots
VOZ_MAX_SEG = 15 * 60
VOZ_ESPERA = 480
# Avisos de tareas en segundo plano (05-11): buzón por zona que escribe la API de esa zona (hoy solo PERSONAL).
# Formato fijo y validado; nunca se reenvía texto de la zona: el gateway construye sus propios mensajes.
AVISOS = Path(os.environ.get("SIP_AVISOS_DIR", "/avisos"))
AVISO_HERRAMIENTAS = {"audio_transcribir": "transcripción de audio", "imagen_generar": "generación de imagen",
                      "medios_procesar": "procesado de un fichero", "imagen_ampliar": "ampliación de imagen",
                      "musica_generar": "composición de música", "imagen_editar": "edición de imagen",
                      "video_generar": "generación de vídeo"}
AVISO_MAX_HORA = 12  # por zona; frena un bucle aviso -> tarea -> aviso
# Cola de PERSONAL (v2.4 §H.3, 09-11): si no responde ningún modelo local (HALO ni el tiny de Neo), el mensaje se guarda
# y se reintenta; jamás cloud. Persistente en el volumen de estado.
COLA = STATE.parent / "cola-personal.json"
COLA_MAX = 20
COLA_EDAD = 24 * 3600
COLA_REINTENTO = 600
_cola_lock = threading.Lock()
_avisos_hora = {}
HELP = (
    "Comandos:\n"
    "/r texto — RESEARCH (web, sin datos personales)\n"
    "/c texto — CODING (código en HALO; nada destructivo)\n"
    "/p texto — PERSONAL (tus documentos y el gestor; modelo local, sin Internet)\n"
    "En el tema de cada zona no hace falta comando; fuera de ellos, sin comando,\n"
    "el mensaje va a la última zona usada. Las notas de voz se transcriben en casa (Whisper en HALO).\n"
    "/zona — zona actual · /nueva — conversación nueva en la zona actual · /ayuda"
)


def log(msg):
    print(time.strftime("%Y-%m-%d %H:%M:%S"), msg, flush=True)


def load_state():
    try:
        return json.loads(STATE.read_text())
    except (OSError, ValueError):
        return {"offset": 0, "users": {}}


def save_state(state):
    tmp = STATE.with_suffix(".tmp")
    tmp.write_text(json.dumps(state))
    tmp.replace(STATE)


def tg(method, http_timeout=30, **params):
    data = urllib.parse.urlencode(params).encode()
    req = urllib.request.Request(f"https://api.telegram.org/bot{TOKEN}/{method}", data=data)
    with urllib.request.urlopen(req, timeout=http_timeout) as r:
        return json.load(r)


def say(chat_id, text, hilo=None):
    """Envía al tema `hilo` del chat privado (o al general). Devuelve False si el tema ya no existe."""
    extra = {"message_thread_id": hilo} if hilo else {}
    try:
        for i in range(0, max(len(text), 1), 4000):  # límite de Telegram: 4096
            tg("sendMessage", chat_id=chat_id, text=text[i:i + 4000] or "(vacío)", **extra)
    except urllib.error.HTTPError:
        if not hilo:
            raise
        log("tema no válido; respuesta en el general")
        say(chat_id, text)
        return False
    return True


INVALIDOS = set()  # temas que el worker vio borrados; el hilo principal los quita del estado


def tema(chat_id, temas, cmd):
    """Tema de la zona, creándolo si falta; None si no se puede (se responde en el general)."""
    if temas.get(cmd) in INVALIDOS:
        INVALIDOS.discard(temas.pop(cmd))
    if cmd not in temas:
        try:
            r = tg("createForumTopic", chat_id=chat_id, name=ZONES[cmd]["name"])
            temas[cmd] = r["result"]["message_thread_id"]
            log(f"tema creado zona={ZONES[cmd]['name']}")
        except Exception as e:
            log(f"sin tema zona={ZONES[cmd]['name']} {type(e).__name__}")
            return None
    return temas[cmd]


def ask_zone(zone, conversation, text):
    body = json.dumps({"model": "hermes-agent", "input": text, "conversation": conversation}).encode()
    req = urllib.request.Request(zone["url"] + "/v1/responses", data=body, headers={
        "Authorization": "Bearer " + zone["key"], "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=ZONE_TIMEOUT) as r:
        d = json.load(r)
    parts = [c.get("text", "") for o in d.get("output", []) if o.get("type") == "message"
             for c in o.get("content", [])]
    return "".join(parts).strip() or f"(sin texto; estado {d.get('status')})"


def transcribir_voz(voz):
    """Baja el audio de Telegram, lo deja al puente del host y espera el texto. Devuelve (ok, texto)."""
    if not VOZ.is_dir():
        return False, "notas de voz no disponibles (falta /voz)"
    f = tg("getFile", file_id=voz["file_id"])["result"]
    if f.get("file_size", 0) > VOZ_MAX_BYTES:
        return False, "audio de más de 20 MB"
    rid = os.urandom(16).hex()
    tmp = VOZ / "requests" / f".{rid}.tmp"
    url = f"https://api.telegram.org/file/bot{TOKEN}/{f['file_path']}"
    n = 0
    with urllib.request.urlopen(url, timeout=120) as r, open(tmp, "wb") as out:
        while True:
            b = r.read(1 << 16)
            if not b:
                break
            n += len(b)
            if n > VOZ_MAX_BYTES:
                out.close()
                tmp.unlink()
                return False, "audio de más de 20 MB"
            out.write(b)
    tmp.replace(VOZ / "requests" / f"{rid}.audio")
    res = VOZ / "results" / f"{rid}.json"
    t0 = time.time()
    while time.time() - t0 < VOZ_ESPERA:
        if res.exists():
            try:
                d = json.loads(res.read_text())
            except ValueError:
                time.sleep(1)
                continue
            res.unlink()
            log(f"voz {n // 1024} KiB transcrita={d.get('ok')} {time.time() - t0:.0f}s")
            return bool(d.get("ok")), d.get("texto") or d.get("error") or "sin texto"
        time.sleep(2)
    log("voz sin resultado a tiempo")
    return False, "la transcripción no llegó a tiempo (¿HALO apagado?)"


EN_CURSO = {}  # zona -> procesando un trabajo ahora (para el acuse)


def worker(jobs):
    """Una cola por zona: en orden dentro de la zona, sin esperar a la otra ni bloquear los comandos."""
    while True:
        chat_id, hilo, cmd, conversation, text, voz, *extra = jobs.get()
        reintento = extra[0] if extra else None  # reintento de la cola de PERSONAL: sin «escribiendo…»
        zone = ZONES[cmd]
        hecho = threading.Event()
        EN_CURSO[cmd] = True
        if not reintento:
            threading.Thread(target=escribiendo, args=(chat_id, hilo, hecho), daemon=True).start()
        try:
            procesar(chat_id, hilo, zone, conversation, text, voz, reintento)
        finally:
            hecho.set()
            EN_CURSO[cmd] = False


def escribiendo(chat_id, hilo, hecho):
    """Telegram quita «escribiendo…» a los 5 s: se renueva cada 4 s mientras la zona trabaja (máx. 30 min)."""
    for _ in range(450):
        try:
            tg("sendChatAction", http_timeout=10, chat_id=chat_id, action="typing",
               **({"message_thread_id": hilo} if hilo else {}))
        except Exception:
            pass  # solo es el indicador de escritura
        if hecho.wait(4):
            return


def leer_cola():
    try:
        return json.loads(COLA.read_text())
    except (OSError, ValueError):
        return []


def guardar_cola(cola):
    tmp = COLA.with_suffix(".tmp")
    tmp.write_text(json.dumps(cola))
    tmp.replace(COLA)


def sin_modelo(answer):
    """Respuesta de Hermes cuando todos los proveedores fallan (o estado failed de /v1/responses)."""
    return "every provider in the fallback chain" in answer or answer.startswith("(sin texto; estado failed")


def reintentar_cola(jobs):
    """Cada COLA_REINTENTO s, el primer mensaje de la cola vuelve a la cola de trabajo de PERSONAL."""
    while True:
        time.sleep(COLA_REINTENTO)
        try:
            with _cola_lock:
                cola, ahora = leer_cola(), time.time()
                for m in [m for m in cola if ahora - m["t"] > COLA_EDAD]:
                    say(m["chat_id"], f"[PERSONAL] Tu mensaje en cola desde las {time.strftime('%H:%M', time.localtime(m['t']))} "
                        "se descarta tras 24 h sin modelo local. Vuelve a enviarlo cuando quieras.", m["hilo"])
                cola = [m for m in cola if ahora - m["t"] <= COLA_EDAD]
                guardar_cola(cola)
            if cola and jobs["p"].qsize() == 0 and not EN_CURSO.get("p"):
                m = cola[0]
                jobs["p"].put((m["chat_id"], m["hilo"], "p", m["conversation"], m["text"], None, m))
        except Exception as e:
            log(f"cola {type(e).__name__}")


def procesar(chat_id, hilo, zone, conversation, text, voz, reintento=None):
    if voz:
        try:
            ok, texto = transcribir_voz(voz)
        except Exception as e:
            ok, texto = False, f"no se pudo bajar el audio ({type(e).__name__})"
            log(f"voz {type(e).__name__}")
        try:
            say(chat_id, f"🎤 [{zone['name']}] " + (f"«{texto}»" if ok else f"sin transcripción: {texto}"), hilo)
        except Exception:
            pass
        if not ok:
            return
        text = "[Nota de voz del usuario, transcrita automáticamente; puede tener errores]\n" + texto
    t0 = time.time()
    caido = False  # ningún modelo local / la zona no contesta: PERSONAL lo encola (v2.4 §H.3)
    try:
        answer = ask_zone(zone, conversation, text)
        caido = sin_modelo(answer)
        log(f"zona={zone['name']} {'sin modelo' if caido else 'ok'} {time.time() - t0:.0f}s")
    except urllib.error.HTTPError as e:
        answer = f"error de la zona (HTTP {e.code})"
        caido = e.code >= 500
        log(f"zona={zone['name']} HTTP {e.code}")
    except TimeoutError:
        answer = (f"sigue trabajando tras {ZONE_TIMEOUT // 60} min y he dejado de esperar. Puede que termine "
                  "igualmente: pregúntale por el resultado dentro de un rato.")
        log(f"zona={zone['name']} TimeoutError")
    except Exception as e:
        answer = f"la zona no responde ({type(e).__name__})"
        caido = isinstance(e, (urllib.error.URLError, ConnectionError))
        log(f"zona={zone['name']} {type(e).__name__}")
    if zone["name"] == "PERSONAL" and (caido or reintento):
        with _cola_lock:
            cola = leer_cola()
            if reintento:
                if caido:
                    return  # sigue sin modelo: se queda en la cola, sin molestar
                cola = [m for m in cola if m["id"] != reintento["id"]]
                guardar_cola(cola)
                answer = (f"(respuesta a tu mensaje en cola desde las "
                          f"{time.strftime('%H:%M', time.localtime(reintento['t']))}) {answer}")
            elif len(cola) >= COLA_MAX:
                answer = ("ahora no responde ningún modelo local y la cola está llena "
                          f"({COLA_MAX} mensajes). Vuelve a intentarlo más tarde; nunca se envía a la nube.")
            else:
                cola.append({"id": f"{int(time.time())}-{os.urandom(3).hex()}", "t": int(time.time()),
                             "chat_id": chat_id, "hilo": hilo, "conversation": conversation, "text": text})
                guardar_cola(cola)
                answer = ("ahora no responde ningún modelo local (ni HALO ni el de Neo). Tu mensaje queda en cola "
                          f"(n.º {len(cola)}) y te contesto en cuanto vuelvan; nunca se envía a la nube.")
                log(f"cola PERSONAL: {len(cola)}")
    try:
        if not say(chat_id, f"[{zone['name']}] {answer}", hilo):
            INVALIDOS.add(hilo)  # se recrea en el siguiente envío
    except Exception as e:
        log(f"envio fallido {type(e).__name__}")


def handle(msg, state, jobs):
    chat, user = msg.get("chat", {}), msg.get("from", {})
    uid = user.get("id")
    if chat.get("type") != "private" or uid not in ALLOWED:
        log(f"descartado: chat={chat.get('type')} uid_permitido={uid in ALLOWED}")
        return
    chat_id = chat["id"]
    hilo = msg.get("message_thread_id")

    def resp(texto):
        say(chat_id, texto, hilo)

    voz = msg.get("voice") or msg.get("audio")
    text = (msg.get("text") or msg.get("caption") or "").strip()
    if voz:
        if voz.get("duration", 0) > VOZ_MAX_SEG or voz.get("file_size", 0) > VOZ_MAX_BYTES:
            resp("Nota de voz demasiado larga (máx. 15 min / 20 MB).")
            return
        voz = {"file_id": voz["file_id"]}
        if not text.startswith("/"):
            text = ""  # el pie de un audio no es un mensaje; la zona la decide el tema o la última usada
    elif not text:
        resp("Solo texto o notas de voz.")
        return
    u = state["users"].setdefault(str(uid), {"zone": None, "n": {}})
    temas = u.setdefault("temas", {})
    # en el tema de una zona, esa zona; fuera, la última usada
    actual = next((z for z, t in temas.items() if t == hilo), None) or u["zone"]
    cmd, rest = None, text
    if text.startswith("/"):
        head, _, rest = text.partition(" ")
        head = head[1:].split("@")[0].lower()
        rest = rest.strip()
        if head in ZONES:
            cmd = head
        elif head in ("start", "ayuda", "help"):
            resp(HELP)
            return
        elif head == "zona":
            z = actual
            resp(f"Zona actual: {ZONES[z]['name']}" if z else "Sin zona. " + HELP)
            return
        elif head == "nueva":
            z = actual
            if not z:
                resp("Sin zona. " + HELP)
                return
            u["n"][z] = u["n"].get(z, 0) + 1
            resp(f"[{ZONES[z]['name']}] conversación nueva.")
            return
        else:
            resp("Comando desconocido.\n" + HELP)
            return
    else:
        cmd = actual
        if not cmd:
            resp("Elige zona con un comando.\n" + HELP)
            return
    zone = ZONES[cmd]
    if not zone["url"]:
        resp(f"[{zone['name']}] zona aún no conectada a Telegram.")
        return
    u["zone"] = cmd
    if voz:
        rest = ""
    elif not rest:
        resp(f"Zona: {zone['name']}. Escribe el mensaje.")
        return
    if len(rest) > MAX_INPUT:
        resp(f"Mensaje demasiado largo (máx. {MAX_INPUT} caracteres).")
        return
    conversation = f"tg-{uid}-{cmd}-{u['n'].get(cmd, 0)}"
    hilo_zona = tema(chat_id, temas, cmd)
    jobs[cmd].put((chat_id, hilo_zona, cmd, conversation, rest, voz))
    if hilo_zona and hilo != hilo_zona:
        resp(f"→ la respuesta saldrá en el tema {zone['name']}.")
    # Acuse inmediato (05-11): que se vea que el mensaje llegó aunque la zona tarde minutos.
    delante = jobs[cmd].qsize() - 1 + EN_CURSO.get(cmd, False)  # en cola + el que la zona está procesando
    que = "nota de voz recibida: la transcribo y se la paso a la zona" if voz else "recibido, trabajando en ello"
    try:
        say(chat_id, f"⏳ [{zone['name']}] {que}" + (f" (hay {delante} por delante)" if delante > 0 else "") + ".",
            hilo_zona)
    except Exception:
        pass  # el acuse no debe impedir el trabajo
    log(f"encolado zona={zone['name']} cola={jobs[cmd].qsize()}")


def leer_aviso(f):
    """Valida un aviso del buzón; devuelve (id, herramienta, estado) o None. El fichero se borra siempre."""
    try:
        st = f.lstat()
        datos = f.read_bytes()[:1024] if f.is_file() and not f.is_symlink() and st.st_size <= 512 else None
    except OSError:
        datos = None
    try:
        f.unlink()
    except OSError:
        pass
    try:
        d = json.loads(datos) if datos else None
    except ValueError:
        d = None
    if (not isinstance(d, dict) or set(d) != {"v", "id", "herramienta", "estado"} or d["v"] != 1
            or not isinstance(d["id"], str) or not re.fullmatch(r"[0-9a-f]{12}", d["id"])
            or d["herramienta"] not in AVISO_HERRAMIENTAS or d["estado"] not in ("ok", "error")):
        return None
    return d["id"], d["herramienta"], d["estado"]


def procesar_avisos(state, jobs):
    for cmd, zone in ZONES.items():
        buzon = AVISOS / cmd
        if not zone["url"] or not buzon.is_dir():
            continue
        try:
            ficheros = sorted(x for x in buzon.iterdir() if x.suffix == ".json")[:10]
        except OSError:
            continue
        for f in ficheros:
            aviso = leer_aviso(f)
            if not aviso:
                log(f"aviso descartado (formato) zona={zone['name']}")
                continue
            tid, herramienta, estado = aviso
            ahora = time.time()
            recientes = [t for t in _avisos_hora.get(cmd, []) if ahora - t < 3600]
            if len(recientes) >= AVISO_MAX_HORA:
                log(f"aviso descartado (más de {AVISO_MAX_HORA}/h) zona={zone['name']}")
                continue
            _avisos_hora[cmd] = recientes + [ahora]
            destino = [uid for uid in ALLOWED if str(uid) in state["users"]]
            if len(destino) != 1:
                log(f"aviso sin destinatario único zona={zone['name']} candidatos={len(destino)}")
                continue
            uid = destino[0]
            u = state["users"][str(uid)]
            hilo = tema(uid, u.setdefault("temas", {}), cmd)  # chat privado: chat_id == id del usuario
            conversation = f"tg-{uid}-{cmd}-{u.setdefault('n', {}).get(cmd, 0)}"
            que = AVISO_HERRAMIENTAS[herramienta]
            try:
                say(uid, f"⏰ [{zone['name']}] terminó una tarea en segundo plano ({que}"
                         + (", con error" if estado == "error" else "") + "): te paso el resultado.", hilo)
            except Exception as e:
                log(f"envio fallido {type(e).__name__}")
            texto = (f"[Aviso automático del sistema SIP; no lo ha escrito el usuario] La tarea en segundo plano "
                     f"{tid} ({herramienta}) ha terminado con estado «{estado}». Recógela con "
                     f"tarea_resultado(id=\"{tid}\") y comunícale el resultado al usuario. Si es una transcripción "
                     "larga, haz un resumen breve y dile dónde está guardado el texto completo.")
            jobs[cmd].put((uid, hilo, cmd, conversation, texto, None))
            log(f"aviso encolado zona={zone['name']} estado={estado}")


def main():
    state = load_state()
    jobs = {z: queue.Queue() for z in ZONES}
    for q in jobs.values():
        threading.Thread(target=worker, args=(q,), daemon=True).start()
    threading.Thread(target=reintentar_cola, args=(jobs,), daemon=True).start()
    # 06-11: un «Connection reset» de Telegram en esta primera llamada tumbaba el proceso (lo levantaba Docker).
    # Se reintenta con espera creciente; si no hay forma, se arranca igual: el menú de comandos no es esencial.
    comandos = json.dumps([
        {"command": "r", "description": "RESEARCH"}, {"command": "c", "description": "CODING"},
        {"command": "zona", "description": "Zona actual"}, {"command": "nueva", "description": "Conversación nueva"},
        {"command": "ayuda", "description": "Ayuda"}])
    for intento in range(6):
        try:
            tg("setMyCommands", commands=comandos)
            break
        except Exception as e:
            log(f"setMyCommands {type(e).__name__} (intento {intento + 1})")
            time.sleep(min(5 * 2 ** intento, 60))
    else:
        log("setMyCommands: sin menú de comandos; sigo")
    log(f"arrancado; zonas conectadas: {[z['name'] for z in ZONES.values() if z['url']]}")
    while True:
        try:
            # 20 s (antes 50): entre esperas se revisa el buzón de avisos
            r = tg("getUpdates", http_timeout=30, offset=state["offset"], timeout=20,
                   allowed_updates=json.dumps(["message"]))
        except Exception as e:
            log(f"getUpdates {type(e).__name__}")
            time.sleep(5)
            continue
        for upd in r.get("result", []):
            state["offset"] = upd["update_id"] + 1
            if "message" in upd:
                try:
                    handle(upd["message"], state, jobs)
                except Exception as e:
                    log(f"handle {type(e).__name__}")
        try:
            procesar_avisos(state, jobs)
        except Exception as e:
            log(f"avisos {type(e).__name__}")
        save_state(state)


if __name__ == "__main__":
    sys.exit(main())
