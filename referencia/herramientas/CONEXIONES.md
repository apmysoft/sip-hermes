# Herramientas instaladas y conexiones pendientes con Hermes (06-11-2026)

> Catálogo para el usuario, siempre al día: `CATALOGO.md` (skill `herramientas` de PERSONAL).

Es el estado de `PROPUESTA-HERRAMIENTAS.md` tras la noche del 06-11. **Casa** (Home Assistant, Uptime Kuma,
Netdata) queda fuera por decisión del usuario: la domótica la lleva Alexa por ahora.

## 1. Conectadas y verificadas de punta a punta

| Herramienta | Zona | Cómo |
|---|---|---|
| Whisper CPU + GPU | PERSONAL | `audio_transcribir` (GPU desde 1 MB, por el planificador; si falla, CPU) |
| Notas de voz | Telegram (todas) | `sip-gateway` → `sip-voz-bridge` → Whisper |
| **FLUX (imagen)** | PERSONAL | **`imagen_generar` (06-11)**: ComfyUI por `:11434/comfyui`. PNG en `/workspace/imagenes`, segundo plano y aviso si tarda; turno real de 190 s, imagen en 75 s |
| **Ampliar imagen (Real-ESRGAN)** | PERSONAL | **`imagen_ampliar` (07-11)**: ×2/×4 desde `/workspace` o `/para` a `/workspace/imagenes` |
| **Música (ACE-Step 1.5)** | PERSONAL | **`musica_generar` (07-11)**: 10–180 s, MP3 en `/workspace/audio` |
| yt-dlp | RESEARCH | `medios_descargar` → `00_entrada` |
| Apagado/estado de HALO | PERSONAL | skill `halo-energia` |

## 2. Instaladas y probadas, sin conectar todavía

**En HALO** (`/opt/sip-medios`, `. /opt/sip-medios/entorno`, `sip-config/medios/probar.sh`: 10/10 con datos
sintéticos, como usuario normal y **en CPU**):

| Herramienta | Para qué | Probado |
|---|---|---|
| DeepFilterNet (`deep-filter`) | Quitar ruido de grabaciones | ✅ |
| Demucs | Separar voz, música e instrumentos | ✅ (CPU; en GPU iría por el planificador) |
| ffmpeg `silenceremove` | Cortar silencios (auto-editor descartado: fallo SIGSEGV como usuario) | ✅ |
| PySceneDetect | Escenas de un vídeo | ✅ |
| rembg + BiRefNet | Quitar fondos | ✅ |
| Kokoro | Voz natural en español (`ef_dora`) | ✅ |
| Docling | PDF, DOCX y otros → Markdown con tablas | ✅ (11 s/página en CPU) |
| OCRmyPDF + Tesseract (spa, eng) | Texto en PDF escaneados | ✅ |
| Subtítulos (Whisper SRT + ffmpeg) | `.srt` e incrustados | ✅ |
| ExifTool | Metadatos de fotos y vídeos | ✅ |
| Pandoc, Typst, Graphviz, Marp, Mermaid | Documentos, PDF, presentaciones, diagramas | ✅ |

**En ComfyUI** (por el planificador, nodos de serie, sin nodos de terceros):

| Modelo | Para qué | Probado |
|---|---|---|
| SDXL + ControlNet Union ProMax | Control fino (pose, bordes, profundidad) | SDXL ✅ (48 s con ampliación); ControlNet descargado |
| Real-ESRGAN ×4 | Ampliar y restaurar fotos | ✅ (768 → 3072 px) |
| Quitar fondo (`RemoveBackground`, nativo) | En GPU, alternativa a rembg | Nodo presente |
| Qwen-Image-Edit 2511 | Editar con instrucciones | Descargado; probablemente le pase lo mismo que a Qwen-Image (RAM, decisión 3) |
| LTX-Video 2B 0.9.8 (fp8) + T5 | Vídeo corto | Descargado, nodos presentes |
| Wan 2.2 TI2V 5B | Vídeo desde texto o imagen | Descargado (05-11) |
| ACE-Step 1.5 turbo | Música | Descargado, nodos presentes |

