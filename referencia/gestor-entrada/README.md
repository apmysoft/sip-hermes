# Gestor de Entrada — SIP (Fase 4, Nivel 1) · MODO RENOMBRE

Desde oct-2026 (decisión del usuario) el gestor **no clasifica ni propone
destinos**: propone **nombres de fichero que expliquen el contenido**, para no
tener que abrir ficheros uno por uno. Nivel 1: nada se renombra sin aprobación
humana.

## Componentes

| Pieza | Dónde | Qué |
|---|---|---|
| `gestor-entrada.py` | `/usr/local/bin/` (root:sip-gestor 0755) | scan / apply / status / dataset export |
| `sip-gestor-entrada.service` | `/etc/systemd/system/` | oneshot para `scan` bajo demanda (sin timer) |
| state SQLite | `/var/lib/sip-gestor-entrada/state.db` | procesados (ruta+hash), propuestas, decisions (dataset S.3), moves |
| Informes | `${STAGING_ROOT}/_staging/_informes/<fecha>/lote-*.{md,json}` | propuestas; aprobación = editar el `.json` |
| Identidad | usuario `sip-gestor` (nologin, `hermes-ro`) | lectura de 00_entrada por ACL; escritura solo en informes + state |
| Vía a PARA | wrapper `/usr/local/bin/sip-gestor-filegate` + sudoers dedicado | PEP `gestor`: move-src/dst ENTRADA (renombra en el sitio) + cuarentena/restore; sin write/mkdir |

## Alcance (honesto)

- **Solo ficheros con texto extraíble**: pdf, docx, odt, rtf, txt, md, csv, tsv
  (en 00_entrada hay ~3.690; el resto son sobre todo fotos/vídeos).
- Fotos/vídeos/audio **no se tocan**: sin visión, renombrar a ciegas dañaría.
- Extracto parcial (≤2 KiB): PDF 1ª página (`pdftotext`), docx/odt vía zip.
- Prioridad a **nombres genéricos** (`descarga (3).pdf`, `scan.pdf`, `IMG_…`,
  nombres cortos); lotes de 50 (`GE_MAX_ITEMS`). Anti ping-pong: un hash ya
  renombrado no se vuelve a proponer (G.4).

## Flujo Nivel 1 (renombres)

1. `sudo systemctl start sip-gestor-entrada.service` (o `sudo -u sip-gestor gestor-entrada.py scan`).
2. Revisar el `.md` del lote (tabla actual → propuesto). Para aprobar **todo el
   lote de una vez**: en el `.json`, poner `"approve_all": true`. Para vetar un
   ítem concreto: `"veto": true` en ese ítem. También se puede aprobar ítem a
   ítem (`"approved": true`) o fijar `"nombre_final"`.
3. `sudo -u sip-gestor gestor-entrada.py apply <lote-id>`: renombra **solo**
   aprobados, con hash verificado; destino = mismo directorio, nuevo nombre
   saneado; si el destino existe o el nombre no cambia, lo salta. Todo queda en
   el log de filegate. Las decisiones (aprobado/rechazado) entran al dataset.
4. Deshacer: `sudo -u sip-gestor sudo -n /usr/local/bin/sip-gestor-filegate
   quarantine <ruta> "motivo"` (nunca rm; TTL 180 d).

## Límites de seguridad

- Contenido jamás sale de Neo (tiny local; P1 local según H.2 de v2.4).
- Fail-closed: error LLM → abstención; sin aprobación no hay cambios; hash que
  cambió → skip; dst fuera de 00_entrada o existente → skip.
- El gestor no escribe/crea en PARA (PEP), no lee tokens ajenos (wrapper), y
  como root solo ejecuta ese wrapper (sudoers de un comando).

## Verificado

- 28-10 (era clasificación): E2E write→scan→approve→move→quarantine con PEP.
- **29-10 — desplegado y verificado en Neo con el tiny real:**
  - Migración de `decisions` y `proposals` sobre la `state.db` existente
    (backup en `/root/sip-agent-backups/2026-10-29/fase4-renombre/`).
  - Lote real `lote-20261029-120413`: 50 ficheros de texto (docx/txt/pdf/rtf),
    **45 renombres propuestos y 5 abstenciones** (4 PDF sin capa de texto + 1
    nombre ya adecuado), **0 errores LLM**, confianza 0.95–1.0.
  - Hallazgo corregido: `max_tokens=120` truncaba el JSON del tiny en los
    `.docx` (20/50 fallos); con 300 → 0.
  - **Pendiente:** aprobar el lote y ejecutar `apply` para verificar el
    renombrado en el sitio.

