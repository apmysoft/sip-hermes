"""Imagen y música para PERSONAL: ComfyUI en HALO, por el planificador de GPU. Todo queda en casa.

v1.0 (06-11): imagen_generar (FLUX.1-schnell, 4 pasos).
v1.1 (07-11): imagen_ampliar (Real-ESRGAN ×4, o ×2 reescalando) y musica_generar (ACE-Step 1.5 turbo).
v1.2 (09-11): imagen_generar con con_texto=true usa Qwen-Image (texto legible en la imagen; ComfyUI a 24 GB).
v1.3 (09-11): imagen_editar (Qwen-Image-Edit 2511): edita una imagen con una instrucción.
v1.4 (09-11): video_generar (LTX-Video 2B destilado): clips de 2 a 8 s en WebM.
v1.5 (09-11): imagen_editar a 40 pasos y cfg 4 (valores de referencia de 2511; con 20/2,5 el texto salía mal),
decisión del usuario: más tiempo a cambio de calidad (~5,5 min).

Los flujos son fijos: el agente solo elige parámetros acotados; no puede mandar flujos arbitrarios a ComfyUI.
imagen_ampliar solo lee de /workspace o /para (rutas resueltas, sin escapar por enlaces) y sube la imagen a la
carpeta input de ComfyUI en HALO, que se vacía a los 2 días (/etc/tmpfiles.d/sip-comfyui.conf).
Requiere el nodo propio sip_espera.py en ComfyUI (sip-config/comfyui/custom_nodes/): reserva abierta antes de
/prompt y fichero en la misma petición, para que llama-swap no pare ComfyUI a mitad de un trabajo.

Segundo plano: como sip-transcribir (v1.1). Espera hasta ESPERA s; si no ha terminado (p. ej. HALO despertando o
la GPU ocupada), devuelve el id de la tarea en /workspace/tareas y, en la API de PERSONAL, deja un aviso de formato
fijo para sip-gateway al acabar. El resultado se recoge con tarea_resultado (de sip-transcribir).
"""
import json
import os
import re
import secrets
import struct
import threading
import time
import urllib.parse
import urllib.request
import uuid

API = os.environ.get("SIP_COMFY_API", "http://${HALO_TAILNET_IP}:11434/comfyui")
WS = os.environ.get("SIP_WORKSPACE", "/workspace")
SALIDA = os.path.join(WS, "imagenes")
SALIDA_AUDIO = os.path.join(WS, "audio")
SALIDA_VIDEO = os.path.join(WS, "video")
FORMATOS_VIDEO = {"horizontal": (768, 512), "vertical": (512, 768), "cuadrado": (640, 640)}
TAREAS = os.path.join(WS, "tareas")
AVISOS = os.environ.get("SIP_AVISOS_DIR")
ESPERA = int(os.environ.get("SIP_TAREA_ESPERA", "300"))
LIMITE_S = 1800
FORMATOS = {"cuadrado": (1024, 1024), "horizontal": (1344, 768), "vertical": (768, 1344)}
FORMATOS_QWEN = {"cuadrado": (1328, 1328), "horizontal": (1664, 928), "vertical": (928, 1664)}  # nativos de Qwen-Image
RAICES = ("/workspace", "/para")
TIPOS_IMAGEN = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".webp": "image/webp"}
MAX_BYTES = 25 << 20
MAX_SALIDA = 8192        # lado máximo del resultado: ×4 hasta 2048 px de entrada, ×2 hasta 4096
_cerrojo = threading.Lock()

SCHEMA = {
    "name": "imagen_generar",
    "description": (
        "Genera una imagen a partir de una descripción con FLUX en la GPU de HALO (local; nada sale de casa). "
        "Tarda de 15 s a 2 min (más si HALO está despertando). Escribe la descripción EN INGLÉS, detallada "
        "(sujeto, estilo, luz, encuadre). Si la imagen debe llevar TEXTO LEGIBLE (cartel, portada, etiqueta, rótulo), "
        "pon con_texto=true y escribe el texto exacto entre comillas: usa Qwen-Image (unos 80 s; FLUX no sabe escribir). "
        "Guarda un PNG en /workspace/imagenes/ y devuelve la ruta. Si tarda más de 5 minutos sigue en segundo plano: "
        "dale al usuario el id y recógelo luego con tarea_resultado."),
    "parameters": {
        "type": "object",
        "properties": {
            "descripcion": {"type": "string", "description": "Descripción de la imagen, en inglés."},
            "formato": {"type": "string", "enum": sorted(FORMATOS), "description": "Por defecto cuadrado."},
            "semilla": {"type": "integer", "description": "Para repetir una imagen; por defecto aleatoria."},
            "con_texto": {"type": "boolean", "description": "true si la imagen debe contener texto legible (Qwen-Image)."},
        },
        "required": ["descripcion"],
    },
}