**En Neo:** **SearXNG** (`sip-searxng`, red `research`, 10.20.0.20, sin puertos). Búsqueda real verificada
desde dentro (43 resultados: Brave, DuckDuckGo, Google).

## 3. Conexiones a implementar

### 3.1 `sip-medios` ✅ (implantado el 06-11)

**Hecho y verificado:**
- `sip-config/medios/sip-medios-api.py`, `sip-medios.service` y `apply-api.sh`: 13/13 pruebas por llama-swap, y el modelo de texto sigue cargado al lado;
- plugin `sip-medios` (`medios_procesar`, toolset `procesar`);
- `sip-documentos` 1.1, que pasa por OCR los PDF escaneados (solo el tramo pedido);
- turno real de PERSONAL: factura escaneada sintética leída con OCR, importe correcto en 22 s.

El diseño original:

PERSONAL ya llega a `${HALO_TAILNET_IP}:11434`. llama-swap puede hacer de puerta para servicios HTTP con
`/upstream/<nombre>/`, como ya hace con Whisper-GPU y ComfyUI. Así:

- **`sip-medios`**: servidor HTTP pequeño en HALO.
  - Usuario propio, solo `127.0.0.1`, entrada y salida por multipart, tamaño y tiempo limitados.
  - **Operaciones fijas:** `ruido`, `separar`, `silencios`, `escenas`, `fondo`, `voz`, `docling`, `ocr`,
    `subtitulos`, `pandoc`, `typst`, `diagrama`. Nada de comandos libres.
  - Registrado en llama-swap como modelo `medios`, en un grupo **de CPU** (`swap: false`,
    `exclusive: false`): no echa al modelo de texto.
- **Plugin `sip-medios`** en PERSONAL, con herramientas de alto nivel:
  - `audio_limpiar` (ruido, silencios, separar voz);
  - `video_subtitular`;
  - `video_escenas`;
  - `imagen_quitar_fondo`;
  - `documento_convertir` (Markdown → PDF, DOCX o presentación, con Typst, Pandoc o Marp);
  - `diagrama`;
  - `voz_generar` (Kokoro, a fichero).
  - Mismo patrón de segundo plano y aviso que `audio_transcribir`.
- **Mejora de `documentos_leer`** (`sip-documentos`): si un PDF no tiene texto, pasarlo por `ocr` o
  `docling`. Hoy dice «no hay OCR». Los documentos van de Neo a HALO dentro de casa, como ya hacen los textos
  que lee el modelo.
- **Esfuerzo:** un bloque. **Sin firewall nuevo.** Hay que tener en cuenta que, igual que ComfyUI,
  `sip-medios` quedaría al alcance de todo lo que llega a `:11434` (zonas y ACL).

### 3.2 Más flujos de imagen, vídeo y música en `sip-imagen`

**09-11:** además `imagen_editar` (Qwen-Image-Edit) y `video_generar` (LTX) ✅. **07-11 ✅ (parcial):** `imagen_ampliar` y `musica_generar` desplegados en `sip-imagen` 1.1, con turno real. El
planificador de GPU ya no corta a ComfyUI (nodo propio `sip-config/comfyui/custom_nodes/sip_espera.py`). Quedan vídeo,
control y editar.

Mismo plugin, flujos fijos (el agente no manda flujos arbitrarios):
- `imagen_ampliar` (Real-ESRGAN);
- `imagen_quitar_fondo` (nativo);
- `imagen_control` (SDXL + ControlNet);
- `video_generar` (LTX o Wan);
- `musica_generar` (ACE-Step);
- `imagen_editar` (Qwen-Image-Edit, tras la decisión de memoria).

Hace falta subir la imagen de entrada a ComfyUI (`/upload/image`) desde `/workspace` o `/para` (solo
lectura). **Esfuerzo:** un bloque, sobre todo de pruebas de calidad y de tiempos.

### 3.3 Entregar ficheros por Telegram (decisión de arquitectura) — **NO (decisión del usuario, 09-11)**

Hoy el gateway solo envía texto (**ADR «Zonas»: gateway sin montajes de datos**, salvo los buzones `/voz` y
`/avisos`). Para recibir en el móvil la imagen, el audio con voz natural o el PDF generado, haría falta un
buzón de salida de formato fijo:
- PERSONAL deja `{id, tipo, ruta}`;
- el gateway envía solo ficheros de `/workspace/imagenes|audio|documentos`, con tamaño y tipo limitados.

