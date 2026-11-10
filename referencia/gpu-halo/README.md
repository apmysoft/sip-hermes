# Planificador de GPU de HALO (05-11-2026)

La RX 7900 XTX (24 GB) la comparten tres servidores que no caben juntos:

| Servidor | VRAM | Uso |
|---|---|---|
| Modelo de texto (`qwen3.8` y el resto de llama-swap) | hasta 21,7 GB | PERSONAL, CODING, LiteLLM |
| Whisper en GPU (`whisper-gpu`) | ~1,6 GB | Audios largos de `audio_transcribir` |
| ComfyUI (`comfyui_auto`) | según el flujo (FLUX ~17 GB) | Imágenes (aún sin uso por Hermes) |

**El planificador es llama-swap**, sin programa propio. Los tres son miembros de su grupo `gpu`
(`swap: true`): solo uno a la vez. Antes de cambiar, llama-swap espera a que termine la petición en curso.
La siguiente petición de texto vuelve a cargar el modelo (unos 7-25 s). `/running` dice qué ocupa la GPU.

- **No ejecuta ComfyUI ni Whisper él.** Arranca y para sus unidades de systemd (`sip-gpu-unidad`, que se
  queda en primer plano mientras la unidad vive). Cada servicio conserva su usuario (`sip-comfy`,
  `sip-whisper`), su tope de RAM y su hardening.
- **Permiso:** regla de polkit `50-sip-llm-gpu.rules`. `sip-llm` puede hacer solo `start`/`stop` de
  `sip-comfyui.service` y `sip-whisper-gpu.service`. Aprobado por el usuario el 05-11 (regla 3).
- **Sin huérfanos:** el drop-in `50-sip-gpu.conf` de `llama-swap.service` para las dos unidades si
  llama-swap se para o se reinicia.
- **Ninguna de las dos unidades tiene arranque propio** (no `enable`). El Whisper de CPU (`sip-whisper`,
  `:8178`) sigue siempre activo para las notas de voz: no echa al modelo de la GPU.

## Acceso

| Qué | Dirección | Quién |
|---|---|---|
| Whisper en GPU | `http://${HALO_TAILNET_IP}:11434/upstream/whisper-gpu/inference` (mismo formulario que `:8178/inference`) | `sip-transcribir` ≥ 1.2, desde 1 MB de audio; si falla, el de CPU |
| ComfyUI | `http://${HALO_TAILNET_IP}:11434/comfyui/` (API y UI) | Cualquiera que llegue a `:11434` por la ACL y nftables |

**Exposición nueva:** ComfyUI escuchaba solo en `127.0.0.1`. Ahora se llega a él a través de llama-swap,
con el mismo alcance que los modelos de texto (`:11434`, sin clave, como Ollama). ComfyUI sin nodos
extra no ejecuta código arbitrario. Solo escribe en `/opt/sip-comfyui` (`ReadWritePaths`).

## Ficheros

| Fichero | Destino |
|---|---|
| `50-sip-llm-gpu.rules` | `/etc/polkit-1/rules.d/` (root 644) |
| `sip-gpu-unidad` | `/usr/local/lib/sip-gpu/` (root 755) |
| `sip-whisper-gpu.service` | `/etc/systemd/system/` |
| `llama-swap-gpu.conf` | `/etc/systemd/system/llama-swap.service.d/50-sip-gpu.conf` |
| `../llm-halo/llama-swap.yaml` | modelos `whisper-gpu` y `comfyui_auto` en el grupo `gpu` |
| `../comfyui/sip-comfyui.service` | solo comentarios: lo gestiona llama-swap |
| `../whisper/install-gpu.sh` | compila `whisper-server-vulkan` (v1.9.5, mismo commit que el de CPU) |

Instalación: `sudo sh ../whisper/install-gpu.sh` y luego `sudo sh apply.sh <audio.wav sintético>`. Copia
previa y `rollback.sh` en `/root/sip-agent-backups/<fecha>/gpu-halo/`. `sudo sh verificar.sh <audio.wav>`
repite la verificación.

## Medido y verificado (05-11)

- **Whisper large-v3-turbo, audio sintético de 3:55:** CPU 58 s (4× tiempo real), GPU Vulkan **3,3 s (70×)**.
  Un audio de una hora: ~1 min en GPU frente a ~15 en CPU.
- **`verificar.sh`:**
  1. 12 modelos en `/v1/models`.
  2. Polkit, desde un proceso de `sip-llm` sin sesión (como llama-swap): niega `start sip-whisper`,
     `restart sip-comfyui`, `stop sip-whisper` y `start ssh`, y permite `start`/`stop` de
     `sip-whisper-gpu`. El intermediario rechaza otras unidades.
  3. Secuencia texto → audio (5 s con el cambio) → texto (9 s) → imagen FLUX (89 s con el arranque) →
     texto (25 s). En cada paso `/running` muestra solo uno y al final no queda ningún servidor de GPU
     activo.
- **Reinicio de llama-swap con `whisper-gpu` cargado:** la unidad queda parada.
- **`sip-transcribir` 1.2 en Neo:**
  - prueba directa en `hermes-personal-api`: GPU en 3 s;
  - turno real de PERSONAL por `sip-gateway`: el agente usó la herramienta, GPU en 4 s, turno de 51 s;
  - vuelta a CPU con la GPU inaccesible y fichero pequeño por CPU, probados en local.

## Incidencia de la prueba (05-11)

La primera prueba de polkit se lanzó con `runuser` desde la sesión gráfica del usuario. Polkit trató
el proceso como parte de esa sesión y pidió autorización en el escritorio. El registro muestra que se
concedió tres veces como `usuario`, así que llegó a parar llama-swap. Se restauró al momento. La prueba
correcta usa `systemd-run --uid=sip-llm`: un proceso sin sesión, como el servicio real. La regla no
cambió.

## Pendiente

- Hermes no usa ComfyUI todavía (herramienta de imagen: siguiente bloque de `herramientas/`).
- Qwen-Image sigue limitado por el `MemoryMax=20G` de ComfyUI (decisión pendiente del usuario).
- El apagado de HALO por inactividad usará `/running` y el estado de estas unidades.