SCHEMA_AMPLIAR = {
    "name": "imagen_ampliar",
    "description": (
        "Amplía y mejora una foto o imagen con Real-ESRGAN en la GPU de HALO (local). Útil para fotos pequeñas, "
        "antiguas o con poca resolución. Lee un PNG, JPG o WebP de /workspace o /para (hasta 25 MB; ×4 hasta 2048 "
        "px de lado y ×2 hasta 4096) y guarda un PNG en /workspace/imagenes/. Tarda segundos (más si HALO está despertando)."),
    "parameters": {
        "type": "object",
        "properties": {
            "ruta": {"type": "string", "description": "Ruta de la imagen, bajo /workspace o /para."},
            "factor": {"type": "integer", "enum": [2, 4], "description": "Por defecto 2."},
        },
        "required": ["ruta"],
    },
}

SCHEMA_EDITAR = {
    "name": "imagen_editar",
    "description": (
        "Edita una imagen o foto siguiendo una instrucción, con Qwen-Image-Edit en la GPU de HALO (local): cambiar un "
        "texto o un cartel, quitar o añadir un objeto, cambiar la luz, el fondo o el estilo, restaurar. Lee un PNG, JPG o "
        "WebP de /workspace o /para (hasta 25 MB; se trabaja a ~1 megapíxel) y guarda un PNG en /workspace/imagenes/. "
        "Escribe la instrucción en inglés, concreta, y añade «keep everything else the same» si debe cambiar solo eso. "
        "Tarda unos 6 minutos: sigue en segundo plano; dale al usuario el id y recógelo con tarea_resultado."),
    "parameters": {
        "type": "object",
        "properties": {
            "ruta": {"type": "string", "description": "Imagen a editar, bajo /workspace o /para."},
            "instruccion": {"type": "string", "description": "Qué cambiar, en inglés."},
            "semilla": {"type": "integer", "description": "Para repetir un resultado; por defecto aleatoria."},
        },
        "required": ["ruta", "instruccion"],
    },
}

SCHEMA_VIDEO = {
    "name": "video_generar",
    "description": (
        "Genera un clip de vídeo corto a partir de una descripción, con LTX-Video en la GPU de HALO (local). Escribe la "
        "descripción EN INGLÉS: sujeto, acción, entorno, luz y movimiento de cámara. De 2 a 8 segundos a 24 fps, sin "
        "sonido. Tarda menos de un minuto (más si HALO está despertando). Guarda un WebM en /workspace/video/."),
    "parameters": {
        "type": "object",
        "properties": {
            "descripcion": {"type": "string", "description": "Descripción del vídeo, en inglés."},
            "segundos": {"type": "integer", "description": "Duración, de 2 a 8. Por defecto 4."},
            "formato": {"type": "string", "enum": sorted(FORMATOS_VIDEO), "description": "Por defecto horizontal."},
            "semilla": {"type": "integer", "description": "Para repetir un vídeo; por defecto aleatoria."},
        },
        "required": ["descripcion"],
    },
}

SCHEMA_MUSICA = {
    "name": "musica_generar",
    "description": (
        "Compone una pieza musical con ACE-Step en la GPU de HALO (local). Indica estilo, instrumentos y ánimo "
        "EN INGLÉS como etiquetas separadas por comas; letra opcional (si no hay, es instrumental). Guarda un MP3 "
        "en /workspace/audio/. Tarda aproximadamente lo mismo que dura la pieza; si pasa de 5 minutos sigue en "
        "segundo plano: dale al usuario el id y recógelo luego con tarea_resultado."),
    "parameters": {
        "type": "object",
        "properties": {
            "estilo": {"type": "string", "description": "Etiquetas en inglés: género, instrumentos, ánimo, voz."},
            "letra": {"type": "string", "description": "Letra con secciones como [verse] y [chorus]. Vacía = instrumental."},
            "segundos": {"type": "integer", "description": "Duración, de 10 a 180. Por defecto 60."},
            "idioma": {"type": "string", "enum": ["es", "en"], "description": "Idioma de la letra. Por defecto es."},
            "bpm": {"type": "integer", "description": "Tempo, de 60 a 180. Por defecto 100."},
            "semilla": {"type": "integer", "description": "Para repetir una pieza; por defecto aleatoria."},
        },
        "required": ["estilo"],
    },
}


