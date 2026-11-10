"""SIP (07-11): GET /sip/reservar/{client_id}?salida=images|audio[&max=s] retiene la GPU para un trabajo y devuelve
su fichero.

Motivo: llama-swap (planificador de GPU de HALO) solo espera a la petición HTTP en curso antes de cambiar de modelo.
POST /prompt vuelve enseguida, así que una petición de texto paraba ComfyUI a mitad del trabajo y el trabajo se
perdía. Uso: el cliente abre esta petición ANTES de enviar POST /prompt con el mismo client_id (así no queda ningún
hueco sin petición abierta, que es por donde se colaba el texto) y la mantiene hasta recibir el fichero. El fichero
viaja en la misma respuesta porque, al cerrarse, llama-swap puede ceder la GPU y el siguiente arranque de ComfyUI
ya no tiene el historial (vive en memoria).

Solo lee la cola, el historial y la carpeta de salida (rutas comprobadas); no ejecuta nada ni acepta flujos.
Respuestas: el fichero (cabecera X-SIP-Estado: hecho) o JSON {"estado": "error"|"sin_salida"|"sin_trabajo"|"tiempo"}.
Sin nodos: NODE_CLASS_MAPPINGS vacío.
"""
import asyncio
import os
import re
import time

import folder_paths
from aiohttp import web
from server import PromptServer

MAX_S = 1800
LLEGADA_S = 180          # lo que puede tardar en llegar el POST /prompt tras abrir la reserva
CLIENTE_RE = re.compile(r"^[A-Za-z0-9_-]{6,64}$")

NODE_CLASS_MAPPINGS = {}
NODE_DISPLAY_NAME_MAPPINGS = {}


def _cliente(item):
    try:
        return (item[3] or {}).get("client_id")
    except (IndexError, AttributeError, TypeError):
        return None


def _buscar(cola, cid):
    """("hecho", entrada_de_historial) | ("en_curso", None) | ("ninguno", None)."""
    for pid, entrada in list(cola.get_history().items())[-200:]:
        if _cliente(entrada.get("prompt") or ()) == cid:
            return "hecho", entrada
    corriendo, pendientes = cola.get_current_queue_volatile()
    if any(_cliente(x) == cid for x in list(corriendo) + list(pendientes)):
        return "en_curso", None
    return "ninguno", None


@PromptServer.instance.routes.get("/sip/reservar/{client_id}")
async def sip_reservar(request):
    cid = request.match_info["client_id"]
    salida = request.query.get("salida", "images")
    if not CLIENTE_RE.match(cid) or salida not in ("images", "audio"):
        return web.json_response({"estado": "error", "motivo": "parámetros no válidos"}, status=400)
    try:
        limite = min(MAX_S, max(1, int(request.query.get("max", MAX_S))))
    except ValueError:
        limite = MAX_S
    cola = PromptServer.instance.prompt_queue
    t0 = time.time()
    estado, entrada = _buscar(cola, cid)
    while estado == "ninguno" and time.time() - t0 < LLEGADA_S:
        await asyncio.sleep(0.5)
        estado, entrada = _buscar(cola, cid)
    if estado == "ninguno":
        return web.json_response({"estado": "sin_trabajo", "segundos": round(time.time() - t0)})
    while estado == "en_curso" and time.time() - t0 < limite:
        await asyncio.sleep(1)
        estado, entrada = _buscar(cola, cid)
    segundos = round(time.time() - t0)
    if estado != "hecho":
        return web.json_response({"estado": "tiempo", "segundos": segundos})
    if entrada.get("status", {}).get("status_str") == "error":
        return web.json_response({"estado": "error", "segundos": segundos})
    ficheros = [i for o in entrada.get("outputs", {}).values() for i in o.get(salida, [])]
    if not ficheros:
        return web.json_response({"estado": "sin_salida", "segundos": segundos})
    i = ficheros[0]
    base = os.path.realpath(folder_paths.get_output_directory())
    ruta = os.path.realpath(os.path.join(base, i.get("subfolder", ""), i["filename"]))
    if not ruta.startswith(base + os.sep) or not os.path.isfile(ruta):
        return web.json_response({"estado": "sin_salida", "segundos": segundos})
    return web.FileResponse(ruta, headers={"X-SIP-Estado": "hecho", "X-SIP-Segundos": str(segundos)})
