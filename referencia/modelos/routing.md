# Coordinador de modelos (Fase 5, H.4)

Estado a **2026-10-29**. Distingue lo diseñado (v2.4), lo documentado y lo
**verificado en Neo**.

## Perfiles vs. zonas (aclaración importante)

v2.4 define **4 zonas** (PERSONAL, CODING, RESEARCH; BROWSER es capacidad de
RESEARCH) + SYSTEM como plano de infraestructura, y exige que cada zona sea un
**proceso/Usuario/contenedor/red distintos**. Los *profiles* de Hermes son solo
la **primera capa lógica** (config, memoria, skills, sesiones, cron); el propio
documento dice **“Profiles Hermes ≠ aislamiento”**. Hoy hay **un solo
contenedor** con 6 perfiles: las zonas físicas aún no están desplegadas.

Los 6 perfiles actuales (creados por el bootstrap; no son las 4 zonas):

| Perfil | Papel hoy | Backend |
|---|---|---|
| `personal` | asistente personal + Gestor de Entrada (**sticky actual**) | `local` (contenedor) |
| `default` | perfil base / tareas de administración | `ssh` → HALO |
| `coding` | implementación con `qwen3-coder:30b` | `ssh` → HALO |
| `research` | investigación (sin cloud aún) | `ssh` → HALO |
| `sandbox` | runner aislado (pruebas) | `ssh` → HALO |
| `system` | tareas de sistema | `ssh` → HALO |

**No hay enrutado automático por tarea**: el “coordinador” de H.4 es hoy
asignación perfil→modelo + override por tarea en kanban. Que un perfil no vea
datos “calientes” no lo inutiliza: cada zona debe ver solo lo suyo por diseño
(CODING no lee PARA; RESEARCH no ve datos personales). La interacción entre
zonas es deliberadamente estrecha (solo `00_entrada` vía filegate y promoción
humana), no un flujo libre entre perfiles.

Por eso el Gestor de Entrada se gestiona desde `personal`: es la zona que sí
puede ver el `/workspace` del contenedor y hablar con el puente. `personal`
queda como perfil activo (sticky) para que no tengas que elegirlo en cada
sesión.

## Política H.4 (diseñada en v2.4)

| Tipo de tarea | Modelo asignado |
|---|---|
| Clasificar `00_entrada`, resúmenes cortos P1 | Tiny GPU (Neo) |
| Implementación, refactor, tests del proyecto activo | `qwen3-coder:30b` (HALO) |
| Arquitectura, diseño, revisión de spec (DEV) | Cloud free tier vía LiteLLM |
| Investigación web | Cloud (RESEARCH) |

Anti-quema: rate-limits por clave dummy en LiteLLM + circuit breaker en el
orquestador. Actualización semanal de modelos: cron en RESEARCH propone y el
humano aprueba.

## Realidad verificada en Neo (29-10-2026)

- **6 perfiles** Hermes: `default`, `coding`, `personal`, `research`,
  `sandbox`, `system` (todos con gateway parado).
- Antes de este bloque **todos** apuntaban a `qwen3.8:27b` (HALO).
- **`coding` → `qwen3-coder:30b` (HALO)**, `agent.reasoning_overrides` con
  `qwen3-coder:30b: "none"`, backend de terminal **SSH** a HALO
  (`${HALO_TAILNET_IP}`). Prueba real `hermes -z` → `OK`; el modelo se cargó en
  VRAM (20,25 GB, Q4_K_M).
- **Tiny Neo** (`qwen3-4b-instruct`) disponible en `127.0.0.1:11434`;
  **Hermes todavía no lo usa** (lo usa directamente el Gestor de Entrada).
- **Zonas por backend (29-10):** `personal` → `terminal.backend: local` +
  `cwd: /workspace` (contenedor; es la zona del asistente personal y del
  puente al Gestor de Entrada). `coding` → `ssh` a HALO. El resto sigue en
  `ssh`. Las herramientas de fichero de Hermes siguen al backend, así que un
  perfil con `ssh` **no** ve el `/workspace` del contenedor.
- **Sin proveedores cloud** configurados (llegan en Fase 6 con LiteLLM+Postgres).
- Mecanismos disponibles en Hermes v0.21.3: `profile` (modelo por perfil),
  `fallback` (cadena de failover), `moa` (mezcla de agentes), `kanban
  set-model` (override de modelo **por tarea**), `cron` (evaluación semanal;
  difirido a Fase 6: sin cloud no aporta, ver 99-NOTAS 30-10).
- **No hay router dinámico automático por tipo de tarea.** Hoy el
  "coordinador" es asignación perfil→modelo + overrides por tarea en kanban;
  el router determinista de H.4 queda pendiente de decisión.