## Puente Hermes → Gestor (29-10-2026)

Hermes **no ejecuta** el gestor: no tiene montado `_staging` ni PARA, su shell va
por SSH a HALO y sigue en Nivel 1 (no puede aprobar). La vía es una cola de
ficheros en el `/workspace` ya montado, con un worker host que corre como
`sip-gestor`:

- Peticiones: `${DOCKER_DATA}/hermes/workspace/_gestor/requests/<id>.json`
- Resultados: `.../_gestor/results/<id>.json` (informes copiados en `results/<id>/`)
- Archivadas: `.../_gestor/processed/<id>.json`

Superficie cerrada: solo `scan` (opcional `max_items` 1–50), `status` y
`apply` con `lote` validado por regex. `apply` comprueba **leyendo** el `.json`
del lote que ya exista aprobación humana (`approve_all` o `approved` sin veto);
el worker nunca aprueba ni escribe en `_staging`. Sin shell, sin symlinks,
máximo 64 KiB por petición.

Artefactos: `sip-gestor-request.py`, `sip-gestor-bridge.service`,
`sip-gestor-bridge.path` y `SKILL.md` (skill `gestor-entrada` instalada en el
volumen de Hermes, en el árbol global y en los 6 perfiles; detectada como
`enabled`).

**Requisito clave: el perfil debe usar backend de terminal `local`.** Las
herramientas de fichero/terminal de Hermes siguen al backend de terminal. Con
el backend `ssh` (HALO), el agente ve el `/workspace` de **HALO**, no el del
contenedor, y no encuentra el puente. Por eso el perfil de asistente personal
(`personal`) se ha pasado a `terminal.backend: local` con `cwd: /workspace`;
`coding` sigue en `ssh` a HALO. Así cada zona tiene su backend:

| Perfil | Backend | Uso |
|---|---|---|
| `personal` | `local` (contenedor) | asistente personal + Gestor de Entrada |
| `coding` | `ssh` → HALO | implementación con `qwen3-coder:30b` |
| resto | `ssh` → HALO | sin cambios |

Configuración aplicada en `personal` (reversible con `config set`):

```bash
hermes config set terminal.backend local
hermes config set cwd /workspace
```

**Verificado en Neo el 29-10:**

- `status` → `ok:true` (`processed: 84`, `proposals: 111`).
- Acción inválida (`rm -rf /`) → `ok:false`, `acción no permitida`.
- `apply` del lote real sin aprobación → `ok:false`, `sin aprobación humana en el lote`.
- `lote` con traversal (`../../etc/passwd`) → `ok:false`, `lote no válido`.
- `scan` con `max_items: 1` → `lote-20261029-124442` (1 propuesta), informes
  copiados a `results/<id>/`; **nada renombrado**.
- Petición creada **desde el contenedor** (uid 1000) → resultado en ~2 s y
  lectura del resultado desde el contenedor.
- Disparo automático de la unit `.path` verificado (sin `systemctl start`).
- Toda petición sale de `requests/` (aceptada o rechazada): evita el bucle
  `unit-start-limit-hit` detectado en la primera prueba.
- **Prueba de aceptación con el agente real** (perfil `personal`, backend
  `local`, `qwen3.8:27b`): Hermes invocó la skill, escribió
  `requests/status-20261029-01.json`, esperó, leyó el resultado y respondió
  `processed: 84 / proposals: 111`. La skill se instaló además en el árbol de
  los 6 perfiles para que esté disponible en cualquiera con backend `local`.

**Cambio de permisos asociado (solo traversal, sin cambiar modos):**

```bash
setfacl -m u:sip-gestor:x ${DOCKER_DATA} ${DOCKER_DATA}/hermes ${DOCKER_DATA}/hermes/workspace
```

`${DOCKER_DATA}` sigue siendo `710` (dueño `usuario`), pero `sip-gestor` puede
atravesarlo hacia `_gestor`; no gana lectura de otros volúmenes.

## Barrido nocturno (Fase 9, 02-11-2026)

`sip-gestor-nocturno.timer` lanza cada noche a las 3:00 (horas valle) el mismo `scan`, como
`sip-gestor-entrada.service`, que sigue para el uso manual. `gestor-nocturno-check.py` (`ExecCondition`)
lo salta si hay `GE_MAX_PENDIENTES` (2) o más lotes sin decidir, para no apilar lotes sin revisar. Un
salto no cuenta como fallo de la unidad. Sin ficheros nuevos, `scan` no crea lote. Los pendientes salen
en el resumen de las 8:00. Instalación: `apply-nocturno.sh`.

