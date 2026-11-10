#!/usr/bin/env python3
"""sip-gestor-request.py — puente host entre Hermes y el Gestor de Entrada.

Lo ejecuta systemd como `sip-gestor` (mismo usuario que el gestor), disparado
por `sip-gestor-bridge.path` cuando aparece un fichero en requests/.

Superficie única y cerrada:
  {"id":"...", "action":"scan"}                  # opcional "max_items": 1..50
  {"id":"...", "action":"status"}
  {"id":"...", "action":"apply", "lote":"lote-YYYYMMDD-HHMMSS"}
  {"id":"...", "action":"lotes"}                 # estados, sin nombres de fichero
  {"id":"...", "action":"ver", "lote":"..."}     # copia el .md del lote a results/<id>/
  {"id":"...", "action":"ver", "lote":"...", "bloque":2}   # solo los ítems 11-20, en lista
  {"id":"...", "action":"anotar", "lote":"...", "bloque":2, "modo":"todo|ninguno|solo",
   "solo":[11,12], "veto":[13], "nombres":{"14":"Nuevo.docx"}}   # se guarda en Neo, no decide
  {"id":"...", "action":"proponer", "lote":"...", "modo":"todo|ninguno|solo",
   "solo":[1,2], "veto":[3,7], "nombres":{"6":"Nuevo.docx"}}
  {"id":"...", "action":"proponer", "lote":"...", "modo":"anotado"}  # junta los bloques anotados
  {"id":"...", "action":"confirmar", "lote":"...", "codigo":"123456"}

`apply` exige que el lote tenga YA una aprobación humana escrita en su .json
(approve_all=true, o algún approved=true sin veto). Este worker no aprueba por
su cuenta: `proponer` solo guarda un borrador (fuera del volumen de Hermes) y
manda al usuario por Telegram un resumen con números y un código de un solo
uso; únicamente `confirmar` con ese código escribe la decisión y aplica. Hermes
no ve el código: se lo da el usuario. Por Telegram no viajan nombres de fichero.

No usa shell: los argumentos van como lista a subprocess. No sigue symlinks.
"""
import hashlib
import hmac
import json
import os
import re
import secrets
import shutil
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

ROOT = Path(os.environ.get("GE_BRIDGE_ROOT",
                           "${DOCKER_DATA}/hermes/workspace/_gestor"))
VISTA = os.environ.get("GE_BRIDGE_VISTA", "/workspace/_gestor")
REQ = ROOT / "requests"
RES = ROOT / "results"
DONE = ROOT / "processed"
INFORMES = Path(os.environ.get("GE_INFORMES",
                               "${STAGING_ROOT}/_staging/_informes"))
GESTOR = os.environ.get("GE_GESTOR", "/usr/local/bin/gestor-entrada.py")
# Borradores y fallos: fuera del volumen de Hermes.
BORRADORES = Path(os.environ.get("GE_BORRADORES", "/var/lib/sip-gestor-entrada/borradores"))
OUTBOX = Path(os.environ.get("GE_OUTBOX", "/var/lib/sip-notify/outbox"))

MAX_BYTES = 64 * 1024
ID_RE = re.compile(r"^[A-Za-z0-9._-]{1,64}$")
LOTE_RE = re.compile(r"^lote-\d{8}-\d{6}$")
ACTIONS = {"scan", "status", "apply", "lotes", "ver", "anotar", "proponer", "confirmar"}
BLOQUE = 10               # ítems por bloque: el modelo local no aguanta revisar 50 de una vez (03-11)
CADUCA_S = 30 * 60
INTENTOS = 3              # por borrador
FALLOS_DIA = 10           # en total; al llegar, se bloquea confirmar 24 h


def now():
    return datetime.now().astimezone().isoformat(timespec="seconds")


def log(msg):
    print(msg, flush=True)


def write_result(rid, payload):
    payload = {"id": rid, "ts": now(), **payload}
    tmp = RES / f".{rid}.tmp"
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2),
                   encoding="utf-8")
    os.replace(tmp, RES / f"{rid}.json")


def run(args, env=None):
    e = os.environ.copy()
    if env:
        e.update(env)
    return subprocess.run([GESTOR, *args], capture_output=True, text=True,
                          timeout=1800, env=e)


