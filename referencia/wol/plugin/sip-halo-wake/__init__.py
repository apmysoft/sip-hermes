"""Despierta HALO sin LLM: la skill halo-wake no sirve si el modelo que la invoca vive en HALO.

Corre en el proceso de Hermes, no en el terminal del agente, así que funciona también en
perfiles con backend ssh. Solo pide; el envío, la MAC y el tope de 5/h son del servicio del host.
"""
import fcntl
import json
import logging
import os
import socket
import time
from pathlib import Path

logger = logging.getLogger(__name__)

PROBE_HOST = os.environ.get("SIP_HALO_PROBE_HOST", "${HALO_TAILNET_IP}")
PROBE_PORT = int(os.environ.get("SIP_HALO_PROBE_PORT", "11434"))
WOL_ROOT = Path(os.environ.get("SIP_HALO_WOL_ROOT", "/workspace/_wol"))
WAIT_SECONDS = 210  # el servicio espera 180 s; margen para que lance la unidad
LOCK = "/tmp/sip-halo-wake.lock"


def halo_up():
    try:
        with socket.create_connection((PROBE_HOST, PROBE_PORT), timeout=2):
            return True
    except OSError:
        return False


def request_wake():
    rid = f"plugin-{int(time.time())}-{os.getpid()}"
    (WOL_ROOT / "requests" / f"{rid}.json").write_text("{}\n")
    result = WOL_ROOT / "results" / f"{rid}.json"
    deadline = time.time() + WAIT_SECONDS
    while time.time() < deadline:
        if result.exists():
            status = json.loads(result.read_text()).get("status", "desconocido")
            result.unlink(missing_ok=True)
            return status
        time.sleep(2)
    return "sin_respuesta"


def ensure_halo(model="", **kwargs):
    # Los modelos de HALO son etiquetas de Ollama (nombre:tag); los cloud de LiteLLM no llevan ':'.
    if ":" not in str(model or "") or halo_up():
        return None
    with open(LOCK, "w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)  # varias sesiones a la vez esperan un solo despertar
        if halo_up():
            return None
        status = request_wake()
    logger.warning("sip-halo-wake: HALO no respondía; WOL %s", status)
    if status in ("awake", "already_awake"):
        return None
    return {"context": f"[SIP] HALO no responde (WOL: {status}). Informa al usuario y no uses cloud para tareas personales."}


def register(ctx):
    ctx.register_hook("pre_llm_call", ensure_halo)
