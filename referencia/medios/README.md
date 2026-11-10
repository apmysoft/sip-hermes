# Herramientas de medios, documentos y texto en HALO (06-11-2026)

Todo en `/opt/sip-medios` (root, lectura para todos). Entorno: `. /opt/sip-medios/entorno` (PATH y cachés de
modelos en `/opt/sip-medios/modelos`, `HF_HUB_OFFLINE=1`). **En CPU por defecto**: la GPU solo a través del
planificador (llama-swap), para no chocar con el modelo de texto (Demucs, por ejemplo, usa la GPU por su
cuenta si no se le dice `-d cpu`).

| Herramienta | Versión / origen |
|---|---|
| pandoc, graphviz, exiftool, espeak-ng, tesseract (spa, eng), ocrmypdf, qpdf, poppler | apt (Ubuntu 24.04) |
| Typst | 0.15.1, digest del release `a6d077d0…` (`/usr/local/bin/typst`) |
| DeepFilterNet `deep-filter` | 0.5.6, binario estático. El release no publica sha256; registrado `70775e25…` |
| Marp CLI, Mermaid CLI | npm 4.5.1 y 11.17.1 (la 12 pide node 22; el sistema tiene 18) |
| PyTorch ROCm | 2.14.1+rocm7.2 (como ComfyUI) |
| rembg (BiRefNet), PySceneDetect, Demucs, Kokoro, Docling, soundfile | pip, versiones en `install-halo.sh` |

- `install-halo.sh`: instalación reproducible. El 06-11 se instaló paso a paso y el script recoge el
  resultado.
- `probar.sh`: 10 pruebas con datos sintéticos (Piper, ffmpeg, Typst), como usuario normal. **10/10 OK el
  06-11.** Las de texto (pandoc, Typst, Graphviz, Marp, Mermaid) se probaron aparte, con resultado OK.
- **Descartado:** auto-editor. Falla con SIGSEGV como usuario normal (2 veces, regla 10); lo sustituye
  `ffmpeg -af silenceremove`. DeepFilterNet por pip tampoco instala en Python 3.12, y por eso se usa el
  binario.
- **Conexión con Hermes (06-11): servicio `sip-medios`.**
  - `sip-medios-api.py`: usuario `sip-medios`, solo `127.0.0.1:8190`, sin Internet (`IPAddressDeny`), 12 GB de
    RAM como máximo, sin dispositivos.
  - Lo arranca llama-swap (modelo `medios`, grupo `cpu`, que no echa al modelo de texto) por `sip-gpu-unidad` y
    polkit (`50-sip-llm-gpu.rules`, ampliado solo a esta unidad).
  - Acceso: `http://${HALO_TAILNET_IP}:11434/upstream/medios/op/<operacion>`.
  - 11 operaciones fijas: ruido, silencios, separar, escenas, subtitulos, fondo, voz, ocr, docling, documento,
    diagrama.
  - Instalación con `apply-api.sh`; pruebas con `probar-api.sh` (13/13 el 06-11).
  - **El documento PDF** se hace con pandoc → Typst sin plantilla (la de pandoc 3.1.3 no compila con
    Typst 0.15).
- Rollback: `rm -rf /opt/sip-medios /usr/local/bin/typst` y `apt remove` de los paquetes.