# --- flujos fijos ----------------------------------------------------------------------------------------------
def _flujo(texto, ancho, alto, semilla, prefijo):
    return {
        "1": {"class_type": "CheckpointLoaderSimple", "inputs": {"ckpt_name": "flux1-schnell-fp8.safetensors"}},
        "2": {"class_type": "CLIPTextEncode", "inputs": {"text": texto, "clip": ["1", 1]}},
        "3": {"class_type": "CLIPTextEncode", "inputs": {"text": "", "clip": ["1", 1]}},
        "4": {"class_type": "EmptySD3LatentImage", "inputs": {"width": ancho, "height": alto, "batch_size": 1}},
        "5": {"class_type": "KSampler", "inputs": {"model": ["1", 0], "positive": ["2", 0], "negative": ["3", 0],
              "latent_image": ["4", 0], "seed": semilla, "steps": 4, "cfg": 1.0, "sampler_name": "euler",
              "scheduler": "simple", "denoise": 1.0}},
        "6": {"class_type": "VAEDecode", "inputs": {"samples": ["5", 0], "vae": ["1", 2]}},
        "7": {"class_type": "SaveImage", "inputs": {"images": ["6", 0], "filename_prefix": prefijo}},
    }


def _flujo_qwen(texto, ancho, alto, semilla, prefijo):
    return {
        "1": {"class_type": "UNETLoader", "inputs": {"unet_name": "qwen_image_2512_fp8_e4m3fn.safetensors",
                                                     "weight_dtype": "default"}},
        "2": {"class_type": "CLIPLoader", "inputs": {"clip_name": "qwen_2.5_vl_7b_fp8_scaled.safetensors",
                                                     "type": "qwen_image", "device": "default"}},
        "3": {"class_type": "VAELoader", "inputs": {"vae_name": "qwen_image_vae.safetensors"}},
        "4": {"class_type": "ModelSamplingAuraFlow", "inputs": {"model": ["1", 0], "shift": 3.1}},
        "5": {"class_type": "CLIPTextEncode", "inputs": {"clip": ["2", 0], "text": texto}},
        "6": {"class_type": "CLIPTextEncode", "inputs": {"clip": ["2", 0], "text": ""}},
        "7": {"class_type": "EmptySD3LatentImage", "inputs": {"width": ancho, "height": alto, "batch_size": 1}},
        "8": {"class_type": "KSampler", "inputs": {"model": ["4", 0], "positive": ["5", 0], "negative": ["6", 0],
              "latent_image": ["7", 0], "seed": semilla, "steps": 20, "cfg": 2.5, "sampler_name": "euler",
              "scheduler": "simple", "denoise": 1.0}},
        "9": {"class_type": "VAEDecode", "inputs": {"samples": ["8", 0], "vae": ["3", 0]}},
        "10": {"class_type": "SaveImage", "inputs": {"images": ["9", 0], "filename_prefix": prefijo}},
    }


def _flujo_editar(entrada, instruccion, semilla, prefijo):
    f = {
        "1": {"class_type": "UNETLoader", "inputs": {"unet_name": "qwen_image_edit_2511_fp8mixed.safetensors",
                                                     "weight_dtype": "default"}},
        "2": {"class_type": "CLIPLoader", "inputs": {"clip_name": "qwen_2.5_vl_7b_fp8_scaled.safetensors",
                                                     "type": "qwen_image", "device": "default"}},
        "3": {"class_type": "VAELoader", "inputs": {"vae_name": "qwen_image_vae.safetensors"}},
        "4": {"class_type": "ModelSamplingAuraFlow", "inputs": {"model": ["1", 0], "shift": 3.1}},
        "5": {"class_type": "CFGNorm", "inputs": {"model": ["4", 0], "strength": 1.0}},
        "6": {"class_type": "LoadImage", "inputs": {"image": entrada}},
        "7": {"class_type": "ImageScaleToTotalPixels", "inputs": {"image": ["6", 0], "upscale_method": "lanczos",
                                                                  "megapixels": 1.0, "resolution_steps": 8}},
        "8": {"class_type": "TextEncodeQwenImageEditPlus", "inputs": {"clip": ["2", 0], "prompt": instruccion,
                                                                      "vae": ["3", 0], "image1": ["7", 0]}},
        "9": {"class_type": "TextEncodeQwenImageEditPlus", "inputs": {"clip": ["2", 0], "prompt": "",
                                                                      "vae": ["3", 0], "image1": ["7", 0]}},
        "10": {"class_type": "FluxKontextMultiReferenceLatentMethod",
               "inputs": {"conditioning": ["8", 0], "reference_latents_method": "index_timestep_zero"}},
        "11": {"class_type": "FluxKontextMultiReferenceLatentMethod",
               "inputs": {"conditioning": ["9", 0], "reference_latents_method": "index_timestep_zero"}},
        "12": {"class_type": "VAEEncode", "inputs": {"pixels": ["7", 0], "vae": ["3", 0]}},
        "13": {"class_type": "KSampler", "inputs": {"model": ["5", 0], "positive": ["10", 0], "negative": ["11", 0],
               "latent_image": ["12", 0], "seed": semilla, "steps": 40, "cfg": 4.0, "sampler_name": "euler",
               "scheduler": "simple", "denoise": 1.0}},
        "14": {"class_type": "VAEDecode", "inputs": {"samples": ["13", 0], "vae": ["3", 0]}},
        "15": {"class_type": "SaveImage", "inputs": {"images": ["14", 0], "filename_prefix": prefijo}},
    }
    return f


