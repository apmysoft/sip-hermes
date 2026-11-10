# Zona CODING propia (Fase 7)

Estado a 02-11-2026: **desplegada**; falta que el usuario pruebe la WebUI `:8788` y `/c` desde el móvil. Objetivo (v2.4, decisión 10 y gateway): que CODING deje de compartir
proceso y `.env` con PERSONAL en `hermes-webui`, y que Telegram (`/c`) llegue a ella por su API.

## Punto de partida (verificado)

- Perfil `profiles/coding` en `hermes-webui`: 4,9 MB; modelo `qwen3-coder:30b` por LiteLLM (`sk-coding`,
  solo modelos locales, 10 rpm y 1 $/día); fallback a Ollama de HALO; terminal por SSH a `hermes-worker`
  en HALO con `id_ed25519_halo_worker`.
- Única variable real en su `.env`: `LITELLM_API_KEY`.
- Comparte con los demás perfiles: `kanban.db` (tablero único), `ssh/` (claves de HALO y del runner),
  la imagen y el proceso.

## Diseño propuesto

| Pieza | Diseño |
|---|---|
| `hermes-coding` | Contenedor propio con la imagen de la WebUI (agente v0.21.3 + parche SSH) y solo el perfil `coding` migrado a un volumen nuevo. UID propio |
| Interfaz | WebUI propia en `${NEO_TAILNET_IP}:8788` (tailnet) y API en red `internal` para `sip-gateway` |
| Red `coding` | `10.23.0.0/24`: solo HALO `:22` y `:11434` y LiteLLM `:4000` (dentro del bridge). Sin DNS externo, LAN ni internet: ejecuta en HALO |
| Enlace `gw-coding` | `10.24.0.0/24`, `internal`, como `gw-research` |
| Claves | Solo `id_ed25519_halo_worker` y `sk-coding`. Ni la clave del runner sandbox ni nada de PERSONAL |
| Kanban | Tablero propio de CODING. El de PERSONAL queda en `hermes-webui` |
| Migración | Copia del perfil (no se mueve); el perfil viejo queda desactivado en la WebUI como archivo y para rollback |

## Decisiones del usuario (02-11, aceptadas)

1. **Interfaz:** WebUI propia en `:8788` además de Telegram. `tailscale/policy.hujson` añade `8788` a la
   regla de `tag:halo` (el usuario ya tiene `tag:sip:*`); lo aplica el usuario en la consola.
2. **Kanban por zona.** En el tablero compartido solo hay 3 tareas de `coding`, archivadas: se empieza
   con tablero vacío.
3. **Firewall:** `apply-firewall.sh` + `nftables-sip.candidate.nft` (pasa `nft -c`); lo aplica el usuario.
4. **Cloud en CODING:** fuera de este bloque. Encaja con el flujo objetivo (planificar en cloud, ejecutar
   en HALO, escalar si fallan las pruebas), a pilotar con un proyecto real.
5. **CLI de Codex/Claude Code con suscripción:** fuera de momento (credenciales al alcance del agente).

## Concreción

- UID de zona reservado `hermes-coding` (993:983) como `WANTED_UID`/`WANTED_GID`.
- WOL: solo `${DOCKER_DATA}/hermes/workspace/_wol` montado en `/workspace/_wol`, con ACL para 993.
- LiteLLM entra en la red `coding` con IP fija `10.23.0.10`.
- API para `sip-gateway`: contenedor hermano `hermes-coding-api` (`hermes gateway run`, solo API) con el
  mismo volumen, en `coding` + `gw-coding` (`10.24.0.10`), herramientas de `api_server` fijadas.
- Red `coding` sin DNS externo: si Hermes intenta resolver nombres de internet, fallará (vigilar demoras).

## Desplegado y verificado el 02-11-2026

- Firewall de la zona aplicado por el usuario (29/29 PASS); ACL `8788` aplicada por el usuario.
- LiteLLM en la red `coding` (`10.23.0.10`), sano, salida a internet aún por `research`.
- `hermes-coding` (WebUI `:8788`, UID 993:983, `cap_drop ALL` + 5 capacidades de arranque,
  `no-new-privileges`): copia del perfil sin `gestor-entrada` ni skills de pruebas; solo la clave del
  worker. Turno real: `hostname` en HALO → `HALO-Neo` con `sk-coding` y `qwen3-coder:30b`. `/` → login.
  No alcanza la WebUI personal, LiteLLM por `research` ni el runner.
- `hermes-coding-api` (`10.24.0.10:8642`, solo lectura, `cap_drop ALL`): `401`/`401`/`200`, cerrada desde
  `gw-research` y `coding`. Herramientas de `api_server`: `terminal`, `file`, `todo`, `memory`,
  `session_search`, `skills`.
