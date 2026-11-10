#!/usr/bin/env python3
"""sip-energia.py — apagado de HALO desde Neo (05-11). Usuario sip-wol (WOL y avisos ya son suyos).

  sip-energia.py auto         # sip-energia-auto.timer, cada 5 min: si HALO lleva 60 min sin nada que lo
                              # impida, lo apaga (HALO vuelve a comprobar) y avisa por Telegram
  sip-energia.py peticiones   # sip-energia.path: puente de PERSONAL en /workspace/_energia

Puente (solo PERSONAL; CODING no monta esta carpeta):
  {"id":"...","action":"estado"}                            # qué está haciendo HALO (sin efecto)
  {"id":"...","action":"proponer"}                          # código de 6 cifras al usuario por Telegram
  {"id":"...","action":"confirmar","borrador":"...","codigo":"123456"}

Con el código, manda la decisión del usuario aunque haya algo activo (lo ha visto al proponer). Si al confirmar
HALO hace algo distinto de lo que vio (otra huella), no se apaga y hay que proponer de nuevo.
Con HALO solo se habla por SSH con la clave de sip-energia, que allí solo admite tres órdenes fijas.
"""
import hashlib
import hmac
import json
import os
import re
import secrets
import subprocess
import sys
import time
from pathlib import Path

HALO = "${HALO_TAILNET_IP}"
STATE = Path(os.environ.get("SIP_ENERGIA_STATE", "/var/lib/sip-energia"))
KEY = STATE / "id_ed25519"
KNOWN = STATE / "known_hosts"
BORRADORES = STATE / "borradores"
ROOT = Path(os.environ.get("SIP_ENERGIA_ROOT", "${DOCKER_DATA}/hermes/workspace/_energia"))
OUTBOX = Path(os.environ.get("SIP_NOTIFY_OUTBOX", "/var/lib/sip-notify/outbox"))
ID_RE = re.compile(r"^[A-Za-z0-9._-]{1,64}$")
MAX_BYTES = 4096
CADUCA_S = 10 * 60
INTENTOS = 3
FALLOS_DIA = 10
TAPO = ("Si apagas también el enchufe Tapo, HALO no podrá despertarse por WOL hasta que lo vuelvas a "
        "encender (al volver la corriente arranca solo).")


def halo(orden):
    """Ejecuta una orden fija en HALO. None si no responde (apagado o sin red)."""
    try:
        r = subprocess.run(
            ["ssh", "-F", "/dev/null", "-i", str(KEY), "-o", "IdentitiesOnly=yes", "-o", "BatchMode=yes",
             "-o", f"UserKnownHostsFile={KNOWN}", "-o", "StrictHostKeyChecking=yes", "-o", "ConnectTimeout=8",
             "-o", "ServerAliveInterval=10", "-o", "ServerAliveCountMax=3", f"sip-energia@{HALO}", orden],
            capture_output=True, text=True, timeout=120)
    except subprocess.TimeoutExpired:
        return None
    if r.returncode == 255:  # conexión
        return None
    try:
        return json.loads(r.stdout)
    except ValueError:
        return {"ok": False, "error": "respuesta no válida de HALO"}


def abiertos(estado):
    return [i.removesuffix(" abierto") for i in estado.get("info", []) if i.endswith(" abierto")]


def avisar(prefijo, texto):
    nombre = f"{prefijo}-{int(time.time())}-{secrets.token_hex(3)}"
    tmp = OUTBOX / f".{nombre}.tmp"  # dentro de la bandeja: rename entre montajes da EXDEV
    tmp.write_text(texto[:1000] + "\n", encoding="utf-8")
    tmp.replace(OUTBOX / f"{nombre}.txt")


def auto():
    e = halo("estado")
    if e is None:
        print("HALO no responde (apagado o sin red): nada que hacer", flush=True)
        return 0
    if "bloqueos" not in e:
        print(f"<4>estado no válido: {e.get('error')}", flush=True)
        return 0
    print(f"HALO: {len(e['bloqueos'])} bloqueo(s), {e['inactivo_min']}/{e['umbral_min']} min sin actividad"
          + (f" [{', '.join(e.get('claves', []))}]" if e.get("claves") else ""), flush=True)
    if e["bloqueos"] or e["inactivo_min"] < e["umbral_min"]:
        return 0
    r = halo("apagar-auto")
    if not r or not r.get("ok"):
        print(f"HALO no se apaga: {(r or {}).get('error', 'sin respuesta')}", flush=True)
        return 0
    ab = abiertos(r)
    avisar("energia", f"HALO se ha apagado por inactividad ({e['umbral_min']} min sin uso)."
           + (f" Seguía abierto: {', '.join(ab)}." if ab else "") + " " + TAPO)
    print("HALO apagado por inactividad", flush=True)
    return 0


# --- Puente de PERSONAL -----------------------------------------------------------------------------------
def resumen(e):
    return {"halo": "encendido", "bloqueos": e.get("bloqueos", []), "abierto": abiertos(e),
            "detalle": [i for i in e.get("info", []) if not i.endswith(" abierto")],
            "minutos_sin_actividad": e.get("inactivo_min"), "apagado_automatico_a_los_min": e.get("umbral_min")}