Verificado: con 5 lotes pendientes, `Result=exec-condition`, «se salta el barrido nocturno»; con el
límite subido a mano, la condición deja pasar. **Sin verificar todavía:** un barrido nocturno real,
porque hasta que se decidan los lotes pendientes siempre se salta.

## Decidir sin editar el JSON (03-11-2026)

Petición del usuario: decidir de forma asistida, sin editar nada a mano. Órdenes nuevas (como
`sip-gestor`; el puente de Hermes **no** las expone, porque son decisiones humanas):

```bash
G="sudo -u sip-gestor /usr/local/bin/gestor-entrada.py"
$G lotes                                          # estado: pendiente / decidido / aplicado / descartado
$G decidir lote-… todo veto=3,7 nombre=5:Otro.pdf # o `solo=1,2,4` o `ninguno`; luego `apply lote-…`
$G descartar lote-… "motivo"                      # cierra un lote sin decidir y libera sus ficheros
```

- `decidir` escribe `approved`/`veto` por ítem, `nombre_final` si se da, y `decidido` (cuándo, quién
  por `SUDO_USER`, vía y resumen). **Nunca aprueba una abstención** salvo con `nombre=`: su «propuesta»
  es el nombre actual saneado y, con `approve_all`, el `apply` la renombraba solo por cambiar espacios
  por `_` (fallo previo, corregido para esta vía). `nombre=` pasa por `sanitize_name` (sin rutas).
- `descartar` apunta el lote en la tabla `discarded` (no en `decisions`: el dataset S.3 no se ensucia)
  y saca de `processed` los ficheros que ningún otro lote vivo cubre, para que vuelvan a proponerse.
  `apply` rechaza un lote descartado. El barrido nocturno y el resumen de las 8:00 no los cuentan.
- Instalación: `apply-decidir.sh` (copia previa y rollback en su cabecera).

**Verificado el 03-11** (primero sobre una copia del estado y los informes, después en real): `decidir`
con vetos, nombre con `/../` saneado, ítem inexistente y argumentos sin modo rechazados, lote descartado
rechazado por `decidir` y por `apply`, descartar dos veces rechazado. En real se descartaron los 3 restos
(`lote-20261028-014106`, modo clasificación, 9 ficheros liberados; `lote-20261029-115548`, truncado, 0
liberados porque se repitió en `lote-20261029-120413`; `lote-20261029-124442`, prueba, 1 liberado). Quedan
2 lotes pendientes reales; el barrido sigue saltándose hasta decidirlos (máximo 2).

## Decidir desde Hermes PERSONAL con código por Telegram (03-11-2026)

Decisión del usuario: decidir los lotes hablando con Hermes PERSONAL (modelo local), sin que los nombres
de fichero pasen por un modelo cloud ni por Telegram. Acciones nuevas del puente:

| Acción | Qué hace |
|---|---|
| `lotes` | estados y recuentos, sin nombres |
| `ver` | copia el `.md` del lote a `results/<id>/` para que Hermes lo enseñe |
| `proponer` | valida la decisión (`modo`, `solo`, `veto`, `nombres`), la simula con `decidir … simular`, guarda un **borrador** en `/var/lib/sip-gestor-entrada/borradores/` (fuera del volumen de Hermes) con el sha256 de un código de 6 cifras, y manda por Telegram el resumen en números y el código |
| `confirmar` | con el código correcto (un solo uso, 30 min, 3 intentos por borrador, bloqueo 24 h tras 10 fallos): `decidir … via=hermes` y `apply`; aviso del resultado por Telegram |

Hermes nunca ve el código: se lo da el usuario tras comprobar en Telegram que el resumen cuadra. Una
inyección que lleve a Hermes a proponer otra cosa no se aplica sin el código, y el resumen la delata.
Por Telegram solo viajan id del lote, recuentos, números de ítem y el código. La unidad del puente gana
`SupplementaryGroups=sip-notify` y la bandeja de avisos en `ReadWritePaths`. Instalación:
`apply-puente-decision.sh`. La skill `gestor-entrada` (perfiles `personal`, `default`, `sandbox`) explica
el flujo a Hermes.

**Verificado el 03-11:** prueba completa sobre copias del estado y de los informes, con el envoltorio de
filegate sustituido por `/bin/false` (sin renombres reales) y los avisos en una bandeja temporal:
`lotes`, `ver`, `proponer` inválido (modo, ítem inexistente) rechazado, aviso sin nombres, código erróneo
(intentos restantes), código correcto → decisión con `via: hermes` y `apply`, código reutilizado
rechazado, lote ya aplicado rechazado, borrador anulado tras 3 fallos. En real: unidad con escritura en
la bandeja; `lotes` y `proponer` inválido desde el contenedor de PERSONAL. **Sin verificar:** el primer
uso real del usuario (Hermes interpretando la decisión con el modelo local, el código en su móvil).

