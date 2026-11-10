# Catálogo de herramientas SIP

Actualizado: 2026-11-09 (tarde). No hace falta nombrar la herramienta: basta con pedirlo con tus palabras.
Todo es local (HALO o Neo) salvo lo que se indica en RESEARCH.

## PERSONAL (WebUI y Telegram)

| Qué puedes pedir | Herramienta | Resultado |
|---|---|---|
| Buscar o leer tus documentos de PARA (los PDF escaneados se leen con OCR) | `documentos_buscar`, `documentos_leer` | Respuesta en el chat |
| Buscar **dentro** del contenido de tus documentos (frases, importes, nombres); los libros (PDF de más de 100 páginas) solo por título | `documentos_buscar_texto` | Fragmentos con la palabra resaltada; el índice se actualiza cada noche |
| Transcribir un audio o una nota de voz | `audio_transcribir` | Texto; si es largo, sigue en segundo plano y avisa |
| Recoger una tarea que seguía en segundo plano | `tarea_resultado` | El resultado pendiente |
| Crear una imagen a partir de una descripción (FLUX); si lleva **texto legible** (cartel, portada, rótulo), con Qwen-Image | `imagen_generar` | PNG en `/workspace/imagenes` (FLUX ~40 s; con texto ~2,5 min) |
| Editar una foto o imagen con una instrucción: cambiar un texto o un cartel, quitar o añadir algo, cambiar la luz o el fondo (Qwen-Image-Edit) | `imagen_editar` | PNG en `/workspace/imagenes` (~6 min) |
| Ampliar o mejorar una foto ×2 o ×4 (Real-ESRGAN) | `imagen_ampliar` | PNG en `/workspace/imagenes` |
| Componer música de 10 a 180 s, instrumental o con letra (ACE-Step) | `musica_generar` | MP3 en `/workspace/audio` |
| Generar un clip de vídeo de 2 a 8 s a partir de una descripción, sin sonido (LTX-Video) | `video_generar` | WebM en `/workspace/video` (<1 min) |
| Quitar el ruido de un audio | `medios_procesar` (ruido) | Fichero en `/workspace/medios` |
| Cortar los silencios largos de un audio | `medios_procesar` (silencios) | Ídem |
| Separar la voz o la música de una grabación | `medios_procesar` (separar) | Ídem |
| Subtítulos `.srt` de un audio o vídeo, o incrustados en el vídeo | `medios_procesar` (subtitulos) | Ídem |
| Listar los cambios de escena de un vídeo | `medios_procesar` (escenas) | CSV |
| Quitar el fondo de una imagen | `medios_procesar` (fondo) | PNG transparente |
| Leer un texto en voz alta en español (voces ef_dora, em_alex, em_santa) | `medios_procesar` (voz) | WAV |
| Añadir texto a un PDF escaneado, o sacar solo el texto | `medios_procesar` (ocr) | PDF o texto |
| Convertir PDF, DOCX, PPTX, XLSX o HTML a Markdown con tablas | `medios_procesar` (docling) | Markdown |
| Crear un documento desde Markdown: PDF, DOCX, ODT, HTML, PPTX o presentación | `medios_procesar` (documento) | Fichero |
| Dibujar un diagrama (Mermaid o Graphviz) | `medios_procesar` (diagrama) | SVG o PNG |
| Redactar una opinión de producto (flujo A) o un texto desde vídeos (flujo B) | delega en `redactor_resena` / `redactor_ctue` | Formulario y resultado de sip-flujos |

**Skills de PERSONAL** (en la WebUI también con `/nombre`):

| Skill | Para qué |
|---|---|
| `herramientas` | Este catálogo |
| `segundo-cerebro` | Responder con tus documentos de PARA |
| `gestor-entrada` | Revisar y confirmar los renombres de `00_entrada` (código por Telegram) |
| `halo-energia` | Ver qué hace HALO y apagarlo (código por Telegram) |
| `halo-wake` | Despertar HALO si no responde |
| `servicios-docker` | Consultar y mantener los servicios domésticos de Neo (código por Telegram) |
| `redactores` | Encargar textos a los redactores de sip-flujos |

## RESEARCH (Telegram `/r`)

| Qué puedes pedir | Herramienta | Resultado |
|---|---|---|
| Buscar en Internet (SearXNG local) | `web_search` | Resultados en el chat |
| Navegar, leer una web, pulsar, escribir, volver atrás | `navegador_abrir`, `navegador_leer`, `navegador_pulsar`, `navegador_escribir`, `navegador_atras`, `navegador_cerrar` | Contenido en el chat |
| Descargar un vídeo o audio (yt-dlp) | `medios_descargar` | Fichero en `00_entrada` |
| Guardar una nota o un resultado | `entrada_guardar` | Nota en `00_entrada` |

Desde el 10-11 usa el modelo local de HALO (qwen3.8) y Gemini solo si HALO no responde (cloud): aun así, no le pases datos personales.

## CODING (Telegram `/c`)

Herramientas de serie de Hermes: terminal y ficheros en el worker aislado de HALO. Skill `sip-lecciones-codigo`.

## Si no responde ningún modelo

Si HALO y el modelo pequeño de Neo están caídos a la vez, por Telegram tu mensaje a PERSONAL queda **en cola**: te
contesta cuando vuelvan (reintenta cada 10 min, hasta 24 h). Nunca se envía a la nube.

## Dónde ver los resultados

En la WebUI de PERSONAL o en `/workspace` por SMB. Telegram solo envía texto: te avisa cuando termina una tarea
larga y el fichero queda en `/workspace`.
