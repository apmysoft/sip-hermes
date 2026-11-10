# Modelos de HALO: llama.cpp + llama-swap (sustituye a Ollama, 05-11-2026)

Es la misma forma de servir modelos que en Neo (`sip-config/llm-neo/`), con el mismo puerto y la misma
dirección que tenía Ollama: **`${HALO_TAILNET_IP}:11434`** (tailnet). Los consumidores no cambian:
- LiteLLM;
- los proveedores `custom:ollama` de Hermes, que usan `/v1`;
- las sondas TCP de WoL, `sip-halo-wake`, el resumen y el traspaso;
- las reglas de nftables;
- la ACL.

Los nombres de modelo de Ollama se conservan como ids o alias.

## Estructura en HALO

```
/var/lib/sip-llm/                  root:sip-llm 755
├── llama-b12110-vulkan/           llama.cpp b12110 (= v0.9.0), backend en uso
├── llama-b12110-rocm/             mismo build con ROCm (usa el ROCm 7.2.4 del sistema), alternativa
├── bin/llama-swap                 v270
├── models/                        GGUF (root:sip-llm 640, 750) + <fichero>.sha256ok
├── llama-swap.yaml                config (root:sip-llm 640)
├── cache/                         HOME y caché de shaders de Mesa (sip-llm)
└── staging/                       descargas en curso (se puede vaciar)
```

- **Servicio:** `llama-swap.service`.
  - Usuario `sip-llm` (nologin, grupos `render` y `video`).
  - `ProtectSystem=strict`, sin capacidades.
  - `Conflicts=ollama.service`.
  - Espera a que exista la IP de la tailnet, como `sip-whisper`.
- **Cada modelo** es un `llama-server` en `127.0.0.1:${PORT}` que llama-swap arranca bajo demanda y para tras 600 s sin uso (como el `keep_alive` de 10 min).

## Instalación (reproducible)

1. `sudo sh install-halo.sh <dir>`: usuario, directorios y binarios, con sha256 comprobado (tabla de abajo).
2. `sudo sh modelos.sh`:
   - copia los blobs de Ollama (su nombre es su sha256 y se verifica);
   - descarga de Hugging Face los dos modelos que Ollama guardaba en su formato propio;
   - es idempotente.
3. `sudo sh apply.sh`:
   - hace la copia previa;
   - para y deshabilita Ollama, sin borrar nada;
   - arranca llama-swap y verifica.

   Su vuelta atrás a Ollama ya no sirve: Ollama se desinstaló el 05-11 tras verificar el reinicio.
4. `sh verificar.sh` (sin root): servicio, 12 modelos y un turno real. Úsalo tras cada arranque.

| Componente | Versión | sha256 |
|---|---|---|
| llama.cpp Vulkan | `llama-b12110-bin-ubuntu-vulkan-x64.tar.gz` | `a5d741940956ec62e8783aee7e5a4c7c761af867d6f027c3277a51e1a3ac59b0` (digest de GitHub) |
| llama.cpp ROCm | `llama-b12110-bin-ubuntu-rocm-10.0-x64.tar.gz` | `664b5c218ec9a38d1e7b543bae7407dc62a4051ba09ddc51bd29f68ee77da674` (digest de GitHub) |
| llama-swap | `llama-swap_270_linux_amd64.tar.gz` | `b7f89c944e83e30c438846f8c513b9e64fb7bdcec1e3f47ed8be31a94d688a09` (checksums del release + digest) |

## Modelos