def _flujo_video(texto, ancho, alto, fotogramas, semilla, prefijo):
    negativo = ("low quality, worst quality, deformed, distorted, disfigured, motion smear, motion artifacts, "
                "fused fingers, bad anatomy, weird hand, ugly")
    return {
        "1": {"class_type": "CheckpointLoaderSimple", "inputs": {"ckpt_name": "ltxv-2b-0.9.8-distilled-fp8.safetensors"}},
        "2": {"class_type": "CLIPLoader", "inputs": {"clip_name": "t5xxl_fp8_e4m3fn_scaled.safetensors", "type": "ltxv",
                                                     "device": "default"}},
        "3": {"class_type": "CLIPTextEncode", "inputs": {"clip": ["2", 0], "text": texto}},
        "4": {"class_type": "CLIPTextEncode", "inputs": {"clip": ["2", 0], "text": negativo}},
        "5": {"class_type": "LTXVConditioning", "inputs": {"positive": ["3", 0], "negative": ["4", 0], "frame_rate": 24.0}},
        "6": {"class_type": "EmptyLTXVLatentVideo", "inputs": {"width": ancho, "height": alto, "length": fotogramas,
                                                              "batch_size": 1}},
        "7": {"class_type": "KSamplerSelect", "inputs": {"sampler_name": "euler"}},
        "8": {"class_type": "LTXVScheduler", "inputs": {"steps": 8, "max_shift": 2.05, "base_shift": 0.95,
                                                        "stretch": True, "terminal": 0.1, "latent": ["6", 0]}},
        "9": {"class_type": "SamplerCustom", "inputs": {"model": ["1", 0], "add_noise": True, "noise_seed": semilla,
              "cfg": 1.0, "positive": ["5", 0], "negative": ["5", 1], "sampler": ["7", 0], "sigmas": ["8", 0],
              "latent_image": ["6", 0]}},
        "10": {"class_type": "VAEDecode", "inputs": {"samples": ["9", 0], "vae": ["1", 2]}},
        "11": {"class_type": "SaveWEBM", "inputs": {"images": ["10", 0], "filename_prefix": prefijo, "codec": "vp9",
                                                    "fps": 24.0, "crf": 32.0}},
    }


def _flujo_ampliar(entrada, factor, prefijo):
    f = {
        "1": {"class_type": "LoadImage", "inputs": {"image": entrada}},
        "2": {"class_type": "UpscaleModelLoader", "inputs": {"model_name": "RealESRGAN_x4plus.safetensors"}},
        "3": {"class_type": "ImageUpscaleWithModel", "inputs": {"upscale_model": ["2", 0], "image": ["1", 0]}},
    }
    ultimo = ["3", 0]
    if factor == 2:
        f["4"] = {"class_type": "ImageScaleBy", "inputs": {"image": ["3", 0], "upscale_method": "lanczos",
                                                           "scale_by": 0.5}}
        ultimo = ["4", 0]
    f["9"] = {"class_type": "SaveImage", "inputs": {"images": ultimo, "filename_prefix": prefijo}}
    return f


