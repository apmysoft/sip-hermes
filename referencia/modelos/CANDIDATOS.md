# Modelos locales: análisis de encaje y plan para después de la implantación

Estado: **análisis (03-11-2026); ejecución aplazada** hasta terminar la implantación (decisión del usuario).
Autorizado por el usuario: borrar los modelos que sobren, descargar candidatos y afinar el servidor de
modelos de HALO. Ya hecho: `deepseek-r1:32b` borrado (no lo usaba ninguna config).

## Restricciones del sistema que mandan más que los benchmarks

1. **HALO tiene una sola GPU (RX 7900 XTX, gfx1100, 24 GB) y un modelo cargado a la vez.** Cambiar de
   modelo cuesta unos 30 s de carga. Un especialista por zona (PERSONAL, CODING, RESEARCH local) haría que
   cada cambio de zona pagase una carga. Conviene **un modelo principal de HALO para casi todo**, más uno
   pequeño y rápido de reserva. Los especialistas, solo para lotes nocturnos, donde la carga no se nota.
2. **HALO no está siempre encendido** (WoL). Lo inmediato en Neo, con el tiny; lo pesado, en lotes.
3. **Todo pasa por Hermes con herramientas.** Lo que más falla en local no es el razonamiento, sino la
   plantilla y el parser de llamadas a herramientas (Muse Glimmer en Ollama: sin `thinking` por la plantilla
   del GGUF de bartowski; error 400 en la Fase 5). El servidor de modelos importa tanto como el modelo.
4. **Contexto:** Qwen 3.6/3.8 y Muse usan atención híbrida, así que la caché es pequeña. Medido:
   `qwen3.8:27b` con 65.536 de contexto = 17,5 GB, todo en GPU, 67 t/s (con MTP); con 98.304, 17,7 GB; con
   131.072, 18,8 GB y 1,2 GB a CPU por la reserva `OLLAMA_GPU_OVERHEAD` (medido el 03-11). Ya no hace falta un modelo
   más pequeño para tener más contexto; el límite real es la calidad: los densos pierden pasados los 32-64K.
5. **Las afirmaciones del modelo no son evidencia** (pilotos 1 y 2). Cualquier candidato se evalúa con un
   verificador que el agente no pueda tocar.

## Por rol

| Rol | Hoy | Candidatos | Análisis |
| --- | --- | --- | --- |
| Principal de HALO (PERSONAL, CODING, reserva de RESEARCH) | `qwen3.8:27b` en PERSONAL; `qwen3-coder:30b` en CODING | `qwen3.8:27b`, `qwen3.6:27b` | Los dos densos de Qwen son los más usados con Hermes en local. Un solo modelo para todo evita cargas. Elegir uno con la batería propia; el otro sobra |
| Ejecutor de código (lotes nocturnos) | `qwen3.8:27b-64k` desde el 03-11 (antes `qwen3-coder:30b`) | El principal; Devstral Small 2 (24B denso, ~15 GB); Qwen3.6-35B-A3B (MoE, ~22 GB) | El coder (MoE con 3B activos) entiende la tarea, pero edita mal ficheros grandes. Devstral es el único hecho para agentes de código que deja sitio para contexto. El 35B-A3B es rápido, pero tiene los mismos 3B activos: probarlo, sin esperar mucho |
| Bucles con muchas herramientas (operaciones de PERSONAL/SYSTEM) | — | Muse Glimmer 30B | Meta lo sitúa por delante en uso de herramientas (MCP-Atlas 75,5 frente a 62,5), pero alucina mucho (AA-Omniscience 82 % frente a 49 % de Qwen): **nunca para RESEARCH sin verificar**. La versión que hay (bartowski Q4_K_M, 21,2 GB, sin razonamiento en Ollama) no es la buena: la oficial de Meta (`K-Quant-17GB`, 16,8 GB) con el drafter DFlash (1,6 GB) necesita llama.cpp |
| Reserva rápida | `gpt-oss:20b` | Se mantiene | 13,8 GB, rápido; ya hace de último fallback |
| Tiny de Neo (clasificador del gestor, titular, router) | `qwen3-4b-instruct` | Gemma 4 E4B (~5 GB a 4 bits) | Tokens nativos de llamada a funciones y formato más estable; un usuario arregló su router con este cambio (anécdota). Probar con los prompts reales del gestor (dataset S.3) antes de cambiar. Por debajo de ~4B, la fiabilidad con herramientas se hunde |
| RESEARCH | Cloud (Gemini, Kimi) | Ningún local como principal | La investigación factual necesita modelos con menos alucinación y navegador; el local solo como reserva |