## Cómo se cambia el modelo de un perfil

Usar `HERMES_HOME` apuntando al perfil (no `HERMES_PROFILE`, que resuelve al
config global):

```bash
sudo docker exec -u 1000 \
  -e HERMES_HOME=/home/hermeswebui/.hermes/profiles/<perfil> \
  hermes-webui /app/venv/bin/hermes config set model.default <modelo>
```

Verificación: `hermes profile show <perfil>` y una prueba real `hermes -z`.

## Modelos sin "thinking"

`qwen3-coder:30b` devuelve `HTTP 400: does not support thinking` si el perfil
pide razonamiento. Solución por perfil (clave `agent.reasoning_overrides`,
el valor debe ser **cadena**; `none` sin comillas se parsea como `null`):

```yaml
agent:
  reasoning_overrides:
    qwen3-coder:30b: "none"
```

## Fallback y circuit breaker (29-10-2026)

**Qué trae Hermes de serie:** `fallback_providers`, una cadena ordenada de
`{provider, model, base_url}` que se prueba cuando el primario falla por
**rate-limit, 5xx o error de conexión**. Además, ante rate-limits consecutivos
arma un **cooldown exponencial del primario** (60 s → 2 min → … → 4 h) por
sesión de agente: eso es el “circuit breaker” real que existe hoy.

**Qué NO trae:** un breaker persistente de cuota/gasto. Eso era del
orquestador (v2.4) y depende de LiteLLM + Postgres con budgets por clave
dummy, que llegan en Fase 6.

### Configuración aplicada

| Perfil | Primario | Fallback 1 | Fallback 2 |
|---|---|---|---|
| `personal` | `qwen3.8:27b-64k` (desde el 04-11; antes `qwen3.8:27b`, 32k) | `gpt-oss:20b` | `qwen3.6:27b` |
| `coding` | `qwen3-coder:30b` | `qwen3.8:27b` | `gpt-oss:20b` |

**03-11-2026:** el perfil `coding` de esta tabla está archivado; la zona CODING (`hermes-coding`, Fase 7)
usa `qwen3.8:27b-64k` → `gpt-oss:20b` (`sip-config/coding/set-executor.sh`). `qwen3-coder:30b` sigue
instalado en HALO, fuera de la cadena: 0 de 6 intentos útiles en los pilotos (`sip-config/piloto/`).

También `agent.api_max_retries: 1` para que el failover sea rápido en vez de
reintentar 3 veces contra un proveedor caído.

### Verificado (29-10)

1. Copia desechable del perfil con el primario apuntando a un **puerto cerrado**
   → respondió el fallback (`gpt-oss:20b` cargado en HALO).
2. Primario apuntando a un **mock que devuelve 429** → respondió el fallback.
3. Perfiles reales con la cadena aplicada: `personal` y `coding` responden
   `OK` por el camino normal; `reasoning_overrides` del coder intacto.
4. Diff contra backup: solo `agent.api_max_retries` y `fallback_providers`.

Backup previo:
`/root/sip-agent-backups/2026-10-29/fase5/fallback-pre-173447.tgz`.

### Límite importante

Todos los fallbacks viven en **HALO**. Si HALO está apagado o inalcanzable, la
cadena se agota: no hay failover real de host. El tiny de Neo **no** está en la
cadena porque escucha solo en `127.0.0.1:11434` y el contenedor no lo alcanza;
abrirlo a la red del contenedor es una decisión de exposición pendiente. El
failover a cloud llegará con LiteLLM (Fase 6).

## Router por tarea: `kanban set-model` (29-10/30-10-2026)

**Qué es:** un tablero SQLite duradero compartido por todos los perfiles. Cada
tarea se asigna a un perfil y la ejecuta un *dispatcher* que lanza un worker en
un workspace aislado. La tarea puede fijar **modelo y proveedor** propios, que
se aplican en el siguiente *dispatch*.

**Flujo verificado (30-10):**

```bash
# crear con override
hermes kanban create "Implementar X" \
  --assignee personal --model qwen3-coder:30b --provider custom:ollama

# o fijarlo después (afecta al siguiente dispatch)
hermes kanban set-model <task_id> qwen3-coder:30b --provider custom:ollama

# ejecutar (una pasada; sin gateway)
hermes kanban dispatch --max 1
```

**Evidencia real (30-10):**

- Override aplicado de verdad: tarea con `gpt-oss:20b` (distinto del primario)
  → durante todo el run `ollama ps` en HALO mostró **`gpt-oss:20b`**.
