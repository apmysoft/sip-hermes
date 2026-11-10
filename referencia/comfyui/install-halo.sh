#!/bin/sh
# ComfyUI en HALO (05-11, ampliación pedida por el usuario; PROPUESTA-HERRAMIENTAS §2.2). Root, en HALO,
# desde este directorio. Solo localhost (127.0.0.1:8188) y SIN arranque automático: Ollama y ComfyUI no
# caben juntos en los 24 GB hasta que exista el planificador de GPU. Hermes no lo usa todavía.
# Versiones fijadas: ComfyUI por tag (commit registrado), PyTorch ROCm 7.2 por versión.
# Rollback: systemctl disable --now sip-comfyui; rm /etc/systemd/system/sip-comfyui.service;
#   rm -rf /opt/sip-comfyui; userdel sip-comfy.
set -eu
cd "$(dirname "$0")"
VER=v0.44.0
TORCH="torch==2.14.1+rocm7.2"
IDX=https://download.pytorch.org/whl/rocm7.2
O=/opt/sip-comfyui
id sip-comfy >/dev/null 2>&1 || useradd --system --home-dir "$O" --shell /usr/sbin/nologin \
  --groups render,video sip-comfy
install -d -m 755 -o sip-comfy -g sip-comfy "$O"
if [ ! -d "$O/ComfyUI/.git" ]; then
  sudo -u sip-comfy git clone -q --depth 1 --branch "$VER" https://github.com/comfyanonymous/ComfyUI "$O/ComfyUI"
fi
sudo -u sip-comfy git -C "$O/ComfyUI" rev-parse HEAD > "$O/COMMIT"
if [ ! -x "$O/venv/bin/python" ]; then
  sudo -u sip-comfy python3 -m venv "$O/venv"
fi
# PyTorch ROCm primero (si no, requirements.txt traería la variante CUDA)
sudo -u sip-comfy "$O/venv/bin/pip" install -q --no-cache-dir --index-url "$IDX" "$TORCH" torchvision torchaudio
sudo -u sip-comfy "$O/venv/bin/pip" install -q --no-cache-dir -r "$O/ComfyUI/requirements.txt"
sudo -u sip-comfy "$O/venv/bin/python" -c "import torch;print('torch',torch.__version__,'hip',torch.version.hip,'gpu',torch.cuda.is_available() and torch.cuda.get_device_name(0))"
install -m 644 sip-comfyui.service /etc/systemd/system/sip-comfyui.service
systemctl daemon-reload
echo "ComfyUI $VER commit $(cut -c1-12 "$O/COMMIT"); servicio instalado SIN habilitar (arrancar a mano: systemctl start sip-comfyui)"
