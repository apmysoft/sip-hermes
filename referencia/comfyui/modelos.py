"""Descarga los modelos de ComfyUI (05-11) con sha256 verificado contra la API de Hugging Face.

Solo .safetensors (los .pth/.ckpt son pickle: pueden ejecutar código al cargarse). Reanuda descargas
cortadas (.part). Uso (como sip-comfy, en HALO): python3 modelos.py /opt/sip-comfyui/ComfyUI/models
"""
import hashlib
import json
import os
import sys
import urllib.request

MODELOS = [  # (repo, ruta en el repo, subcarpeta de models/)
    ("Comfy-Org/flux1-schnell", "flux1-schnell-fp8.safetensors", "checkpoints"),
    ("Comfy-Org/Qwen-Image_ComfyUI", "split_files/diffusion_models/qwen_image_2512_fp8_e4m3fn.safetensors", "diffusion_models"),
    ("Comfy-Org/Qwen-Image_ComfyUI", "split_files/text_encoders/qwen_2.5_vl_7b_fp8_scaled.safetensors", "text_encoders"),
    ("Comfy-Org/Qwen-Image_ComfyUI", "split_files/vae/qwen_image_vae.safetensors", "vae"),
    ("Comfy-Org/Qwen-Image-Edit_ComfyUI", "split_files/diffusion_models/qwen_image_edit_2511_fp8mixed.safetensors", "diffusion_models"),
    ("Comfy-Org/Wan_2.2_ComfyUI_Repackaged", "split_files/diffusion_models/wan2.2_ti2v_5B_fp16.safetensors", "diffusion_models"),
    ("Comfy-Org/Wan_2.2_ComfyUI_Repackaged", "split_files/text_encoders/umt5_xxl_fp8_e4m3fn_scaled.safetensors", "text_encoders"),
    ("Comfy-Org/Wan_2.2_ComfyUI_Repackaged", "split_files/vae/wan2.2_vae.safetensors", "vae"),
    ("Comfy-Org/Real-ESRGAN_repackaged", "RealESRGAN_x4plus.safetensors", "upscale_models"),
    # 06-11: SDXL + ControlNet (control fino), vídeo LTX y música ACE-Step (soportados por ComfyUI sin nodos extra)
    ("stabilityai/stable-diffusion-xl-base-1.0", "sd_xl_base_1.0.safetensors", "checkpoints"),
    ("xinsir/controlnet-union-sdxl-1.0", "diffusion_pytorch_model_promax.safetensors", "controlnet"),
    ("Lightricks/LTX-Video", "ltxv-2b-0.9.8-distilled-fp8.safetensors", "checkpoints"),
    ("comfyanonymous/flux_text_encoders", "t5xxl_fp8_e4m3fn_scaled.safetensors", "text_encoders"),
    ("Comfy-Org/ACE-Step-1.5", "checkpoints/ace_step_1.5_turbo_aio.safetensors", "checkpoints"),
]
UA = {"User-Agent": "sip-comfyui-modelos/1.0"}


def metadatos(repo):
    url = f"https://huggingface.co/api/models/{repo}/tree/main?recursive=true"
    with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=60) as r:
        return {f["path"]: f for f in json.load(r) if f.get("type") == "file"}


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for b in iter(lambda: f.read(1 << 24), b""):
            h.update(b)
    return h.hexdigest()


def bajar(repo, ruta, destino, esperado, tam):
    part = destino + ".part"
    ya = os.path.getsize(part) if os.path.exists(part) else 0
    if ya < tam:
        req = urllib.request.Request(f"https://huggingface.co/{repo}/resolve/main/{ruta}",
                                     headers={**UA, "Range": f"bytes={ya}-"})
        with urllib.request.urlopen(req, timeout=120) as r, open(part, "ab") as f:
            if ya and r.status != 206:
                f.truncate(0)
            while True:
                b = r.read(1 << 22)
                if not b:
                    break
                f.write(b)
    real = sha256(part)
    if real != esperado:
        os.remove(part)
        raise SystemExit(f"sha256 distinto en {ruta}: {real} != {esperado} (borrado el .part)")
    os.replace(part, destino)


def main(base):
    cache = {}
    for repo, ruta, sub in MODELOS:
        meta = cache.setdefault(repo, metadatos(repo)).get(ruta)
        if not meta or not ruta.endswith(".safetensors"):
            raise SystemExit(f"no encontrado o no safetensors: {repo}/{ruta}")
        esperado, tam = meta["lfs"]["oid"], meta["size"]
        d = os.path.join(base, sub)
        os.makedirs(d, exist_ok=True)
        destino = os.path.join(d, os.path.basename(ruta))
        if os.path.exists(destino) and os.path.getsize(destino) == tam:
            print(f"ya está  {sub}/{os.path.basename(ruta)}", flush=True)
            continue
        print(f"bajando  {sub}/{os.path.basename(ruta)} ({tam / 1e9:.1f} GB)", flush=True)
        bajar(repo, ruta, destino, esperado, tam)
        print(f"OK sha256 {esperado[:12]}  {sub}/{os.path.basename(ruta)}", flush=True)
    print("TODOS LOS MODELOS OK", flush=True)


if __name__ == "__main__":
    main(sys.argv[1])