def lote_aprobado(lote):
    """True solo si el humano ya aprobó el lote en su .json."""
    fecha = lote[5:13]                      # lote-YYYYMMDD-...
    p = INFORMES / fecha / f"{lote}.json"
    try:
        if p.is_symlink() or p.stat().st_size > 2 * 1024 * 1024:
            return False, "lote no válido"
        d = json.loads(p.read_text(encoding="utf-8"))
    except Exception as ex:
        return False, f"no se pudo leer el lote: {type(ex).__name__}"
    items = d.get("items") or []
    if d.get("approve_all") is True:
        return True, "approve_all en el lote"
    if any(i.get("approved") is True and not i.get("veto") for i in items):
        return True, "approved individual en el lote"
    return False, "sin aprobación humana en el lote"


def items_lote(lote):
    """Ítems del .json del lote ({número: ítem}). ValueError si no se puede leer."""
    p = INFORMES / lote[5:13] / f"{lote}.json"
    if p.is_symlink() or not p.is_file() or p.stat().st_size > 2 * 1024 * 1024:
        raise ValueError("lote no encontrado")
    return {i["item"]: i for i in json.loads(p.read_text(encoding="utf-8"))["items"]}


def rango_bloque(req, items):
    b = req.get("bloque")
    total = (len(items) + BLOQUE - 1) // BLOQUE
    if not isinstance(b, int) or isinstance(b, bool) or not 1 <= b <= total:
        raise ValueError(f"bloque debe ser 1..{total}")
    return b, total, [n for n in sorted(items) if (n - 1) // BLOQUE + 1 == b]


def ver_bloque(rid, req, lote):
    try:
        items = items_lote(lote)
        b, total, nums = rango_bloque(req, items)
    except ValueError as ex:
        return {"ok": False, "error": str(ex)}
    lineas = [f"Lote {lote} · bloque {b} de {total} (ítems {nums[0]}-{nums[-1]})", ""]
    for n in nums:
        it = items[n]
        if "inyección" in (it.get("motivo") or ""):
            lineas.append(f"{n}. {it['nombre_actual']}\n   (⚠ posible inyección en el documento: míralo "
                          "tú antes de decidir; se queda igual salvo que le des nombre)")
        elif it["abstencion"]:
            lineas.append(f"{n}. {it['nombre_actual']}\n   (sin propuesta: se queda igual salvo que le des nombre)")
        else:
            lineas.append(f"{n}. {it['nombre_actual']}\n   → {it['nombre_propuesto']}")
    dst = RES / rid
    dst.mkdir(exist_ok=True)
    (dst / f"{lote}-bloque{b}.txt").write_text("\n".join(lineas) + "\n", encoding="utf-8")
    return {"ok": True, "bloque": b, "bloques": total, "items": [nums[0], nums[-1]],
            "informe": vista(dst / f"{lote}-bloque{b}.txt")}


def _anotado(lote):
    try:
        return json.loads((BORRADORES / f"{lote}.anotado.json").read_text(encoding="utf-8"))
    except Exception:
        return {"bloques": {}}


def anotar(rid, req, lote):
    """Guarda la decisión de un bloque (fuera del volumen de Hermes). No decide nada."""
    try:
        items = items_lote(lote)
        b, total, nums = rango_bloque(req, items)
        args, veto, nombrados = args_decision(req)
        fuera = [n for n in set(veto) | set(nombrados) | set(req.get("solo") or []) if n not in nums]
        if fuera:
            raise ValueError(f"ítems fuera del bloque {b} ({nums[0]}-{nums[-1]}): {rangos(fuera)}")
    except ValueError as ex:
        return {"ok": False, "error": str(ex)}
    modo = req["modo"]
    base = set(nums) if modo == "todo" else set(req.get("solo") or []) if modo == "solo" else set()
    aprobados = (base - set(veto)) | set(nombrados)   # dar nombre a un ítem es aprobarlo
    nombres = {str(int(k)): v for k, v in (req.get("nombres") or {}).items()}
    a = _anotado(lote)
    a["bloques"][str(b)] = {"aprobados": sorted(aprobados), "nombres": nombres}
    BORRADORES.mkdir(mode=0o700, exist_ok=True)
    (BORRADORES / f"{lote}.anotado.json").write_text(json.dumps(a, ensure_ascii=False))
    hechos = sorted(int(k) for k in a["bloques"])
    faltan = [x for x in range(1, total + 1) if x not in hechos]
    return {"ok": True, "bloque": b, "aprobados_en_bloque": len(aprobados),
            "bloques_anotados": hechos, "faltan": faltan,
            "siguiente": f"ver bloque {faltan[0]}" if faltan else "proponer con modo anotado"}


def args_anotado(lote):
    """Junta los bloques anotados en una petición de proponer. ValueError si falta alguno."""
    items = items_lote(lote)
    total = (len(items) + BLOQUE - 1) // BLOQUE
    a = _anotado(lote)["bloques"]
    faltan = [b for b in range(1, total + 1) if str(b) not in a]
    if faltan:
        raise ValueError(f"faltan bloques por anotar: {rangos(faltan)}")
    aprobados = sorted({n for x in a.values() for n in x["aprobados"]})
    nombres = {k: v for x in a.values() for k, v in x["nombres"].items()}
    if not aprobados:
        return {"modo": "ninguno"}
    return {"modo": "solo", "solo": aprobados, "nombres": nombres}


def vista(p):
    """Ruta tal como la ve Hermes en su contenedor (el puente está montado en /workspace/_gestor)."""
    return VISTA + "/" + str(Path(p).relative_to(ROOT))


def avisar(texto):
    """Aviso a Telegram por la bandeja de sip-notify (tmp + rename en el mismo directorio)."""
    nombre = f"gestor-{int(time.time())}-{secrets.token_hex(3)}"
    tmp = OUTBOX / f".{nombre}.tmp"
    tmp.write_text(texto[:1000], encoding="utf-8")
    os.replace(tmp, OUTBOX / f"{nombre}.txt")


def rangos(nums):
    """[3, 7, 39, 40, 41] -> '3, 7, 39-41'"""
    out, nums = [], sorted(nums)
    i = 0
    while i < len(nums):
        j = i
        while j + 1 < len(nums) and nums[j + 1] == nums[j] + 1:
            j += 1
        out.append(str(nums[i]) if i == j else f"{nums[i]}-{nums[j]}")
        i = j + 1
    return ", ".join(out) or "ninguno"


def _enteros(v, campo):
    if not isinstance(v, list) or len(v) > 200 or not all(
            isinstance(x, int) and not isinstance(x, bool) and 1 <= x <= 999 for x in v):
        raise ValueError(f"{campo} debe ser una lista de números de ítem")
    return sorted(set(v))


def args_decision(req):
    """Petición de Hermes -> argumentos de `gestor-entrada.py decidir`. ValueError si no es válida."""
    modo = req.get("modo")
    if modo not in ("todo", "ninguno", "solo"):
        raise ValueError("modo debe ser todo, ninguno o solo")
    args = [modo] if modo != "solo" else ["solo=" + ",".join(map(str, _enteros(req.get("solo"), "solo")))]
    veto = _enteros(req.get("veto") or [], "veto")
    if veto:
        args.append("veto=" + ",".join(map(str, veto)))
    nombres = req.get("nombres") or {}
    if not isinstance(nombres, dict) or len(nombres) > 50:
        raise ValueError("nombres debe ser {\"ítem\": \"nombre\"}")
    for k, v in sorted(nombres.items()):
        if not (isinstance(k, str) and k.isdigit() and isinstance(v, str) and 0 < len(v) <= 150):
            raise ValueError("nombres debe ser {\"ítem\": \"nombre\"}")
        args.append(f"nombre={int(k)}:{v}")
    return args, veto, sorted(int(k) for k in nombres)


def _fallos():
    p = BORRADORES / "fallos.json"
    try:
        return [t for t in json.loads(p.read_text()) if t > time.time() - 86400]
    except Exception:
        return []


def _apuntar_fallo():
    f = _fallos() + [time.time()]
    (BORRADORES / "fallos.json").write_text(json.dumps(f))
    return len(f)


def proponer(rid, req, lote):
    anotado = req.get("modo") == "anotado"
    try:
        if anotado:
            req = args_anotado(lote)
        args, veto, nombrados = args_decision(req)
    except ValueError as ex:
        return {"ok": False, "error": str(ex)}
    r = run(["decidir", lote, *args, "simular"])
    if r.returncode != 0:
        return {"ok": False, "error": (r.stderr or r.stdout).strip()[-500:]}
    resumen = r.stdout.strip().split(": ", 1)[-1]
    codigo = f"{secrets.randbelow(10**6):06d}"
    BORRADORES.mkdir(mode=0o700, exist_ok=True)
    borrador = {"lote": lote, "args": args, "creado": time.time(), "intentos": 0, "resumen": resumen,
                "codigo_sha256": hashlib.sha256(codigo.encode()).hexdigest()}
    (BORRADORES / f"{lote}.json").write_text(json.dumps(borrador, ensure_ascii=False))
    pedido = (f"Aprobados (por bloques): {rangos(req.get('solo') or [])}" if anotado
              else f"Vetos pedidos: {rangos(veto)}")
    avisar(f"Gestor de entrada: borrador para {lote}\n{resumen}.\n"
           f"{pedido}. Nombres dados a mano: {rangos(nombrados)}.\n"
           f"Código: {codigo} (caduca en 30 min)\n"
           f"Dáselo a Hermes solo si cuadra con lo que le pediste.")
    return {"ok": True, "resumen": resumen,
            "siguiente": "pide al usuario el código que le ha llegado por Telegram y usa confirmar"}


def confirmar(rid, req, lote):
    if len(_fallos()) >= FALLOS_DIA:
        return {"ok": False, "error": "confirmaciones bloqueadas 24 h por demasiados códigos erróneos"}
    p = BORRADORES / f"{lote}.json"
    try:
        b = json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return {"ok": False, "error": "no hay borrador para ese lote: usa proponer"}
    if time.time() - b["creado"] > CADUCA_S:
        p.unlink(missing_ok=True)
        return {"ok": False, "error": "borrador caducado: vuelve a proponer"}
    codigo = str(req.get("codigo") or "")
    if not hmac.compare_digest(hashlib.sha256(codigo.encode()).hexdigest(), b["codigo_sha256"]):
        b["intentos"] += 1
        n = _apuntar_fallo()
        if b["intentos"] >= INTENTOS:
            p.unlink(missing_ok=True)
            avisar(f"Gestor de entrada: borrador de {lote} anulado tras {INTENTOS} códigos erróneos.")
            return {"ok": False, "error": "código erróneo; borrador anulado"}
        p.write_text(json.dumps(b, ensure_ascii=False))
        if n >= FALLOS_DIA:
            avisar("Gestor de entrada: confirmaciones bloqueadas 24 h por demasiados códigos erróneos.")
        return {"ok": False, "error": f"código erróneo ({INTENTOS - b['intentos']} intentos más)"}
    p.unlink(missing_ok=True)                # un solo uso
    env = {"GE_DECIDIDO_POR": "usuario (código de Telegram)"}
    r = run(["decidir", lote, *b["args"], "via=hermes"], env)
    if r.returncode != 0:
        return {"ok": False, "error": (r.stderr or r.stdout).strip()[-500:]}
    (BORRADORES / f"{lote}.anotado.json").unlink(missing_ok=True)
    r = run(["apply", lote])
    salida = (r.stderr or "").strip().splitlines()
    final = next((l.split("] ", 1)[-1] for l in reversed(salida) if f"apply {lote}:" in l), "")
    avisar(f"Gestor de entrada: {final or lote + ' aplicado'}.")
    return {"ok": r.returncode == 0, "resultado": final, "stderr": (r.stderr or "")[-2000:]}


def handle(p):
    """Procesa una petición y la retira SIEMPRE de requests/.

    Si una petición rechazada se quedara en requests/, la unidad .path
    volvería a disparar el servicio en bucle. Por eso el archivado va en
    `finally`, cubriendo también los `return` tempranos.
    """
    rid = p.stem
    if not ID_RE.match(rid):
        p.unlink(missing_ok=True)
        return
    try:
        _process(p, rid)
    finally:
        try:
            shutil.move(str(p), DONE / p.name)
        except Exception:
            p.unlink(missing_ok=True)


def _process(p, rid):
    try:
        if p.is_symlink() or not p.is_file() or p.stat().st_size > MAX_BYTES:
            write_result(rid, {"ok": False, "error": "petición no válida"})
            return
        req = json.loads(p.read_text(encoding="utf-8"))
    except PermissionError:
        write_result(rid, {"ok": False, "error": "no puedo leer la petición (permisos): avisa al "
                           "usuario; falla sip-gestor-permisos.service en Neo"})
        return
    except Exception as ex:
        write_result(rid, {"ok": False,
                           "error": f"JSON inválido: {type(ex).__name__}"})
        return
    action = req.get("action")
    if action not in ACTIONS:
        write_result(rid, {"ok": False, "error": "acción no permitida"})
        return

    if action == "scan":
        env = {}
        mi = req.get("max_items")
        if mi is not None:
            if not isinstance(mi, int) or isinstance(mi, bool) or not 1 <= mi <= 50:
                write_result(rid, {"ok": False,
                                   "error": "max_items debe ser 1..50"})
                return
            env["GE_MAX_ITEMS"] = str(mi)
        r = run(["scan"], env)
        out = (r.stdout or "").strip().splitlines()
        lote = out[-1] if out and LOTE_RE.match(out[-1]) else None
        payload = {"action": action, "ok": r.returncode == 0, "lote": lote,
                   "stdout": (r.stdout or "")[-2000:],
                   "stderr": (r.stderr or "")[-2000:]}
        if r.returncode == 0 and lote:
            fecha = lote[5:13]
            dst = RES / rid
            dst.mkdir(exist_ok=True)
            for ext in (".json", ".md"):
                src = INFORMES / fecha / f"{lote}{ext}"
                if src.is_file():
                    shutil.copy2(src, dst / src.name)
            payload["informe"] = vista(dst)
    elif action in ("status", "lotes"):
        r = run([action])
        payload = {"action": action, "ok": r.returncode == 0,
                   "stdout": (r.stdout or "")[-4000:],
                   "stderr": (r.stderr or "")[-2000:]}
    elif action in ("ver", "anotar", "proponer", "confirmar"):
        lote = str(req.get("lote") or "")
        if not LOTE_RE.match(lote):
            write_result(rid, {"ok": False, "error": "lote no válido"})
            return
        if action == "ver" and "bloque" in req:
            payload = ver_bloque(rid, req, lote)
        elif action == "anotar":
            payload = anotar(rid, req, lote)
        elif action == "ver":
            src = INFORMES / lote[5:13] / f"{lote}.md"
            if src.is_symlink() or not src.is_file():
                payload = {"ok": False, "error": "lote no encontrado"}
            else:
                dst = RES / rid
                dst.mkdir(exist_ok=True)
                shutil.copyfile(src, dst / src.name)
                payload = {"ok": True, "informe": vista(dst / src.name)}
        elif action == "proponer":
            payload = proponer(rid, req, lote)
        else:
            payload = confirmar(rid, req, lote)
        payload = {"action": action, "lote": lote, **payload}
    else:                                   # apply
        lote = str(req.get("lote") or "")
        if not LOTE_RE.match(lote):
            write_result(rid, {"ok": False, "error": "lote no válido"})
            return
        ok, why = lote_aprobado(lote)
        if not ok:
            write_result(rid, {"action": action, "ok": False, "lote": lote,
                               "error": why})
            return
        r = run(["apply", lote])
        payload = {"action": action, "ok": r.returncode == 0, "lote": lote,
                   "stdout": (r.stdout or "")[-2000:],
                   "stderr": (r.stderr or "")[-2000:]}

    write_result(rid, payload)


def main():
    for d in (REQ, RES, DONE):
        d.mkdir(parents=True, exist_ok=True)
    for p in sorted(REQ.glob("*.json")):
        log(f"procesando {p.name}")
        try:
            handle(p)
        except Exception as ex:
            write_result(p.stem, {"ok": False,
                                  "error": f"fallo interno: {type(ex).__name__}"})
    return 0


if __name__ == "__main__":
    sys.exit(main())