Cambia el ADR, así que **lo decides tú**. Mientras tanto, los ficheros se ven en la WebUI o en el
`/workspace` por SMB.

### 3.4 SearXNG → RESEARCH ✅ (aplicado el 06-11)

Aplicado con el visto bueno del usuario, más el toolset `search` (solo `web_search`). Verificado:
- el `web_search` de Hermes devuelve resultados de SearXNG;
- el resto de la red privada sigue cerrado (timeouts y `sip-drop-research` +6);
- 0 errores.

El modelo de RESEARCH sigue prefiriendo su navegador en las pruebas: elige él. Lo que se aplicó:

`sip-config/research/searxng/apply-conexion.sh`:
- **una excepción en nftables**: red `research` → `10.20.0.20:8080`, nada más; ya pasa `nft -c`;
- `web.search_backend: searxng` y `SEARXNG_URL` en RESEARCH;
- comprueba que el resto de la red privada sigue cerrado.

### 3.5 Paperless y biblioteca

Plan aparte: `PLAN-PAPERLESS.md` (decisiones del usuario).

### 3.6 Voz de salida

Kokoro (natural) y Piper (rápido) están instalados. Para que Hermes «hable» por Telegram hace falta 3.3.

## 4. No instaladas, y por qué

| Herramienta | Motivo |
|---|---|
| ~~Índice de texto completo, garantías~~ (✅ 09-11); semántica + reranker, vencimientos, descripción de imágenes nocturna | Leen todo PARA: **decisión tuya pendiente** (el índice de libros en HALO, idea del usuario 09-11) (preparados el 05-11; el clasificador de permisos ya frenó el despliegue una vez). Paperless resolvería parte de esto para los papeles |
| WhisperX / pyannote (quién habla) | Los modelos de pyannote piden aceptar condiciones en Hugging Face con tu cuenta |
| Chatterbox / F5-TTS (clonar voces) | Clonar voces exige el consentimiento de la persona; Kokoro ya da voz natural. Si lo quieres, se instala |
| Stable Audio Open | Modelo con acceso restringido en Hugging Face (tu cuenta). ACE-Step cubre la música |
| crawl4ai / Firecrawl local | Hermes no soporta crawl4ai. Firecrawl autoalojado son 5 contenedores; RESEARCH ya lee páginas con su navegador |
| changedetection.io | Necesita decidir exposición y canal de avisos (bot propio o `sip-notify`) y qué vigilar |
| NLLB / MADLAD | El modelo de 27B traduce bien; no compensa otro modelo |
| Apache Tika | Docling cubre los formatos de oficina; Tika viene con Paperless si se adopta |
| auto-editor | Fallo (SIGSEGV como usuario normal, 2 veces, regla 10). Lo sustituye `ffmpeg silenceremove` |
| ~~Qwen-Image~~ | ✅ 09-11: en `imagen_generar` con `con_texto` (ComfyUI a 24 GB, `--cache-none`). Qwen-Image-Edit en `imagen_editar` (✅ 09-11) |
| Conversión a formatos duraderos (PDF/A, FLAC) | Depende de qué hacer con `04_archivo` y Paperless |
| Casa (Home Assistant, Uptime Kuma, Netdata) | Excluido por el usuario |

## 5. v2.4: lo que queda

- ~~**Respaldo de PERSONAL con el modelo pequeño de Neo (v2.4: «Tiny en Neo; jamás cloud»)**~~ ✅ 06-11:
  implantado y verificado con un turno real (`sip-config/tiny-personal/README.md`). El «parado por la regla 10»
  era un choque de puerto con JDownloader (5800), no la variante de 32K.
- **Cola de tareas pesadas y lotes valle:** cubierto en parte. Las tareas largas (transcripción, imagen) ya
  van en segundo plano con aviso. Falta una cola para «HALO apagado y no urgente», que hoy no hace falta: el
  WOL despierta HALO a demanda.
- **Lo que depende del calendario:** Kimi (18-11), semana de observación de la Fase 9 y comprobar el
  apagado automático (esta noche).