def _flujo_musica(estilo, letra, segundos, idioma, bpm, semilla, prefijo):
    return {
        "1": {"class_type": "CheckpointLoaderSimple", "inputs": {"ckpt_name": "ace_step_1.5_turbo_aio.safetensors"}},
        "2": {"class_type": "ModelSamplingAuraFlow", "inputs": {"model": ["1", 0], "shift": 3.0}},
        "3": {"class_type": "TextEncodeAceStepAudio1.5", "inputs": {
            "clip": ["1", 1], "tags": estilo, "lyrics": letra, "seed": semilla, "bpm": bpm,
            "duration": float(segundos), "timesignature": "4", "language": idioma, "keyscale": "C major",
            "generate_audio_codes": True, "cfg_scale": 2.0, "temperature": 0.85, "top_p": 0.9, "top_k": 0,
            "min_p": 0.0}},
        "4": {"class_type": "ConditioningZeroOut", "inputs": {"conditioning": ["3", 0]}},
        "5": {"class_type": "EmptyAceStep1.5LatentAudio", "inputs": {"seconds": float(segundos), "batch_size": 1}},
        "6": {"class_type": "KSampler", "inputs": {"model": ["2", 0], "positive": ["3", 0], "negative": ["4", 0],
              "latent_image": ["5", 0], "seed": semilla, "steps": 8, "cfg": 1.0, "sampler_name": "euler",
              "scheduler": "simple", "denoise": 1.0}},
        "7": {"class_type": "VAEDecodeAudio", "inputs": {"samples": ["6", 0], "vae": ["1", 2]}},
        "8": {"class_type": "SaveAudioMP3", "inputs": {"audio": ["7", 0], "filename_prefix": prefijo,
                                                       "quality": "V0"}},
    }


# --- ComfyUI ---------------------------------------------------------------------------------------------------
def _pedir(ruta, datos=None, timeout=60):
    req = urllib.request.Request(API + ruta, json.dumps(datos).encode() if datos is not None else None,
                                 {"Content-Type": "application/json"} if datos is not None else {})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def _subir(datos, nombre, tipo):
    limite = uuid.uuid4().hex
    cuerpo = (f"--{limite}\r\nContent-Disposition: form-data; name=\"image\"; filename=\"{nombre}\"\r\n"
              f"Content-Type: {tipo}\r\n\r\n").encode() + datos + (
              f"\r\n--{limite}\r\nContent-Disposition: form-data; name=\"overwrite\"\r\n\r\ntrue\r\n"
              f"--{limite}--\r\n").encode()
    req = urllib.request.Request(API + "/upload/image", cuerpo,
                                 {"Content-Type": f"multipart/form-data; boundary={limite}"})
    with urllib.request.urlopen(req, timeout=600) as r:  # 600: HALO puede estar despertando
        return json.load(r)["name"]


def _ejecutar(flujo, tid, clave, carpeta, nombre, extra):
    """Lanza un flujo fijo y guarda su primera salida (`images` o `audio`) en `carpeta/nombre`.

    Primero abre la reserva (/sip/reservar, nodo propio sip_espera.py en HALO) y después envía /prompt con el mismo
    client_id: siempre hay una petición abierta y llama-swap no cede la GPU a un modelo de texto a mitad del
    trabajo (fallo del 07-11). El fichero llega por la propia reserva."""
    t0 = time.time()
    res = {}

    def reservar():
        try:
            req = urllib.request.Request(API + f"/sip/reservar/{tid}?" + urllib.parse.urlencode(
                {"salida": clave, "max": LIMITE_S}))
            with urllib.request.urlopen(req, timeout=LIMITE_S + 600) as r:  # +600: HALO puede estar despertando
                if r.headers.get("X-SIP-Estado") == "hecho":
                    res["datos"] = r.read()
                else:
                    res["estado"] = json.load(r).get("estado")
        except Exception as e:
            res["fallo"] = e

    hilo = threading.Thread(target=reservar, daemon=True)
    hilo.start()
    time.sleep(1)  # que la reserva llegue antes que /prompt
    _pedir("/prompt", {"prompt": flujo, "client_id": tid}, timeout=600)
    hilo.join(LIMITE_S + 660)
    if "fallo" in res:
        raise OSError(str(res["fallo"])) from res["fallo"]
    if "datos" not in res:
        estado = res.get("estado", "sin_respuesta")
        return {"error": {"tiempo": "el trabajo tardó demasiado",
                          "error": "ComfyUI no pudo completar el trabajo"}.get(
                              estado, f"ComfyUI no devolvió resultado ({estado})")}
    os.makedirs(carpeta, exist_ok=True)
    destino = os.path.join(carpeta, nombre)
    with open(destino, "wb") as f:
        f.write(res["datos"])
    return {"guardado": destino, "segundos": round(time.time() - t0), **extra}


def _sin_halo(e):
    return {"error": f"no se pudo hablar con ComfyUI en HALO ({type(e).__name__}); puede estar apagado o "
                     "despertando: reintenta en un minuto"}


def _slug(texto, defecto):
    return re.sub(r"[^a-z0-9]+", "-", texto.lower())[:40].strip("-") or defecto


