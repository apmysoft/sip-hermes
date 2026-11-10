"""Prueba de ComfyUI (05-11): una imagen con FLUX.1-schnell fp8 por la API local (127.0.0.1:8188).

Uso (en HALO, con sip-comfyui en marcha): python3 probar-imagen.py "prompt" [semilla] [flux|qwen]
Con el planificador de GPU (05-11): SIP_COMFY_API=http://${HALO_TAILNET_IP}:11434/comfyui (llama-swap arranca
ComfyUI y descarga el modelo de texto; el POST espera a que esté listo).
qwen = Qwen-Image 2512 fp8 (texto legible dentro de la imagen), 20 pasos.
Imprime el tiempo y el fichero generado (en /opt/sip-comfyui/ComfyUI/output/).
"""
import json
import sys
import time
import urllib.request
import uuid

import os
API = os.environ.get("SIP_COMFY_API", "http://127.0.0.1:8188")
prompt = sys.argv[1] if len(sys.argv) > 1 else "a red fox reading a book in a cozy library, warm light, photo"
semilla = int(sys.argv[2]) if len(sys.argv) > 2 else 42
modelo = sys.argv[3] if len(sys.argv) > 3 else "flux"
flujo = {
    "1": {"class_type": "CheckpointLoaderSimple", "inputs": {"ckpt_name": "flux1-schnell-fp8.safetensors"}},
    "2": {"class_type": "CLIPTextEncode", "inputs": {"text": prompt, "clip": ["1", 1]}},
    "3": {"class_type": "CLIPTextEncode", "inputs": {"text": "", "clip": ["1", 1]}},
    "4": {"class_type": "EmptySD3LatentImage", "inputs": {"width": 1024, "height": 1024, "batch_size": 1}},
    "5": {"class_type": "KSampler", "inputs": {"model": ["1", 0], "positive": ["2", 0], "negative": ["3", 0],
          "latent_image": ["4", 0], "seed": semilla, "steps": 4, "cfg": 1.0, "sampler_name": "euler",
          "scheduler": "simple", "denoise": 1.0}},
    "6": {"class_type": "VAEDecode", "inputs": {"samples": ["5", 0], "vae": ["1", 2]}},
    "7": {"class_type": "SaveImage", "inputs": {"images": ["6", 0], "filename_prefix": "sip-prueba"}},
}
if modelo == "qwen":
    flujo = {
        "1": {"class_type": "UNETLoader", "inputs": {"unet_name": "qwen_image_2512_fp8_e4m3fn.safetensors", "weight_dtype": "default"}},
        "2": {"class_type": "CLIPLoader", "inputs": {"clip_name": "qwen_2.5_vl_7b_fp8_scaled.safetensors", "type": "qwen_image"}},
        "3": {"class_type": "VAELoader", "inputs": {"vae_name": "qwen_image_vae.safetensors"}},
        "4": {"class_type": "ModelSamplingAuraFlow", "inputs": {"model": ["1", 0], "shift": 3.1}},
        "5": {"class_type": "CLIPTextEncode", "inputs": {"text": prompt, "clip": ["2", 0]}},
        "6": {"class_type": "CLIPTextEncode", "inputs": {"text": "", "clip": ["2", 0]}},
        "7": {"class_type": "EmptySD3LatentImage", "inputs": {"width": 1328, "height": 1328, "batch_size": 1}},
        "8": {"class_type": "KSampler", "inputs": {"model": ["4", 0], "positive": ["5", 0], "negative": ["6", 0],
              "latent_image": ["7", 0], "seed": semilla, "steps": 20, "cfg": 2.5, "sampler_name": "euler",
              "scheduler": "simple", "denoise": 1.0}},
        "9": {"class_type": "VAEDecode", "inputs": {"samples": ["8", 0], "vae": ["3", 0]}},
        "10": {"class_type": "SaveImage", "inputs": {"images": ["9", 0], "filename_prefix": "sip-prueba-qwen"}},
    }
cid = uuid.uuid4().hex
t0 = time.time()
req = urllib.request.Request(API + "/prompt", json.dumps({"prompt": flujo, "client_id": cid}).encode(),
                             {"Content-Type": "application/json"})
pid = json.load(urllib.request.urlopen(req, timeout=300))["prompt_id"]  # incluye el arranque de ComfyUI
while True:
    h = json.load(urllib.request.urlopen(f"{API}/history/{pid}", timeout=30))
    if pid in h:
        st = h[pid].get("status", {})
        if st.get("status_str") == "error":
            print("ERROR", json.dumps(st)[:800])
            sys.exit(1)
        imgs = [i["filename"] for o in h[pid]["outputs"].values() for i in o.get("images", [])]
        print(f"OK {time.time() - t0:.1f}s ->", imgs)
        break
    if time.time() - t0 > 900:
        print("TIMEOUT")
        sys.exit(1)
    time.sleep(1)