- **Hallazgo importante (1c):** una tarea `personal` con override
  `qwen3-coder:30b` **falló primero con `HTTP 400: does not support
  thinking`**, porque el worker usa la config del **perfil asignado** (y
  `personal` no tenía el override de reasoning) y la salvó la **cadena de
  fallback** (`qwen3.8:27b`). Lección doble: (a) los ajustes por modelo . como
  `reasoning_overrides` deben existir en el perfil asignado; (b) el fallback
  cubre errores 400 reales, no solo red/5xx. Corregido: override añadido a
  `personal` y al config global; repetida la prueba → el run llamó a
  `qwen3-coder:30b` directamente sin 400.
- **Hallazgo 2 (1c):** el worker termina su turno y puede quedar `running`
  stale si el modelo responde texto sin llamar a la herramienta
  `kanban_complete` (ocurrió con el coder en una tarea trivial; gpt-oss sí la
  llamó). El sistema tiene **reclaim** en el siguiente `dispatch` y auto-block
  tras 2 fallos; hay que esperarse estos retardos y no purgar a mano sin
  comprobar.
- Las tareas de prueba se archivaron y purgaron; el tablero queda vacío.

**Límite operativo importante:** el dispatcher de producción vive en el
**gateway** (`hermes gateway start`); el antiguo `kanban daemon` está
deprecado. Hoy los gateways están parados, así que las tareas **no se ejecutan
solas**: hay que lanzar `hermes kanban dispatch` (o arrancar el gateway, que
además habilita canales de mensajería y es una decisión aparte). Se ha dejado
en modo manual a propósito.

**Límite de diseño:** el override es **explícito por tarea**. No existe todavía
clasificación automática de “esta tarea es de coding → ponle el 30B”. Eso lo
puede hacer el agente al crear la tarea (con reglas/skill) o tú al crearla; el
router determinista completo sigue pendiente.

## Router automático: skill `kanban-router` (30-10-2026) ✅

Reglas versionadas en `sip-config/modelos/kanban-router-SKILL.md`, instaladas
en el árbol global y los 6 perfiles (verificada `enabled`). La tabla asigna:

| Tipo de tarea | assignee | modelo |
|---|---|---|
| Implementación/refactor/tests | `coding` | `qwen3-coder:30b` (desde el 03-11, `qwen3.8:27b-64k`: lento, ~1 h por tarea mediana) |
| Personal/generalista | `personal` | sin override (qwen3.8:27b-64k desde el 04-11) |
| Ligera/contexto largo | `personal` | `gpt-oss:20b` solo si conviene |
| Gestor de Entrada | vía skill `gestor-entrada`, no kanban | tiny host |

**Verificación end-to-end (30-10, sesión WebUI real, perfil `personal`):**
el asistente creó `t_b32d46fb` («Refactor de la función de parseo de un
proyecto») por sí solo: assignee `coding`, `model_override
qwen3-coder:30b` + `provider custom:ollama`, workspace `dir @
/workspace/kanban/refactor-parseo`, `idempotency_key
2026-10-30-refactor-parseo`, estado `ready`, sin dispatch ni ejecución
(board: 1 ready / 0 running). El id se verificó con `kanban show`.

**Hallazgo de la primera prueba (mismo día, corregido):** la sesión WebUI del
perfil `personal` no tenía ni terminal ni los tools nativos de kanban. Causa:
el `platform_toolsets.cli` del perfil era una lista granular heredada sin
`terminal`/`web`/`kanban` (diminuto: 11 tools visibles + 3 diferidas,
recompuesto y coincidente con el journal). Corrección: añadido `kanban` a
`platform_toolsets.cli` de `personal` (backup
`/root/sip-agent-backups/2026-10-30/fase5/toolsets-pre-150602.tgz`);
compulsado por composición simulada: los 14 tools `kanban_*` aparecen. La
skill prescribe ahora el tool nativo (`kanban_create` con
`model`/`provider`/`workspace_kind`/`workspace_path`/`skills`/
`idempotency_key`) como camino principal, sin shell. Notas: los hijos de
`delegate_task` no pueden mutar el tablero (diseño del agente); el agente de
WebUI no puede ejecutar `kanban dispatch` (sin terminal): lo lanza el
usuario; el tablero es una sola base global por diseño (sin bifurcación por
perfil). `terminal` sigue sin exponerse en la lista `cli` del perfil —
exponerlo es decisión separada (las aprobaciones existentes lo salvaguardan).

## Vía LiteLLM (Fase 6 Bloque B, 01-11-2026)