- **Hallazgo ⚠️ corregido:** por la API, con `approvals.mode: smart`, un `rm -rf` lo aprobó el modelo
  guardián y se ejecutó (la API cuenta como gateway, no como desatendida, y `unattended_mode: deny` no se
  aplica). Corrección: la API monta `config.api.yaml` (de `make-api-config.sh`) con `mode: manual` y
  `timeout: 5`. Verificado: `rm -rf` queda en `pending_approval`, sin llamada al guardián, y el directorio
  sigue existiendo. La WebUI conserva `smart`.
- `ssh` necesita entrada en `passwd` para 993: `passwd`/`group` generados de la imagen, montados `:ro`.
- `sip-gateway` con `/c` conectado; alcanza solo las dos APIs.

## Ejecutor y lecciones (03-11-2026)

- **Ejecutor:** `qwen3.8:27b-64k` (etiqueta de HALO: `qwen3.8:27b` con `num_ctx` 65536 y `temperature`
  0.6), por LiteLLM, con `gpt-oss:20b` de reserva. `set-executor.sh` crea la etiqueta, la añade a LiteLLM y
  a `sk-coding`, cambia la config por sustitución exacta (conserva los comentarios) y regenera
  `config.api.yaml`. Copias en `/root/sip-agent-backups/2026-11-03/coding-executor-003537`. Motivo: los
  pilotos (`sip-config/piloto/`): 3 de 3 entregas correctas frente a 0 de 6 del coder, pero a 37-49 min
  por tarea; sirve para lotes y para el traspaso nocturno (`sip-config/traspaso/`), no para urgencias.
- **Lecciones:** skill `software-development/sip-lecciones-codigo` (`skills/`, root:root 644: el agente la
  lee y no la puede editar), instalada con `apply-skills.sh`. Doce reglas sacadas de los fallos reales de
  los pilotos. La amplía el revisor; el agente propone con la etiqueta `LECCIÓN:` en su informe.
  Hallazgos al instalarla: Hermes guarda las skills en caché dentro del proceso (hay que reiniciar los dos
  contenedores) y el índice del prompt recorta la descripción a ~57 caracteres, así que la orden de uso va
  al principio.

## Pendiente

- **Verificado por el usuario (02-11):** `/c hostname` → `[CODING] … HALO-Neo`; `/r` lo mismo → RESEARCH no
  tiene acceso a HALO (aislamiento correcto). Contraseña de `:8788` guardada en Vaultwarden.
- **Verificado por el usuario:** login en `:8788` con las conversaciones anteriores de `coding`.
- ~~Desactivar el perfil `coding` en `hermes-webui`~~: **hecho (02-11)**, movido a
  `_archivo/coding-2026-11-02` dentro del volumen (no aparece en la WebUI; sirve de rollback).
- ~~Worker de HALO compartido~~: **limpiado (02-11, autorizado)**. `gestor-entrada` y las 5 skills de pruebas
  movidas (no borradas) del worker y de los homes que se sincronizan con él (CODING y, en `hermes-webui`,
  raíz, `research` y `system`); copias en `/root/sip-agent-backups/2026-11-02/skills-limpieza/` (Neo) y
  `/root/sip-agent-backups/2026-11-02/worker-skills/` (HALO). Tras turnos SSH en `system`, raíz y CODING,
  no reaparecen. PERSONAL (backend local) conserva `gestor-entrada`.
- **Instalaciones al vuelo desactivadas** (`HERMES_DISABLE_LAZY_INSTALLS=1`): sin internet, Hermes intentaba
  instalar `edge-tts` y `boto3` (Bedrock) y cada arranque de CLI esperaba hasta agotar tiempo. Tras el
  cambio, un turno CLI tarda 9 s.
- Los perfiles `default`, `system` y `research` de `hermes-webui` siguen usando el worker de HALO.
- `config.api.yaml` puede divergir de la config de CODING: relanzar `make-api-config.sh` tras cambiarla.
- Copia `config.yaml.pre-api` dentro del volumen de CODING (anterior a fijar `api_server`).

## Riesgos conocidos

Dos WebUI con el mismo agente (versiones y parches iguales) y la skill `kanban-router`, que suponía un
tablero compartido: sin probar en el tablero propio.

## Contraseña de la WebUI (03-11, O4)

Ya no va por `HERMES_WEBUI_PASSWORD` (el compose no carga `/root/sip-coding-webui.env`): es `password_hash` en
`webui/settings.json` del volumen, fijada por el usuario con `sip-config/operacion/o4/fijar-password-webui.sh coding`.
La contraseña que generaba `apply-coding.sh` ya no se usa.