**Incidencia del primer uso (03-11, 19:07):** `lotes` y `ver` pedidos por Hermes fallaron con
`JSON inválido: PermissionError`. El terminal de Hermes usa `umask 077` y sus peticiones salían `0600`;
mis pruebas escribían con `echo` (umask 0007) y no lo vieron. Arreglo: ACL por defecto en `requests/`
(`u::rw,g::rw,o::-`; con ACL por defecto no se aplica el umask): con `umask 077` sale `0660` y el
puente responde `ok` (verificado). Incluido en `apply-puente-decision.sh`.
**No bastó:** la herramienta de escribir ficheros de Hermes crea con modo `0600` explícito, que anula el
ACL (19:16-19:18, mismo error), y PERSONAL no tiene terminal en sus sesiones (lo comprobó Hermes con un
subagente: solo herramientas de ficheros). **Arreglo final:** `sip-gestor-permisos.service`, oneshot
como `usuario` (uid 1000, el mismo usuario que Hermes: no gana acceso), requerido por el puente y ejecutado
antes que él: añade `g+r` a los `*.json` regulares de `requests/` cuyo dueño es él y cuyo grupo es
`sip-gestor`. Abre cada componente desde `${DOCKER_DATA}/hermes` con `O_NOFOLLOW` y usa `fchmod`; sin
red, sin sockets, sin `/home`, sin capacidades, solo escritura en `requests/`. Descartado: hacerlo como
root (carpeta controlada por Hermes). **Verificado:** petición con `0600` explícito desde el contenedor
→ `ok`; un enlace `requests/enlace.json` → fichero `0600` de `_gestor/` no se tocó (sigue `600`) y el
puente rechazó el enlace.
**Prueba con el agente real (19:40):** `hermes chat --oneshot` en `hermes-webui` con el perfil `personal`
(modelo local), pidiendo no mostrar nombres: `lotes` y `ver` → `ok`. Hallazgo: `informe` traía la ruta
del host (`${DOCKER_DATA}/...`), que Hermes no ve; corregido a `/workspace/_gestor/...` (también en
`scan`). Repetido: Hermes leyó el informe y respondió `FILAS=50; ABSTENCIONES=5` (coincide con el lote).

**Primer uso real del usuario (03-11, noche): no apto para 50 ítems.** Revisar uno a uno con Hermes
(`qwen3.8:27b`, contexto 32k en HALO, con razonamiento) se congeló hacia el mensaje 16; unas respuestas
tardaban 3 s y otras minutos (el contexto crece con cada ítem) y acabó en `Response remained truncated
after 4 continuation attempts`. Los dos lotes se decidieron en la consola con `decidir` (el usuario
permitió que Claude viera los nombres para este caso). **Pendiente:** más contexto en PERSONAL y que el
flujo de Hermes trabaje por bloques de 10 ítems.

## Revisión por bloques de 10 desde Hermes (04-11-2026)

Respuesta al primer uso real. En el puente:
- `ver` con `"bloque": N` escribe en `results/<id>/` un `.txt` con 10 ítems numerados (en lista, no en
  tabla) y devuelve `bloques` e `items`.
- `anotar` guarda la decisión de un bloque en `/var/lib/sip-gestor-entrada/borradores/<lote>.anotado.json`
  (fuera del volumen de Hermes). Rechaza números de otro bloque, y repetir un bloque lo sustituye.
- `proponer` con `"modo": "anotado"` exige todos los bloques. Junta los aprobados en `solo=` con sus
  nombres y sigue el flujo de siempre (código por Telegram y `confirmar`). Si `confirmar` sale bien,
  borra las anotaciones.

Dar nombre a un ítem lo aprueba, y las abstenciones sin nombre siguen sin aplicarse (lo hace `decidir`).
La skill indica a Hermes ir siempre por bloques. PERSONAL pasa además a `qwen3.8:27b-64k`
(`hermes/personal-64k.sh`), la misma etiqueta que CODING.

**Verificado:**
- `tests/test_sip_gestor_bloques.py`: 4 pruebas OK.
- `apply-bloques.sh` en Neo, con peticiones `0600` desde el contenedor: bloque 5 = ítems 41-50; un
  ítem de otro bloque se rechaza; `proponer` sin bloques se rechaza sin mandar código.
