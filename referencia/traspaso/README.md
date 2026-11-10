# Traspaso nocturno (Fase 9)

Ejecuta tareas de código en CODING por la noche, con un verificador que el agente no controla. Diseño del
informe del 02-11 y de los pilotos (02 y 03-11): el modelo local tarda (~1 h en una tarea mediana) y su
informe no es evidencia, así que solo vale desatendido y verificado.

- `sip-traspaso.timer`: 1:30 cada noche. `ExecCondition` salta si la cola está vacía.
- `sip-traspaso.py run`: tareas en orden de nombre. No empieza intentos entre las 7:00 y las 20:00.
- Ejecutor: el modelo de CODING (`qwen3.8:27b-64k` desde el 03-11; `coding/set-executor.sh`).

## Encolar una tarea

Lo hace el revisor (persona o modelo de frontera), que antes deja el repositorio en el worker de HALO
(`/srv/hermes-worker/workspace/<dir>`, propiedad de `hermes-worker`, con su rama y sin remoto).

```text
/var/lib/sip-traspaso/cola/<AAAAMMDD-NN-slug>/     (root, 0700)
  tarea.json
  mensaje.md      la especificación que recibe CODING (criterios de aceptación incluidos)
```

```json
{
  "workspace": "/workspace/<dir>",
  "permitidos": ["src/App.tsx", "vite.config.ts"],
  "verificacion": ["npm run lint", "npm test", "npm run build 2>&1 | grep -v '(!)'"],
  "ignorar": [],
  "max_intentos": 2,
  "timeout_min": 120,
  "commit": true
}
```

- `verificacion`: órdenes de shell en el workspace; cada una debe salir con 0. Para criterios de tamaño o
  de texto, se escribe la orden de forma que falle (`grep -q`, `test`, `! grep`).
- `permitidos`: patrones `fnmatch` de los ficheros que se pueden cambiar. Cualquier otro cambio desde el
  inicio hace fallar la tarea, también en ficheros ignorados por git (por ejemplo `node_modules`).
  Siempre se ignoran `.git/`, `dist/`, `__pycache__/`, cachés de Vite y `*.tsbuildinfo`; `ignorar` añade
  más.
- `commit`: exige un commit nuevo y el árbol limpio.

## Qué hace con cada tarea

1. Despierta HALO por el servicio WOL si no responde (petición en `_wol/requests`). Si no despierta, la
   tarea sigue en cola y se avisa.
2. Anota la base (`git rev-parse HEAD`) y una marca de tiempo en `.git/sip-traspaso-base`.
3. Manda `mensaje.md` a la API de CODING (conversación `traspaso-<id>`), como `/c`.
4. Verifica por el SSH del worker que ya usa CODING (`docker exec hermes-coding ssh`): sin clave nueva.
5. Si falla, manda una revisión con los fallos y las salidas reales, en la misma conversación. Si lo que
   falla es la llamada a la API (infraestructura, no el modelo), no reintenta: resultado `error_api`.
   La clave de la API llega a la unidad por `LoadCredential` (`ProtectHome` oculta `/root`).
6. Mueve la tarea a `hecho/<id>/` con `informe.md`, añade una línea a `registro.jsonl` y avisa por
   `sip-notify`. **Nunca fusiona, sube ni borra.**

## Límites conocidos

- El agente y el verificador comparten usuario en el worker: un agente decidido podría falsear la marca de
  tiempo (`touch`) o los binarios de `node_modules`. Contra un modelo descuidado basta; contra uno hostil
  no. Por eso la revisión humana del diff sigue siendo obligatoria antes de fusionar.
- Una tarea por vez; el modelo local no admite peticiones paralelas (`OLLAMA_NUM_PARALLEL=1`).
- Preparar el workspace es manual (lo hace quien encola).

## Registro

`registro.jsonl`: una línea por tarea, con modelo, base, intentos (segundos, fallos del verificador e
informe del modelo) y resultado. Es el «registro de tareas» del informe del 02-11: con 15-20 tareas reales
dirá qué parte del trabajo de código rinde HALO.