## Servidor de modelos de HALO: Ollama → llama-swap (como Neo)

**Hecho el 05-11-2026** (decisión del usuario; adelantado): ver `sip-config/llm-halo/README.md`. Medido: Vulkan con MTP 77 t/s frente a 54-67 de Ollama (sí gana velocidad, al contrario de lo previsto abajo); Muse razona con `--jinja`; gpt-oss va mejor sin EAGLE3. Lo de abajo es el análisis previo.


- **A favor:** plantilla original del GGUF con `--jinja` (arregla Muse y evita fallos de parser de otros);
  DFlash/drafters por modelo; binarios fijos con sha256 y config por modelo (contexto, sampling) en un YAML
  versionado, igual que `sip-config/llm-neo/`. Una sola forma de servir modelos en SIP.
- **Lo que no gana:** velocidad. Ollama 0.34 ya usa llama.cpp por dentro con MTP (aceptación ~50-80 % con
  `qwen3.8`), y un usuario con la misma GPU midió Vulkan solo un 4 % más rápido que Ollama/ROCm.
- **Coste:** casi todo usa `/v1` (LiteLLM, proveedores `ollama` de Hermes) y el puerto 11434 (sondas de
  WoL, del plugin de despertar, del resumen matutino y de los firewalls de zona): basta con mantener el
  puerto. Solo `sip-model-eval.py` usa la API propia de Ollama (`/api/tags`) y habría que pasarlo a
  `/v1/models`. Los nombres de modelo (`qwen3.8:27b`…) deben conservarse como alias en llama-swap.
- **Encontrado de paso:** la unidad `ollama` de HALO tiene un `PATH` con el venv de `forocoches_scraper`
  (heredado de una sesión). No tiene efecto conocido; corregir en la migración.

## Plan (después de la Fase 10)

1. ~~Migrar HALO a llama-swap (backend Vulkan o ROCm, medido), con copia, rollback y `apply.sh`.~~ **Hecho 05-11** (Vulkan).
2. Batería propia de evaluación, por la noche: los dos pilotos más tareas reales, con un verificador fijo
   (`tsc`, build y tamaño, lint, pruebas y un diff que detecte pruebas tocadas) y tope de intentos.
3. Candidatos, en orden: `qwen3.8:27b`, `qwen3.6:27b`, Muse Glimmer oficial con DFlash, Devstral Small 2 y
   Qwen3.6-35B-A3B. Gemma 4 E4B, aparte, contra S.3 en Neo.
4. Quedarse con un principal, un ejecutor de código (si no es el mismo) y la reserva. Borrar el resto.

## Fuentes (03-11-2026)

- Tabla agéntica con contraste en SWE-bench real: <https://huggingface.co/datasets/witcheer/agentic-score-leaderboard>
- Hermes con modelos locales (testimonios): <https://bestllmfor.com/guides/hermes-agent-local-models/>
- Muse Glimmer, variantes oficiales y DFlash: <https://ai-on-mac.com/articles/meta-muse-glimmer-30b-mac-en/>,
  <https://wavect.io/blog/muse-glimmer-30b-local-agent-guide/>, <https://unsloth.ai/docs/models/muse-glimmer.md>
- Qwen3.6 27B frente a 35B-A3B: <https://specpicks.com/reviews/qwen-3-6-35b-a3b-vs-27b-dense-24gb-gpu-2026>
- Devstral Small 2: <https://huggingface.co/mistralai/Devstral-Small-2-24B-Instruct-2512>
- Laguna XS 2.1 (descartado por ahora: ~20 GB y parser con historial de fallos): <https://friendli.ai/models/Fdxyra/Laguna-XS-2.1>
- Router pequeño: <https://reddit.sentinel-team.org/posts/1smh0ny/snapshots/2026-04-17T23%3A20%3A42.645991Z>,
  <https://d-central.tech/local-llm-agent-capability/>
- Ollama frente a llama.cpp en 7900 XTX: <https://reddit.sentinel-team.org/posts/1w7fjow/snapshots/2026-09-04T21%3A20%3A12.3645Z>
- Agentes nocturnos que rebajan las pruebas: <https://dev.to/pat9000/a-verifier-loop-beats-a-faster-local-model-4aea>