`coding` y `research` usan `custom:litellm` (`http://sip-litellm:4000/v1`);
`personal`, `default`, `system` y `sandbox` siguen directos a Ollama. Detalle y
evidencia en `sip-config/litellm/README.md`.

- Los fallbacks de `coding` siguen directos a Ollama: si el proxy cae o da `429`,
  responde `qwen3.8:27b`, no el coder. Solo hay modelos locales, sin riesgo cloud.
- `kanban-router` fija `custom:litellm` para `coding` desde el 01-11 (verificado: tarea
  con ese override por `sk-coding`). `personal` sigue en `custom:ollama`.
- Hermes calcula 131072–262144 de contexto, pero Ollama carga 32768
  (`OLLAMA_CONTEXT_LENGTH` en HALO), también en directo. Es previo al proxy.

## Local, cloud y datos privados (aclaración del 01-11-2026)

- **Quién decide:** no hay elección por dificultad. El agente aplica la tabla de
  `kanban-router` al crear la tarea, y el resto del tiempo cada perfil usa su modelo. El
  fallback solo actúa ante fallos. v2.4 pide política determinista por zona y tipo de
  tarea: el LLM elige dentro de los límites, pero no los fija.
- **Cloud diseña, local implementa (H.4):** solo DEV. Diseñado, sin implementar ni probar.
- **Datos P1:** solo modelos locales (H.1, H.2). No hay fragmentación automática: para
  dividir la tarea, alguien tiene que leer los datos, y un resumen hecho por un modelo
  local puede filtrar detalles. Según v2.4, un prompt con contexto P1 es P1.
- **Propuesta, sin implementar, a decidir por el usuario:** procedimiento a ciegas. El
  cloud diseña un procedimiento a partir de una descripción genérica escrita por el
  humano, sin datos; el humano lo revisa y lo promueve como skill; PERSONAL lo ejecuta en
  local. El flujo va solo de cloud a local. La revisión también frena inyecciones.
- **Límite actual:** taint tracking sin implementar y zonas físicas sin desplegar.

## Pendiente (Fase 5)

Revisado el 04-11-2026 contra lo desplegado:

1. ~~Router automático por tipo de tarea~~ → **cubierto por zonas**. La política determinista
   de v2.4 es por zona: PERSONAL solo local (`qwen3.8:27b-64k`), CODING con ejecutor local
   por LiteLLM, RESEARCH cloud por LiteLLM con su clave. Dentro de cada zona, `kanban-router`
   fija el modelo por tipo de tarea al crearla. No hace falta un router que decida solo: el
   LLM elige dentro de esos límites y no los fija.
2. ~~Zonas físicas~~ → **desplegadas en la Fase 7**: `hermes-webui` (PERSONAL, UID 1000, red
   `sip`), `hermes-coding*` (993, red `coding`) y `hermes-research` (995, red `research`).
   Los perfiles que quedan en `hermes-webui` (`default`, `sandbox`, `system`) son capa lógica
   de PERSONAL.
3. ~~Cablear `research` a cloud~~ ✅ (Fase 6). `system` no necesita cloud.
4. ~~Cron de evaluación semanal de modelos~~ → **desplegado el 02-11 (Fase 9)**; ver `EVALUACION.md`.
5. ~~Gateway~~ → `sip-gateway` propio (Fase 7, 02-11).
6. ~~Spike de la vía de ejecución~~ → **decidido: backend SSH nativo** (S.13, opción 1). CODING
   trabaja en HALO por SSH con worker acotado; no hizo falta MCP ni dispatcher.
7. ~~S.2 y escalera 3B→7B~~ → **S.2 ✅ 04-11**; se queda el 4B (`llm-neo/README.md`).
8. Failover de host: si HALO cae, **fail-closed** según H.3. PERSONAL no salta a cloud con P1;
   lo despierta `sip-halo-wake` (WOL; si falla, aviso por Telegram para el enchufe). Sin
   verificar: un despertar real con HALO apagado (prueba del usuario, `wol/README.md`).

## Rollback

Backup previo (29-10):
`/root/sip-agent-backups/2026-10-29/fase5/perfiles-config-121310.tgz`
(config global + `config.yaml` de los 6 perfiles).

Para volver `coding` al estado anterior:

```bash
sudo docker exec -u 1000 \
  -e HERMES_HOME=/home/hermeswebui/.hermes/profiles/coding \
  hermes-webui /app/venv/bin/hermes config set model.default qwen3.8:27b
# y quitar el override de reasoning del config.yaml del perfil
```

Para quitar la cadena de fallback de un perfil:

```bash
hermes fallback clear        # con HERMES_HOME del perfil
hermes config unset agent.api_max_retries
```
