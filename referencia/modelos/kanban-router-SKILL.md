---
name: kanban-router
description: Reglas para crear tareas en el tablero kanban de Hermes con el modelo, proveedor y perfil correctos automáticamente. Úsala SIEMPRE que vayas a crear una tarea kanban o fijar su modelo (kanban create / set-model / swarm).
---
# Router de tareas kanban (SIP)

Reglas de asignación deterministas (H.4 del plan SIP). Aplicarlas **antes** de
crear cualquier tarea: una tarea sin el modelo correcto desperdicia el modelo
grande o ejecuta coding con el generalista.

## Cómo crear la tarea

**Camino principal: el tool nativo `kanban_create`** (no hace falta shell ni
terminal):

```json
kanban_create(
  title="Refactor de la función de parseo",
  assignee="coding",
  body="<especificación completa>",
  model="qwen3.8:27b-64k",
  provider="custom:litellm",
  workspace_kind="dir", workspace_path="/workspace/kanban/refactor-parseo",
  idempotency_key="2026-10-30-refactor-parseo"
)
```

- `kanban_create` está disponible directamente en tu toolset; úsalo siempre
  antes que recurrir a comandos.
- El proveedor depende del assignee: `custom:litellm` para `coding` y `custom:ollama`
  para `personal`, que nunca pasa por el proxy.
- Usa `idempotency_key` descriptiva (p. ej. `<fecha>-<slug>`) para evitar
  duplicados.
- Nunca intentes `kanban_create` desde un subagente propio (los hijos de
  `delegate_task` no pueden mutar el tablero): créala tú mismo.
- El id sale de la respuesta del tool; nunca parsees `kanban list`.

**Camino alternativo (CLI, solo si el tool no existe):** `hermes` no está en
el PATH de tu shell. Usa siempre la ruta absoluta:

```bash
/app/venv/bin/hermes kanban create "TÍTULO" \
  --assignee <perfil> --workspace scratch \
  --model <modelo> --provider <custom:litellm|custom:ollama> \
  --idempotency-key <clave-única> --json
```

## Tabla de enrutado

| Tipo de tarea | assignee | Modelo (parámetros `model`/`provider`) |
|---|---|---|
| Implementación, refactor, tests, migración de código | `coding` | `qwen3.8:27b-64k` + `custom:litellm` (lento: ~1 h en una tarea mediana; para lotes, no para urgencias) |
| Tarea personal/general del asistente (resúmenes, notas, agenda, consultas) | `personal` | sin `model` (hereda: qwen3.8:27b) |
| Tareas ligeras de poca computación o con contexto largo y simple | `personal` | `gpt-oss:20b` + `custom:ollama` (solo si conviene) |
| Investigación web (RESEARCH) | `research` | sin `model` (cloud llegará en Fase 6) |
| Tareas del Gestor de Entrada / datos personales | NO usar kanban: skill `gestor-entrada` | — |

El workspace por defecto es `scratch` (efímero); si debe conservarse usa
`workspace_kind="dir"` + `workspace_path` absoluto. Si la tarea necesita
ejecutar en HALO (repos, builds, tests), el assignee es `coding` (su terminal
va por SSH a HALO). Si solo usa el contenedor, `personal`.

## Tras crear la tarea

1. **No la ejecutes.** El gateway está parado a propósito y tú no tienes
   terminal en la WebUI: quien lanza la ejecución es el usuario con su
   comando (`hermes kanban dispatch --max 1`). Propónselo en tu respuesta.
   **Nunca** intentes lanzar `hermes gateway` — no permitido.
2. Reporta al usuario: id de la tarea, assignee, modelo elegido y por qué
   (cada uno en una línea), y cómo se ejecutará (`kanban show <id>`).
3. Si el usuario quiere que NADA se ejecute sin su revisión, no dispatch:
   deja la tarea en `ready` y dilo.

## Reglas duras

- Nunca fijes un modelo cloud ni uses otro proveedor que los de esta tabla. Una tarea
  con datos personales nunca lleva `custom:litellm`.
- **Nunca** edites el `model.default` de los perfiles para complementar una tarea: el ajuste por-perfil queda como está.
- El workspace `scratch` es **efímero** y se borra al terminar; si el resultado
  debe conservarse, usa `--workspace dir:/workspace/kanban/<slug>` y dilo al
  usuario.
- No cambies de modelo a mitad de una tarea en curso: si hace falta, crea otra.
- Si el usuario pide explícitamente otro modelo, gana el usuario sobre esta
  tabla, pero dilo explícitamente en la respuesta.
