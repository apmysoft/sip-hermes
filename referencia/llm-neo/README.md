# Tiny GPU en Neo — llama.cpp + llama-swap (Fase 4 SIP)

Runtime LLM local en Neo para la clasificación de entrada (Gestor de Entrada) y,
en el futuro, para el coordinador de Hermes (Fase 5). Decisión registrada en
99-NOTAS (27-10): llama.cpp directo en lugar de Ollama. HALO también, desde el 05-11 (`sip-config/llm-halo/`).

## Layout en Neo

```
/var/lib/sip-llm/
├── llama-b11935/        # binarios llama.cpp (build nocturno b11935, v0.7.0-dev, commit 7ecb57f7a)
├── cudart/              # CUDA 12.8 runtime empaquetado (libcudart/libcublas/libcublasLt) — sin toolkit en el sistema
├── bin/llama-swap       # llama-swap v267
├── models/              # GGUF (root:sip-llm 0640)
├── llama-swap.yaml      # config (root:sip-llm 0640)
└── staging/             # artefactos descargados (se puede purgar)
```

- Servicio systemd: `llama-swap.service` (unit versionada en este directorio),
  usuario `sip-llm` (nologin), `ProtectSystem=strict`, escucha **solo
  `127.0.0.1:11434`**. API OpenAI-compatible (`/v1/chat/completions`, `/v1/models`).
- El modelo carga bajo demanda y descarga tras `ttl` (600 s) sin peticiones.

## Pins (verificados 27/28-10-2026)

| Componente | Versión | sha256 | Verificación |
|---|---|---|---|
| llama.cpp binarios | b11935 (`llama-b11935-bin-ubuntu-cuda-12.8-x64.tar.gz`) | `1a6ab634838ba2c6a7f887fc08af54d976818974b1959a2dd739d05223f21f3e` | registro propio (upstream no publica checksums) |
| CUDA runtime | b11935 (`cudart-…-cuda-12.8-x64.tar.gz`) | `e18b679b203ee3065a2a6c249e1381c010f1722b3d059f3a288c8fba06546122` | registro propio |
| llama-swap | v267 | `5e57a83418554ed4c4be1247819c0dd2ba7deb2c44f334fb5da3afec51b2d41c` | checksums oficiales del release ✅ |
| Modelo | Qwen3-4B-Instruct-2507 Q4_K_M (`unsloth/Qwen3-4B-Instruct-2507-GGUF`) | `3605803b982cb64aead44f6c1b2ae36e3acdb41d8e46c8a94c6533bc4c67e597` | API de Hugging Face (lfs sha256) ✅ |

Driver Neo: 580.178.04 (GTX 1070 8 GiB, Pascal compute 6.1). vLLM descartado: Pascal
fuera de soporte. Sin CUDA toolkit instalado: los binarios usan `LD_LIBRARY_PATH`
hacia `/var/lib/sip-llm/cudart` (definido en `llama-swap.yaml`).

## Uso

```bash
# smoke
curl -s http://127.0.0.1:11434/v1/models
# chat
curl -s http://127.0.0.1:11434/v1/chat/completions -H 'Content-Type: application/json' \
  -d '{"model":"qwen3-4b-instruct","messages":[{"role":"user","content":"hola"}],"max_tokens":50}'
# estado GPU
nvidia-smi --query-gpu=memory.used,utilization.gpu --format=csv
# logs
journalctl -u llama-swap.service -f
curl -s http://127.0.0.1:11434/logs        # últimos 10 KB
```

Salida JSON estructurada: `response_format: {"type":"json_schema", …}` (verificada;
es lo que usa el Gestor de Entrada, con abstención forzable por esquema).

## Medido (27/28-10-2026)

- Carga inicial del modelo: ~25-30 s (en frío). Descarga automática tras 600 s idle.
- Idle: ~47-49 tok/s decode, 3,9 GiB VRAM (quedan ~4 GiB para Jellyfin/Immich).
- **S.2 (triple contención), 04-11-2026 ✅** con `s2-triple-contencion.sh`. Carga sintética, sin tocar
  las bibliotecas:
  - NVENC con el ffmpeg de Jellyfin sobre `testsrc2` 1080p, sin `-re`: 10,5x, más o menos 10 flujos en
    tiempo real.
  - Inferencias CLIP + caras de Immich sobre imágenes de ruido: 742 en 120 s, en GPU (968 MiB).
  - El tiny con la petición del gestor (JSON por schema, `max_tokens` 300).

  | Medida | Solo el tiny | Triple contención |
  |---|---|---|
  | tok/s | 43,0 | 34,9 (−19 %) |
  | Segundos por propuesta | 3,0 | 4,0 |
  | JSON válido | 4/4 | 4/4 |

  VRAM: pico de 5,1 GiB de 8 (con el escritorio de Neo). **Decisión: se queda el 4B.** Un 7B Q4
  (~5,5 GiB con contexto) dejaría la VRAM al límite en el peor caso, y el 4B acierta el 89 % de los
  nombres en los lotes reales (99-NOTAS, 04-11).

## Rollback

```bash
sudo systemctl disable --now llama-swap.service
sudo rm /etc/systemd/system/llama-swap.service && sudo systemctl daemon-reload
sudo userdel sip-llm            # opcional; conservar no estorba
sudo rm -rf /var/lib/sip-llm    # conservar staging/ nada más
```

No toca nada del sistema salvo la unit, el usuario y `/var/lib/sip-llm`.
Copia previa/estado: `/root/sip-agent-backups/2026-10-27/fase4/PRE-CHANGE.txt`
(no existía ningún runtime LLM previo en Neo).