def _generar(texto, formato, semilla, tid, con_texto=False):
    tabla, flujo, modelo = (FORMATOS_QWEN, _flujo_qwen, "Qwen-Image") if con_texto else (FORMATOS, _flujo, "FLUX")
    ancho, alto = tabla.get(formato, tabla["cuadrado"])
    try:
        return _ejecutar(flujo(texto, ancho, alto, semilla, f"sip-{tid}"), tid, "images", SALIDA,
                         f"{time.strftime('%Y%m%d-%H%M%S')}-{_slug(texto, 'imagen')}.png",
                         {"semilla": semilla, "formato": f"{ancho}x{alto}", "modelo": modelo})
    except OSError as e:
        return _sin_halo(e)


def _ampliar(ruta, datos, tipo, factor, tid):
    base = os.path.splitext(os.path.basename(ruta))[0]
    try:
        entrada = _subir(datos, f"sip-{tid}{os.path.splitext(ruta)[1].lower()}", tipo)
        return _ejecutar(_flujo_ampliar(entrada, factor, f"sip-{tid}"), tid, "images", SALIDA,
                         f"{time.strftime('%Y%m%d-%H%M%S')}-{_slug(base, 'imagen')}-x{factor}.png",
                         {"origen": ruta, "factor": factor})
    except OSError as e:
        return _sin_halo(e)


def _editar(ruta, datos, tipo, instruccion, semilla, tid):
    base = os.path.splitext(os.path.basename(ruta))[0]
    try:
        entrada = _subir(datos, f"sip-{tid}{os.path.splitext(ruta)[1].lower()}", tipo)
        return _ejecutar(_flujo_editar(entrada, instruccion, semilla, f"sip-{tid}"), tid, "images", SALIDA,
                         f"{time.strftime('%Y%m%d-%H%M%S')}-{_slug(base, 'imagen')}-editada.png",
                         {"origen": ruta, "semilla": semilla})
    except OSError as e:
        return _sin_halo(e)


def _video(texto, formato, segundos, semilla, tid):
    ancho, alto = FORMATOS_VIDEO.get(formato, FORMATOS_VIDEO["horizontal"])
    fotogramas = 24 * segundos // 8 * 8 + 1  # LTX pide 8n+1 fotogramas
    try:
        return _ejecutar(_flujo_video(texto, ancho, alto, fotogramas, semilla, f"sip-{tid}"), tid, "images",
                         SALIDA_VIDEO, f"{time.strftime('%Y%m%d-%H%M%S')}-{_slug(texto, 'video')}.webm",
                         {"segundos": round(fotogramas / 24, 1), "formato": f"{ancho}x{alto}", "semilla": semilla})
    except OSError as e:
        return _sin_halo(e)


def _musica(estilo, letra, segundos, idioma, bpm, semilla, tid):
    try:
        return _ejecutar(_flujo_musica(estilo, letra, segundos, idioma, bpm, semilla, f"sip-{tid}"), tid, "audio",
                         SALIDA_AUDIO, f"{time.strftime('%Y%m%d-%H%M%S')}-{_slug(estilo, 'musica')}.mp3",
                         {"duracion_s": segundos, "semilla": semilla, "instrumental": letra == "[Instrumental]"})
    except OSError as e:
        return _sin_halo(e)


# --- tareas en segundo plano -----------------------------------------------------------------------------------
def _escribir(ruta, datos, modo=0o600):
    tmp = ruta + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(datos, f, ensure_ascii=False)
    os.chmod(tmp, modo)
    os.replace(tmp, ruta)


