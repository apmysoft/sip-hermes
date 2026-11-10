# Alertas de operación (v2.4 M.12)

Estado a 03-11-2026: **desplegado y verificado** en Neo (`sip-alertas.timer`, cada hora).

Deterministas, sin LLM ni contenido personal. Avisan por la bandeja de `sip-notify` solo cuando una alerta
aparece o sube de nivel; la recuerdan como mucho una vez al día y avisan cuando se resuelve. Estado en
`/var/lib/sip-alertas/estado.json`. Prueba sin avisar: `sudo python3 -I /usr/local/sbin/sip-alertas.py --dry-run`.

| Alerta | Fuente | Umbral |
| --- | --- | --- |
| Disco | `statvfs` (como `df`) de `/`, `Almacenamiento`, `DockerData`, `Almacen_extra`, `Backup_Boveda`, `cold` si está montado | 80 % aviso, 90 % crítico |
| RAM | `/proc/meminfo` | 80 / 90 % |
| Egresos de PERSONAL | journal del kernel, `sip-drop-sip` con origen `hermes-webui` | 20 paquetes/h |
| Cuarentena | `${STAGING_ROOT}/_cuarentena` | 100 entradas o 1 GiB |
| WOL | `/var/lib/sip-wol/sent.log` | 3 envíos/h (el servicio corta en 5 y ya avisa) |
| Cuota cloud | logs de `sip-litellm` (429) y presupuestos de las claves | 10 errores/h; 80 % del presupuesto |
| Logins fallidos | logs de las dos WebUI (`/api/auth/login` 401/429) y de Vaultwarden | 5/h |
| SQLite (S.12, 04-11) | logs de las 4 zonas («database is locked») y tamaño de `state.db-wal` en sus volúmenes | 1 bloqueo/h; WAL de 256 MiB |
| Tiny de Neo (06-11) | registro de `llama-swap` de Neo en 24 h (`status=500` o arranque fallido); pasiva, sin cargar el modelo | 1 petición con error (AVISO; se resuelve tras 24 h limpias) |

Solo cuenta los egresos de `hermes-webui`: Vaultwarden comparte la red `sip` y sus descargas de iconos
también se cortan (224 paquetes en 1 h el 03-11, al usarlo el usuario), pero no son de PERSONAL.

## Verificado el 03-11-2026

- Simulación: todas las fuentes leídas; disco de `${PARA_ROOT}` corregido al criterio de `df` (95 %,
  no 90 %: sin los bloques reservados a root).
- Ejecución real bajo systemd: aviso `CRÍTICO disco ${PARA_ROOT}: 95 %` enviado; la segunda
  ejecución, `sin cambios`.

Instalación: `apply.sh` (rollback en su cabecera).