| Id (y alias) | Fichero | Notas |
|---|---|---|
| `qwen3.8:27b` (`qwen3.8:27b-64k`) | blob de Ollama + proyector de visión | 64K (96K probado y revertido el 06-11), MTP con 4 tokens de borrador, temp 0.6. Una sola instancia para los dos nombres |
| `qwen3.8-heretic:27b` (06-11) | `0bserverx/Qwen3.8-27B-Heretic-Abliterated-Uncensored-GGUF` `RVN-Q4_K_M-multilingual-mtp` (commit `ab8d7bd`, sha256 `8b207715…`) | **Redactor sin censura** de `automatizaciones-locales` (elección del usuario). Abliteración Heretic/ARA: KL 0,0085 respecto al original, 0-1 rechazos de 100. imatrix multilingüe, cabeza MTP oficial (n 3), solo texto, 32K. Apache 2.0 |
| `qwen3.6:27b` | blob de Ollama + proyector de visión | 64K, MTP con 3 |
| `qwen3-coder:30b` | blob de Ollama | 64K |
| `gpt-oss:20b` | `ggml-org/gpt-oss-20b-GGUF` MXFP4 | Ollama usaba su formato propio (`gptoss`), que llama.cpp no carga. Sin EAGLE3 (ver medidas) |
| `muse-glimmer:30b` (`hf.co/bartowski/…:Q4_K_M`) | blob de Ollama + proyector de visión | Con `--jinja` ya razona: en Ollama no podía, por su plantilla |
| `qwen3-vl:8b` | blob de Ollama + proyector de visión | 32K |
| `qwen3-vl:30b` | `Qwen/Qwen3-VL-30B-A3B-Instruct-GGUF` Q4_K_M + mmproj F16 | Ollama usaba su formato propio (`qwen3vlmoe`) |
| `bge-m3` (`bge-m3:latest`), `qwen3-embedding:0.6b` | blobs de Ollama | Embeddings **en CPU** (`--device none`); conviven con el modelo de GPU |

Hay **un modelo de GPU a la vez** (grupo `gpu`, como `OLLAMA_MAX_LOADED_MODELS=1`). Desde el 05-11 el grupo incluye también `whisper-gpu` y `comfyui_auto` (planificador de GPU: `sip-config/gpu-halo/`); no salen en `/v1/models`. La caché KV es q8_0
con flash attention, como en Ollama.

`eagle3-gpt-oss-20b-Q8_0.gguf` se descargó para la medida y se borró el 05-11.

## Medido (05-11-2026, RX 7900 XTX, `qwen3.8:27b` Q4_K_M)

| | ROCm | Vulkan (RADV) | Ollama 0.34 |
|---|---|---|---|
| Prompt de 512 / 16K | 1115 / 1032 t/s | 938 / 850 t/s | — |
| Generación sin MTP | 38 t/s | 41 t/s | — |
| **Generación con MTP (n=4)** | 61 t/s | **77 t/s** | 54–67 t/s |

- **Aceptación del borrador MTP:** 52–56 %, como en Ollama.
- **Carga:** unos 7 s desde la caché de disco; 14 s en el primer turno tras el cambio.
- **VRAM de `qwen3.8` con 64K:** 21,7 GB, de los que 1,2 GB son el proyector de visión y 1,3 GB el contexto MTP; sin ellos, 18,4. Ollama ocupaba 17,5 GB.
- **gpt-oss:20b:** 197 t/s sin borrador y 111 con EAGLE3 (acepta el 15 %), así que se usa sin borrador.
- **Elección: Vulkan.** En los turnos de Hermes con caché de prompt manda la generación, y Vulkan no depende del ROCm del sistema. ROCm gana unos 3 s en un primer prompt de 16K.

## Verificado (05-11)

- **Cada modelo:**
  - la herramienta se llama bien;
  - el razonamiento sale separado;
  - el *streaming* usa el resultado de la herramienta.
- **Visión** (`qwen3-vl:8b`, `qwen3-vl:30b` y `qwen3.8`): extracción exacta de una factura sintética.
- **Embeddings:** funcionan en CPU sin tocar la VRAM.
- **Tras el cambio:**
  - Neo recibe `/v1/models` con código 200;
  - turnos de PERSONAL y CODING por su API correctos;
  - LiteLLM con `qwen3.8:27b` y `gpt-oss:20b` correcto;
  - 0 errores en los registros de Hermes;
  - `sip-model-eval` lee 12 modelos por `/v1/models`.