def proponer():
    e = halo("estado")
    if e is None:
        return {"ok": False, "halo": "apagado o no responde", "error": "HALO ya está apagado o no responde"}
    if "huella" not in e:
        return {"ok": False, "error": e.get("error", "estado no válido")}
    codigo = f"{secrets.randbelow(10**6):06d}"
    bid = f"apagar-{secrets.token_hex(4)}"
    BORRADORES.mkdir(mode=0o700, parents=True, exist_ok=True)
    (BORRADORES / f"{bid}.json").write_text(json.dumps({
        "huella": e["huella"], "creado": time.time(), "intentos": 0,
        "codigo_sha256": hashlib.sha256(codigo.encode()).hexdigest()}))
    activo = "; ".join(e["bloqueos"]) or "nada activo"
    ab = abiertos(e)
    avisar("wol-apagar", f"Apagar HALO. Ahora mismo: {activo}."
           + (f" Abierto: {', '.join(ab)}." if ab else "")
           + f" Si quieres apagarlo, dale a Hermes este código: {codigo} (caduca en 10 min). "
             "Si no lo has pedido tú, ignóralo.")
    return {"ok": True, "borrador": bid, **resumen(e),
            "siguiente": "cuéntale al usuario lo que está activo y pídele el código que le ha llegado por Telegram"}


def confirmar(req):
    f = STATE / "fallos.json"
    hoy = time.strftime("%F")
    try:
        fallos = json.loads(f.read_text())
    except (OSError, ValueError):
        fallos = {}
    if fallos.get(hoy, 0) >= FALLOS_DIA:
        return {"ok": False, "error": "confirmaciones bloqueadas hoy por demasiados códigos erróneos"}
    bid = str(req.get("borrador") or "")
    p = BORRADORES / f"{bid}.json"
    if not ID_RE.match(bid) or not p.is_file():
        return {"ok": False, "error": "borrador no encontrado"}
    b = json.loads(p.read_text())
    if time.time() - b["creado"] > CADUCA_S:
        p.unlink()
        return {"ok": False, "error": "borrador caducado; vuelve a proponer"}
    if not hmac.compare_digest(hashlib.sha256(str(req.get("codigo") or "").encode()).hexdigest(), b["codigo_sha256"]):
        b["intentos"] += 1
        f.write_text(json.dumps({hoy: fallos.get(hoy, 0) + 1}))
        if b["intentos"] >= INTENTOS:
            p.unlink()
            avisar("wol-apagar", f"Apagar HALO: petición anulada tras {INTENTOS} códigos erróneos.")
            return {"ok": False, "error": "código erróneo; petición anulada"}
        p.write_text(json.dumps(b))
        return {"ok": False, "error": f"código erróneo ({INTENTOS - b['intentos']} intentos más)"}
    p.unlink()
    r = halo(f"apagar-usuario {b['huella']}")
    if r is None:
        return {"ok": False, "error": "HALO no responde (puede que ya esté apagado)"}
    if not r.get("ok"):
        return {"ok": False, "error": r.get("error", "no se pudo apagar"),
                **(resumen(r["estado"]) if isinstance(r.get("estado"), dict) else {})}
    avisar("energia", f"HALO se apaga a petición tuya en {r.get('apagado_en_s', 20)} s. {TAPO}")
    return {"ok": True, "apagado_en_s": r.get("apagado_en_s"), "nota": TAPO}


def peticiones():
    req_dir, res_dir = ROOT / "requests", ROOT / "results"
    time.sleep(1)  # deja terminar la escritura que ha disparado la unidad
    for ent in sorted(os.scandir(req_dir), key=lambda x: x.name):
        rid = ent.name[:-5] if ent.name.endswith(".json") else ""
        accion = None
        try:
            if not ID_RE.match(rid):
                raise ValueError("nombre")
            fd = os.open(ent.path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
            with os.fdopen(fd, "rb") as fh:
                st = os.fstat(fh.fileno())
                if (st.st_mode & 0o170000) != 0o100000 or st.st_size > MAX_BYTES:
                    raise ValueError("tipo")
                req = json.loads(fh.read(MAX_BYTES + 1).decode("utf-8"))
            assert isinstance(req, dict)
            accion = req.get("action")
            if accion == "estado":
                e = halo("estado")
                res = {"ok": True, "halo": "apagado o no responde"} if e is None else \
                    ({"ok": True, **resumen(e)} if "bloqueos" in e else {"ok": False, "error": e.get("error")})
            elif accion == "proponer":
                res = proponer()
            elif accion == "confirmar":
                res = confirmar(req)
            else:
                res = {"ok": False, "error": "acción no permitida", "acciones": ["estado", "proponer", "confirmar"]}
        except Exception as ex:  # noqa: BLE001 — siempre hay resultado y la petición se retira
            res = {"ok": False, "error": f"petición no válida ({type(ex).__name__})"}
        finally:
            try:
                os.unlink(ent.path)
            except OSError:
                pass
        if rid and ID_RE.match(rid):
            out = res_dir / f"{rid}.json"
            tmp = res_dir / f".{rid}.tmp"
            tmp.write_text(json.dumps({"id": rid, "ts": int(time.time()), **res}, ensure_ascii=False, indent=2))
            tmp.chmod(0o644)
            tmp.replace(out)
        print(f"petición {rid or '(nombre no válido)'}: {accion} -> {'ok' if res.get('ok') else res.get('error')}",
              flush=True)
    return 0


if __name__ == "__main__":
    modo = sys.argv[1] if len(sys.argv) > 1 else ""
    sys.exit(auto() if modo == "auto" else peticiones() if modo == "peticiones" else 2)