def _leer(tid):
    try:
        with open(os.path.join(TAREAS, tid + ".json"), encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def _hilo(tid, herramienta, trabajo, hecho):
    def latido():
        while not hecho.wait(60):
            try:
                os.utime(os.path.join(TAREAS, tid + ".json"))
            except OSError:
                pass
    threading.Thread(target=latido, daemon=True).start()
    try:
        res = trabajo()
    except Exception as e:  # el hilo nunca muere sin dejar estado
        res = {"error": f"fallo interno ({type(e).__name__})"}
    with _cerrojo:
        tarea = _leer(tid) or {}
        tarea.update(estado="error" if "error" in res else "ok", fin=int(time.time()), resultado=res)
        try:
            _escribir(os.path.join(TAREAS, tid + ".json"), tarea)
        except OSError:
            pass
        hecho.set()
    if tarea.get("segundo_plano") and AVISOS and os.path.isdir(AVISOS):
        try:
            _escribir(os.path.join(AVISOS, f"{tid}.json"),
                      {"v": 1, "id": tid, "herramienta": herramienta, "estado": tarea["estado"]}, 0o644)
        except OSError:
            pass


def _lanzar(herramienta, fichero, trabajo, session_id, nota):
    tid = secrets.token_hex(6)
    with _cerrojo:
        os.makedirs(TAREAS, exist_ok=True)
        _escribir(os.path.join(TAREAS, tid + ".json"),
                  {"id": tid, "herramienta": herramienta, "fichero": fichero[:60], "estado": "en_curso",
                   "inicio": int(time.time()), "segundo_plano": False, "session_id": str(session_id or "")})
    hecho = threading.Event()
    threading.Thread(target=_hilo, args=(tid, herramienta, lambda: trabajo(tid), hecho), daemon=True,
                     name=f"sip-imagen-{tid}").start()
    if hecho.wait(ESPERA):
        return json.dumps((_leer(tid) or {}).get("resultado") or {"error": "resultado perdido"}, ensure_ascii=False)
    with _cerrojo:
        tarea = _leer(tid) or {}
        if tarea.get("estado") != "en_curso":
            return json.dumps(tarea.get("resultado") or {"error": "resultado perdido"}, ensure_ascii=False)
        tarea["segundo_plano"] = True
        _escribir(os.path.join(TAREAS, tid + ".json"), tarea)
    return json.dumps({"en_segundo_plano": True, "tarea": tid,
                       "nota": f"{nota} Dile al usuario que se le avisará al terminar (en la WebUI, que pregunte "
                               "luego). No repitas la llamada."}, ensure_ascii=False)


def _semilla(v):
    try:
        return int(v) % (2**32) if v is not None else secrets.randbelow(2**32)
    except (TypeError, ValueError):
        return secrets.randbelow(2**32)


def _entero(v, defecto, minimo, maximo):
    try:
        return max(minimo, min(maximo, int(v)))
    except (TypeError, ValueError):
        return defecto


# --- herramientas ----------------------------------------------------------------------------------------------
def imagen_generar(args, **kwargs):
    texto = " ".join(str(args.get("descripcion") or "").split())[:1500]
    if len(texto) < 3:
        return json.dumps({"error": "falta la descripción"})
    formato = args.get("formato") if args.get("formato") in FORMATOS else "cuadrado"
    semilla = _semilla(args.get("semilla"))
    con_texto = args.get("con_texto") in (True, "true", "si", "sí", 1)
    return _lanzar("imagen_generar", texto, lambda tid: _generar(texto, formato, semilla, tid, con_texto),
                   kwargs.get("session_id"), "La imagen sigue generándose en HALO.")


def _dimensiones(datos, ext):
    """Ancho y alto sin dependencias (PNG, JPEG, WebP). None si no se reconoce."""
    try:
        if ext == ".png" and datos[:8] == b"\x89PNG\r\n\x1a\n":
            return struct.unpack(">II", datos[16:24])
        if ext in (".jpg", ".jpeg") and datos[:2] == b"\xff\xd8":
            i = 2
            while i < len(datos) - 9:
                if datos[i] != 0xFF:
                    return None
                marca, largo = datos[i + 1], struct.unpack(">H", datos[i + 2:i + 4])[0]
                if marca in (0xC0, 0xC1, 0xC2):
                    alto, ancho = struct.unpack(">HH", datos[i + 5:i + 9])
                    return ancho, alto
                i += 2 + largo
        if ext == ".webp" and datos[:4] == b"RIFF" and datos[8:12] == b"WEBP":
            if datos[12:16] == b"VP8X":
                return (int.from_bytes(datos[24:27], "little") + 1, int.from_bytes(datos[27:30], "little") + 1)
            if datos[12:16] == b"VP8 ":
                return (struct.unpack("<H", datos[26:28])[0] & 0x3FFF, struct.unpack("<H", datos[28:30])[0] & 0x3FFF)
            if datos[12:16] == b"VP8L":
                b = int.from_bytes(datos[21:25], "little")
                return ((b & 0x3FFF) + 1, ((b >> 14) & 0x3FFF) + 1)
    except (struct.error, IndexError):
        return None
    return None


def _leer_imagen(args):
    """(ruta, datos, ext, (ancho, alto)) o un JSON de error."""
    ruta = os.path.realpath(str(args.get("ruta") or "").strip())
    if not any(ruta == r or ruta.startswith(r + "/") for r in RAICES):
        return json.dumps({"error": "la imagen debe estar en /workspace o /para"})
    ext = os.path.splitext(ruta)[1].lower()
    if ext not in TIPOS_IMAGEN:
        return json.dumps({"error": "formato no admitido; solo PNG, JPG o WebP"})
    try:
        if os.path.getsize(ruta) > MAX_BYTES:
            return json.dumps({"error": "la imagen pasa de 25 MB"})
        with open(ruta, "rb") as f:
            datos = f.read()
    except OSError:
        return json.dumps({"error": "no se puede leer la imagen"})
    dim = _dimensiones(datos, ext)
    if not dim:
        return json.dumps({"error": "el fichero no parece una imagen válida"})
    return ruta, datos, ext, dim


def imagen_editar(args, **kwargs):
    instruccion = " ".join(str(args.get("instruccion") or "").split())[:1500]
    if len(instruccion) < 3:
        return json.dumps({"error": "falta la instrucción"})
    leida = _leer_imagen(args)
    if isinstance(leida, str):
        return leida
    ruta, datos, ext, _ = leida
    semilla = _semilla(args.get("semilla"))
    return _lanzar("imagen_editar", os.path.basename(ruta),
                   lambda tid: _editar(ruta, datos, TIPOS_IMAGEN[ext], instruccion, semilla, tid),
                   kwargs.get("session_id"), "La imagen sigue editándose en HALO.")


def imagen_ampliar(args, **kwargs):
    ruta = os.path.realpath(str(args.get("ruta") or "").strip())
    if not any(ruta == r or ruta.startswith(r + "/") for r in RAICES):
        return json.dumps({"error": "la imagen debe estar en /workspace o /para"})
    ext = os.path.splitext(ruta)[1].lower()
    if ext not in TIPOS_IMAGEN:
        return json.dumps({"error": "formato no admitido; solo PNG, JPG o WebP"})
    try:
        if os.path.getsize(ruta) > MAX_BYTES:
            return json.dumps({"error": "la imagen pasa de 25 MB"})
        with open(ruta, "rb") as f:
            datos = f.read()
    except OSError:
        return json.dumps({"error": "no se puede leer la imagen"})
    dim = _dimensiones(datos, ext)
    if not dim:
        return json.dumps({"error": "el fichero no parece una imagen válida"})
    factor = 4 if args.get("factor") in (4, "4") else 2
    if max(dim) * factor > MAX_SALIDA:
        if max(dim) * 2 > MAX_SALIDA:
            return json.dumps({"error": f"la imagen ya es grande ({dim[0]}x{dim[1]}); el máximo es 4096 px de lado"})
        factor = 2  # ×4 pasaría de 8192 px: se baja a ×2
    return _lanzar("imagen_ampliar", os.path.basename(ruta),
                   lambda tid: {**_ampliar(ruta, datos, TIPOS_IMAGEN[ext], factor, tid),
                                "tamano": f"{dim[0] * factor}x{dim[1] * factor}"},
                   kwargs.get("session_id"), "La imagen sigue ampliándose en HALO.")


def video_generar(args, **kwargs):
    texto = " ".join(str(args.get("descripcion") or "").split())[:1500]
    if len(texto) < 3:
        return json.dumps({"error": "falta la descripción"})
    formato = args.get("formato") if args.get("formato") in FORMATOS_VIDEO else "horizontal"
    segundos = _entero(args.get("segundos"), 4, 2, 8)
    semilla = _semilla(args.get("semilla"))
    return _lanzar("video_generar", texto, lambda tid: _video(texto, formato, segundos, semilla, tid),
                   kwargs.get("session_id"), "El vídeo sigue generándose en HALO.")


def musica_generar(args, **kwargs):
    estilo = " ".join(str(args.get("estilo") or "").split())[:500]
    if len(estilo) < 3:
        return json.dumps({"error": "falta el estilo"})
    letra = str(args.get("letra") or "").strip()[:3000] or "[Instrumental]"
    segundos = _entero(args.get("segundos"), 60, 10, 180)
    idioma = args.get("idioma") if args.get("idioma") in ("es", "en") else "es"
    bpm = _entero(args.get("bpm"), 100, 60, 180)
    semilla = _semilla(args.get("semilla"))
    return _lanzar("musica_generar", estilo,
                   lambda tid: _musica(estilo, letra, segundos, idioma, bpm, semilla, tid),
                   kwargs.get("session_id"), "La música sigue componiéndose en HALO.")


def register(ctx):
    ctx.register_tool(name="imagen_generar", toolset="imagen", schema=SCHEMA, handler=imagen_generar)
    ctx.register_tool(name="imagen_ampliar", toolset="imagen", schema=SCHEMA_AMPLIAR, handler=imagen_ampliar)
    ctx.register_tool(name="musica_generar", toolset="imagen", schema=SCHEMA_MUSICA, handler=musica_generar)
    ctx.register_tool(name="imagen_editar", toolset="imagen", schema=SCHEMA_EDITAR, handler=imagen_editar)
    ctx.register_tool(name="video_generar", toolset="imagen", schema=SCHEMA_VIDEO, handler=video_generar)