## Contexto de `qwen3.8` a 96K: probado y REVERTIDO (06-11)

**Decisión del usuario:** vuelve a 64K, porque 34 t/s con contexto largo no le compensa. Lo de abajo es la medida,
que queda como referencia.

Medido con un llama-server temporal, con los mismos parámetros que en producción (MTP, proyector de imágenes,
caché q8):

| Contexto | VRAM | Resultado |
|---|---|---|
| 96K (98304) | 22,8 GB al cargar; **23,6 GB de 25,8 con el contexto lleno** | ✅ |
| 128K | 24,2 GB solo al cargar | ❌ Sin margen con el escritorio de HALO |

- **Prompt sintético de 81.458 tokens con una aguja al principio:** la encuentra.
- **Velocidad con contexto largo:**
  - leerlo la primera vez cuesta 152 s (537 t/s, frente a 850 con 16K);
  - el turno siguiente, con la caché de prompt, lee lo nuevo en 0,6 s;
  - la generación baja a 34 t/s con 81K acumulados (~77 con contexto corto).
- **Hermes:** `context_length: 98304` en las configuraciones de PERSONAL (raíz, que no lo tenía; perfil
  `personal`; API) y de CODING (API y WebUI, bloque de LiteLLM). El bloque cuyo respaldo es `gpt-oss` (64K)
  sigue en 32768. Hermes compacta al 50 %, es decir, a unos 48K.
- **Verificado:** `verificar.sh` OK y turnos reales de PERSONAL y CODING (18-19 s). Copias en
  `/root/sip-agent-backups/2026-11-06/contexto-96k/` (HALO y Neo).

## Redactor sin censura: prueba del 06-11 (`probar-redactor.sh`, datos sintéticos)

- **Prosa en español natural**, a 66-74 t/s con MTP. Una crítica dura con tacos sale sin rechazo (el original
  la suavizaría o la rechazaría).
- **Fidelidad:** con «aspectos con los que NO está de acuerdo: ruidoso», el redactor invirtió la experiencia
  («lo que menos me convence es el ruido») en 3 de 3 intentos, y **el original también** (1 de 2). No es
  efecto de la abliteración, sino de cómo se pide. Con «el usuario DESMIENTE (otras opiniones lo dicen, pero
  en su experiencia es FALSO): que sea ruidoso», **3 de 3 correctos**. Es una regla para las plantillas de
  la aplicación.
- `qwen3.8` razona antes de responder. Con `max_tokens` bajo (700), a veces gasta todo pensando y devuelve
  texto vacío; hay que usar un margen amplio o desactivar el razonamiento en la petición.

## Diferencias con Ollama que hay que saber

- **API propia de Ollama:** `/api/tags`, `/api/show` y `/api/create` dan 404; `/api/version` responde.
  - Hermes usaba `/api/show` para detectar el contexto; ahora lo toma de `context_length` de su configuración, que ya existía.
  - `coding/set-executor.sh` y `hermes/personal-64k.sh` quedan obsoletos. Las variantes se definen ahora en `llama-swap.yaml`.
- **El contexto lo fija `-c` en la línea de cada modelo.** El `num_ctx` de una petición se ignora.
- **Estado:**
  - `curl http://${HALO_TAILNET_IP}:11434/running` (equivale a `ollama ps`);
  - `/unload` descarga todo;
  - `journalctl -u llama-swap`.
- **Ollama** está desinstalado desde el 05-11 (noche). Se quitaron el binario, `/usr/local/lib/ollama`, la unidad, el usuario y el grupo, y sus 109 GB de modelos (`/usr/share/ollama`); el disco liberó 114 GB. La copia de la unidad y la lista de modelos está en `/root/sip-agent-backups/2026-11-05/ollama-desinstalado/`.

## Reinicio verificado (05-11, 23:02)

llama-swap arrancó solo a los 13 s del kernel, escuchando solo en la IP de la tailnet. Sin unidades fallidas, 12 modelos y turno correcto (`verificar.sh`).
