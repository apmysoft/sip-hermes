# SIP + Hermes: un asistente de IA doméstico, local y con barreras de verdad

Esto es el diseño completo, y lo construido de verdad, de un sistema de agentes de IA para casa. Corre en dos
ordenadores normales, trabaja con tus documentos y no envía ningún dato personal a la nube. Las barreras de
seguridad las ponen el sistema operativo, la red y los permisos, no la «buena voluntad» del modelo.

Se publica para que se pueda **replicar o adaptar**, no como un instalador de un clic: las piezas de `referencia/`
son las que funcionan en el montaje original, con rutas, usuarios y redes reales sustituidos por variables y
marcadores.

## Qué hace

- **Un agente para tus documentos (PERSONAL):** busca y lee en tu archivo personal (facturas, contratos, notas), con
  índice de texto completo y OCR. Propone nombres para lo que entra nuevo, transcribe audio y genera o retoca
  imágenes. Se usa desde Telegram o desde una web, solo por la VPN. **No tiene Internet ni modelos en la nube.**
- **Un agente para programar (CODING):** trabaja en un *worker* aislado del equipo potente, sin red ni acceso a tus
  documentos, y de noche puede avanzar tareas de una cola con un verificador independiente.
- **Un agente para investigar (RESEARCH):** busca en Internet con un buscador propio y un navegador de órdenes
  fijas, sin ver ningún dato tuyo, y deja los resultados en tu bandeja de entrada.
- **Todo lo que tiene efecto real** (renombrar, apagar un equipo, crear un servicio Docker) se hace con un código de
  un solo uso que te llega al móvil y que el agente nunca ve.
- **Nada se borra:** todas las escrituras pasan por un servicio (filegate) que, en lugar de borrar, mueve a una
  cuarentena de 180 días.

## Con qué

- **Servidor siempre encendido:** i7-6700K, 16 GB y GTX 1070 (8 GB). Aloja los agentes ([Hermes Agent](https://github.com/NousResearch/hermes-agent))
  en contenedores, un modelo pequeño (4B) de respaldo y todos los servicios de control.
- **Equipo de trabajo con GPU:** Ryzen 9 5950X y RX 7900 XTX (24 GB). Sirve el modelo grande (27B a 64K de
  contexto) con llama.cpp + llama-swap, además de Whisper, ComfyUI y el OCR. Se enciende por Wake-on-LAN cuando
  hace falta y se apaga solo.
- **Red:** Tailscale con política *deny by default*; nftables por zona; nada abierto a Internet.
- Linux (Ubuntu / Mint), Docker, systemd y Python con la biblioteca estándar en casi todo.

## Por dónde empezar

| Si quieres… | Lee |
|---|---|
| Entender la idea en 10 minutos | [`docs/COMO-FUNCIONA.md`](docs/COMO-FUNCIONA.md) |
| Ver el diseño completo y su razonamiento | [`docs/ARQUITECTURA.md`](docs/ARQUITECTURA.md). Empieza por la sección 0, que resume en qué se apartó lo construido del diseño |
| Saber qué salió mal y cómo se arregló | [`docs/LECCIONES.md`](docs/LECCIONES.md) |
| Montarlo tú | [`docs/IMPLANTACION.md`](docs/IMPLANTACION.md) (fases y pruebas de seguridad) y [`referencia/`](referencia/) |
| Mantenerlo | [`docs/OPERACION.md`](docs/OPERACION.md) |
| Reglas para el agente que te ayude a montarlo | [`plantillas/AGENTS.md`](plantillas/AGENTS.md) |

## Estructura

```
docs/         diseño, funcionamiento, lecciones, implantación y operación
referencia/   las piezas reales (servicios, unidades systemd, cortafuegos, plugins, apply.sh), anonimizadas
plantillas/   documentos de control vacíos: estado actual, identidades, rotación de claves y reglas del agente
```

## Lo que no está

- **Datos personales, credenciales y el diario de implantación:** se han destilado en `LECCIONES.md` e
  `IMPLANTACION.md`.
- **Servicios domésticos ajenos** al sistema (multimedia, descargas…). Se mencionan donde compiten por la GPU o la
  RAM, porque eso condiciona decisiones.
- **El motor de automatismos** (flujos de redacción programados), que es un proyecto aparte.

## Cómo adaptar las rutas

En `referencia/` aparecen marcadores que tienes que sustituir por los tuyos:

| Marcador | Qué es |
|---|---|
| `${PARA_ROOT}` | Raíz de tus documentos (estructura PARA: `00_entrada`, `01_proyectos`, `02_areas`, `03_recursos`, `04_archivo`) |
| `${NEO_TAILNET_IP}`, `${HALO_TAILNET_IP}` | IP de Tailscale del servidor y del equipo con GPU |
| `${NEO_LAN_IP}`, `${HALO_LAN_IP}`, `${HALO_MAC}`, `${LAN_*}` | Direcciones de la LAN y MAC del equipo con GPU, para el WOL |
| `${STAGING_ROOT}` | Disco aparte para staging y cuarentena |
| `${DOCKER_DATA}`, `${BACKUP_VAULT}` | Datos de Docker y destino de las copias (Kopia) |
| `${TAILNET}`, `${TAILNET_DOMAIN}`, `${TAILNET_IP_DISPOSITIVO_N}` | Tu tailnet y la IP de tus otros dispositivos |
| `/home/usuario`, `usuario@example.org` | Tu usuario y tu correo |

Busca también `Neo` y `HALO`: son los nombres de los dos equipos.

## Estado

Diseño v2.4 implantado y en uso diario desde noviembre de 2026, con las pruebas de seguridad O1–O13 superadas. Las
versiones (Hermes 0.22.7, modelos e imágenes) están fijadas por digest o sha256 en `referencia/`; comprueba las
actuales antes de copiarlas.

La implantación se hizo con un agente de programación (Claude Code) como guía, con sudo temporal y las reglas de
`plantillas/AGENTS.md`. Buena parte de los ficheros de `referencia/` y de los documentos se escribieron así, siempre
con revisión y pruebas en el sistema real.

## Licencia

- **Código** (`referencia/`, scripts): [GPL-3.0-or-later](LICENSE).
- **Documentación** (`docs/`, `plantillas/`, este README): [CC BY-SA 4.0](LICENSE-docs).

Ambas son copyleft: si lo mejoras y lo redistribuyes, comparte las mejoras con la misma licencia. Las propuestas y
correcciones son bienvenidas como *issues* o *pull requests*.
