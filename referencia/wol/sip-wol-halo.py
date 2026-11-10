#!/usr/bin/env python3
"""Emisor WOL de HALO a nivel host (v2.4 M.11). Lo dispara sip-wol-halo.path.

Único emisor de magic packets. El contenido de la petición se ignora: nada que
escriba Hermes puede cambiar la MAC, el destino ni el límite. Toda petición se
retira siempre de requests/, para no provocar unit-start-limit-hit en la .path.
"""
import fcntl
import json
import os
import re
import socket
import sys
import time
from pathlib import Path

MAC = "${HALO_MAC}"
BROADCAST = "${LAN_BROADCAST}"
MAX_PER_HOUR = 5  # tabla de parámetros de v2.4

ROOT = Path(os.environ.get("SIP_WOL_ROOT", "${DOCKER_DATA}/hermes/workspace/_wol"))
STATE = Path(os.environ.get("SIP_WOL_STATE", "/var/lib/sip-wol/sent.log"))
PROBE_HOST = os.environ.get("SIP_WOL_PROBE_HOST", "${HALO_TAILNET_IP}")
PROBE_PORT = int(os.environ.get("SIP_WOL_PROBE_PORT", "11434"))
WAIT_SECONDS = int(os.environ.get("SIP_WOL_WAIT", "180"))
OUTBOX = Path(os.environ.get("SIP_NOTIFY_OUTBOX", "/var/lib/sip-notify/outbox"))
# Modo ausencia (M.15, sip-ausencia): solo peticiones explícitas (skill halo-wake); las del plugin
# sip-halo-wake (prefijo plugin-, en cada turno) se contestan "ausencia" sin enviar nada.
AUSENCIA = Path(os.environ.get("SIP_AUSENCIA", "/var/lib/sip-ausencia/activa"))
ALERTS = {
    "timeout": "HALO no despierta: el WOL no ha funcionado en 3 min. Enciende el enchufe de HALO en la app Tapo.",
    "rate_limited": "HALO sigue sin responder y se alcanzó el tope de 5 WOL/hora. Revisa el enchufe de HALO en la app Tapo.",
}


def halo_up():
    try:
        with socket.create_connection((PROBE_HOST, PROBE_PORT), timeout=3):
            return True
    except OSError:
        return False


def recent_sends(now):
    if not STATE.exists():
        return []
    return [t for t in (float(x) for x in STATE.read_text().split()) if now - t < 3600]


def send_magic(now, sends):
    payload = b"\xff" * 6 + bytes.fromhex(MAC.replace(":", "")) * 16
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
        s.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        s.sendto(payload, (BROADCAST, 9))
    STATE.write_text("\n".join(str(t) for t in sends + [now]) + "\n")


def wake():
    """Devuelve el estado final; HALO despierto no gasta cupo ni envía nada."""
    if halo_up():
        return "already_awake"
    # 06-11: dos instancias comparten el registro (Hermes en _wol y sip-flujos): el cupo se cuenta bajo cerrojo.
    with open(STATE.with_suffix(".lock"), "a") as cerrojo:
        fcntl.flock(cerrojo, fcntl.LOCK_EX)
        now = time.time()
        sends = recent_sends(now)
        if len(sends) >= MAX_PER_HOUR:
            print(f"<4>ALERTA WOL: limite de {MAX_PER_HOUR}/h alcanzado; no se envia", flush=True)
            return "rate_limited"
        send_magic(now, sends)
    print(f"WOL enviado ({len(sends) + 1}/{MAX_PER_HOUR} en la ultima hora)", flush=True)
    deadline = time.time() + WAIT_SECONDS
    while time.time() < deadline:
        if halo_up():
            return "awake"
        time.sleep(3)
    return "timeout"


def alert(status):
    """Deja el aviso en la bandeja de sip-notify; un fallo aquí no debe bloquear los resultados."""
    if status not in ALERTS:
        return
    try:
        # Dentro de la bandeja (ReadWritePaths son montajes distintos: rename entre ellos da EXDEV);
        # sip-notify ignora los ficheros que empiezan por punto.
        tmp = OUTBOX / f".wol-{int(time.time())}.tmp"
        tmp.write_text(ALERTS[status] + "\n")
        tmp.replace(OUTBOX / f"wol-{int(time.time())}.txt")
    except OSError as exc:
        print(f"<3>No se pudo dejar el aviso: {exc}", flush=True)


def main():
    requests = [p for p in (ROOT / "requests").iterdir()]
    if not requests:
        return 0
    ausente = AUSENCIA.exists()
    pedidas = [p for p in requests if not (ausente and p.name.startswith("plugin-"))]
    status = wake() if pedidas else "ausencia"  # varias peticiones equivalen a un solo despertar
    print(f"{len(requests)} peticion(es), {len(requests) - len(pedidas)} rechazada(s) por ausencia: {status}",
          flush=True)
    alert(status)
    for p in requests:
        rid = re.sub(r"[^A-Za-z0-9_-]", "_", p.stem)[:64] or "peticion"
        out = ROOT / "results" / f"{rid}.json"
        tmp = out.with_suffix(".tmp")
        st = status if p in pedidas else "ausencia"
        tmp.write_text(json.dumps({"id": rid, "status": st, "at": int(time.time())}) + "\n")
        tmp.chmod(0o644)
        tmp.replace(out)
        p.unlink(missing_ok=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