- Hermes real (`--oneshot`) con un lote sintético de 45 ítems y respuestas dadas en el mensaje: 5
  bloques anotados exactamente como se pidió, en **2 min 10 s** (36 llamadas a herramientas, sin
  cortes). Lote y anotaciones borrados después.

**Falta:** el uso real del usuario, con turnos de verdad.

## Primer uso real por bloques y fallo de `confirmar` (04-11-2026)

El usuario revisó `lote-20261104-031148` por bloques desde PERSONAL: 8 aprobados (todos con nombre
propio), 38 vetados, 4 abstenciones; código por Telegram y `confirmar` correctos. **Falló el `apply`**:
la unidad del puente tiene `NoNewPrivileges=true` y `sudo -n sip-gestor-filegate` no puede elevar, así
que los 8 renombres dieron error. Las pruebas del 03/04-11 confirmaban sobre un lote ya aplicado y nunca
llegaron a un renombre. Además el gestor guardaba el fallo como decisión «aprobado» y el lote salía como
«aplicado».

- **Corregido y desplegado:** un renombre fallido no deja decisión, cuenta como «con error», `apply`
  termina con 1 (el puente devuelve `ok: false`) y `lotes` dice «aplicado con errores»; un `apply`
  posterior lo reintenta (prueba `tests/test_sip_gestor_apply.py`). La skill explica «saltados» frente
  a «con error» y pide no reintentar.
- **Recuperado:** `apply` del lote desde la consola como `sip-gestor`, la decisión ya confirmada:
  8 renombrados, 42 saltados, 0 con error.
- **Decidido por el usuario (04-11) e instalado por él:** `sip-gestor-bridge.service` sin `NoNewPrivileges`
  (el clasificador del agente lo bloqueaba). **Verificado:** `lote-20261104-112531` revisado con Hermes y
  confirmado con el código; el puente aplicó solo 19 renombres, 0 con error.

## Duplicados y basura a cuarentena (03-11-2026)

`cuarentena-duplicados.py <lote.json> <simular|ejecutar> '<json {duplicado: original|null}>'`, como
`sip-gestor`. Para cada ítem comprueba que es fichero regular, no enlace, con el hash del lote, y que el
original que se queda sigue intacto con el mismo hash; luego `sip-gestor-filegate quarantine` (política
`gestor|quarantine-src|PARA`, sin cambios). Recuperable con `restore <uuid>` hasta la purga de 180 días.
Los duplicados se buscan agrupando por `hash` en el `.json` del lote. Después, vetar esos ítems en
`decidir`. Usado el 03-11: 12 ítems en `lote-20261029-120413` (7 duplicados + 5 de torrent) y 10 en
`lote-20261029-232339` (9 duplicados + un `~$…docx` de bloqueo de Word).

## Limitaciones conocidas

- Un ítem ya procesado **no se vuelve a proponer**, aunque se rechace o aunque
  se mejore el prompt: `processed` guarda ruta+hash. Para reintentar un fichero
  hay que borrar su fila de `processed` (o añadir un comando `reset`).
- Un renombre se hace con la extensión original; el resto de mayúsculas/espacios
  se normaliza a `_`.
- PDF **escaneado sin capa de texto** → abstención (no hay OCR). Si algún día
  hace falta, sería un paso aparte.
- Si dos ficheros del mismo directorio proponen el mismo nombre (duplicados),
  `apply` renombra uno y **salta** el otro (destino existente).
- El puente no notifica a Hermes: el agente debe leer `results/<id>.json` y
  esperar (un `scan` con el modelo frío puede tardar minutos; en la prueba con
  `max_items: 1` tardó ~5,5 min porque llama-swap cargó el tiny bajo demanda).

## Rollback

```bash
sudo systemctl disable --now sip-gestor-entrada.service 2>/dev/null
sudo rm -f /etc/systemd/system/sip-gestor-entrada.service /usr/local/bin/gestor-entrada.py
# deshacer renombres ya hechos: cuarentena por fichero (filegate) + restore
```

Puente Hermes (reversible por separado):

```bash
sudo systemctl disable --now sip-gestor-bridge.path
sudo rm -f /etc/systemd/system/sip-gestor-bridge.{path,service} /usr/local/bin/sip-gestor-request.py
sudo systemctl daemon-reload
# ACL de traversal (opcional; no afecta a los modos)
sudo setfacl -x u:sip-gestor ${DOCKER_DATA} ${DOCKER_DATA}/hermes ${DOCKER_DATA}/hermes/workspace
# perfil personal de vuelta a HALO
hermes config set terminal.backend ssh   # con HERMES_HOME del perfil personal
```
