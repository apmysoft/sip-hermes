# Fase 6 — LiteLLM + Postgres dedicado (SIP)

Proxy de modelos de Hermes (H.4/Fase 6). Alcance actual: infraestructura
y breaker de cuota / rate-limits por clave; sin proveedores cloud todavía.

## Diseño (v2.4)

- Claves reales solo en el proxy; los agentes usan claves dummy.
- Rate-limits/budgets por clave virtual **requieren** la DB dedicada.
- Proveedores SOLO por `config.yaml` + env. **Admin UI deshabilitada**
  (`DISABLE_ADMIN_UI=true` + `disable_env_credential_login`).
- La DB solo contiene metadatos de gasto; la configuración de proveedores
  no se hace nunca por UI.
- Solo tailnet: `${NEO_TAILNET_IP}:4000` (misma política que la WebUI).
- Volumen DB en `${DOCKER_DATA}` (data-root de Docker); logically NVMe sólo
  compose/config/env (KB) y el env file.
- Recursos: db `mem_limit 384m` y `shared_buffers=64MB`; proxy `mem_limit 1g`.

## Secretos (solo servidor, fuera del repo)

- `/root/sip-litellm.env` (0600 root:root) — NO versionable. Contenido:
  `LITELLM_MASTER_KEY` (sk-sip-... — generada aleatoria), `POSTGRES_PASSWORD`,
  `LITELLM_DB_URL` (`postgresql://litellm:<pass>@litellm-db:5432/litellm`).
- Generación (Neo, como root):
  ```bash
  install -d -m 700 /root 2>/dev/null # ya existe
  MASTER="sk-sip-master-$(openssl rand -hex 24)"
  DBPASS="$(openssl rand -hex 16)"
  cat > /root/sip-litellm.env <<EOF
  LITELLM_MASTER_KEY=$MASTER
  POSTGRES_PASSWORD=$DBPASS
  LITELLM_DB_URL=postgresql://litellm:$DBPASS@litellm-db:5432/litellm
  EOF
  chmod 600 /root/sip-litellm.env
  ```
- Registrar la CREACIÓN en `ROTACION.md` (nombre y ubicación, nunca el valor).

## Despliegue (Neo)

```bash
sudo -n install -d -m 755 /opt/sip-litellm ${DOCKER_DATA}/docker_root/volumes/sip-litellm
sudo -n cp sip-config/litellm/docker-compose.yml /opt/sip-litellm/
sudo -n cp sip-config/litellm/litellm.config.yaml /opt/sip-litellm/
cd /opt/sip-litellm && sudo -n docker compose up -d
```

## Verificación (hecha el 31-10-2026, en Neo)

1. `docker compose ps` → `sip-litellm` y `sip-litellm-db` ambos **healthy**.
   El data-root de Docker es `${DOCKER_DATA}/docker_root` (`docker info`):
   las imágenes y el volumen de la DB viven en el disco de datos.
2. `curl http://${NEO_TAILNET_IP}:4000/health/liveliness` → `I'm alive!`.
3. Petición real completada (`openai/gpt-oss:20b` passthrough a
   Ollama/HALO) con la master key → respuesta del modelo; el gasto quedó
   registrado en la DB (`LiteLLM_SpendLogs`, 8 filas tras las pruebas).
   VRAM liberada después.
4. **Rate-limit por clave dummy verificado**: clave con `rpm_limit:1`
   (`/key/generate`) → 1.ª petición `200`, 2.ª inmediata **`429 Rate limit
   exceeded · Current limit: 1`**. El campo correcto de la API es
   `rpm_limit` (ojo: `rpm` se ignora y la clave se crea sin límite).
5. **UI sin vía de entrada** (regla v2.4): `DISABLE_ADMIN_UI` en el env +
   `disable_env_credential_login` en config → `POST /v2/login` con la
   master key como password → **401 Invalid credentials** (es rechazo por
   diseño: sin usuarios en DB no hay login posible). Proveedores: solo
   config/env.
6. Clave de prueba purgada: tabla de claves vacía al cierre (`0 rows`).

Notas de despliegue que se topetaron y quedaron resueltas:
- `cap_drop ALL` rompe el entrypoint de Postgres → `cap_add` mínima
  (CHOWN/FOWNER/SETUID/SETGID/DAC_READ_SEARCH) en `litellm-db`.
- La imagen LiteLLM no trae `curl`: el healthcheck usa el `python3` del
  venv del contenedor.

## Backup / SQL

- La DB es infraestructura: copia diaria cifrada con age en
  `/var/backups/sip-litellm/` (timer `sip-litellm-backup.timer`, 14 copias,
  artefactos e instalación en `backup/`). Restauración descrita en el script y
  probada el 01-11 en un Postgres desechable: 2 claves y 62 registros, igual que
  la DB real. Kopia global se abarcará en Fase 10.
- Cambios de provider: editar litellm.config.yaml + `docker compose restart`
  (la config se recarga en reinicio; nunca por UI).

## Rollback

- `docker compose down` (sin `-v`: mantiene el volumen de datos).
- Para eliminarlo todo: `docker compose down -v` + borrar
  /opt/sip-litellm + /root/sip-litellm.env (requiere confirmación;
  registrada la rotación de la master key).

## Bloque B — perfiles cableados (verificado el 01-11-2026, en Neo)

| Perfil | Vía | Clave | Límites | Modelos permitidos |
|---|---|---|---|---|
| `coding` | proxy | `sk-coding` | 10 rpm, 1 $/día | los 4 locales |
| `research` | proxy | `sk-research` | 10 rpm, 1 $/día | los locales salvo el coder |
| `personal` | **directo a Ollama** | ninguna | — | v2.4: solo local, nunca proxy |
| `default`, `system`, `sandbox` | directo a Ollama | ninguna | — | sin cambios |

- URL interna: `http://sip-litellm:4000/v1`. Desde el contenedor, la IP tailnet
  `${NEO_TAILNET_IP}:4000` da timeout: no usarla en perfiles.
- Clave en el `.env` del perfil (`LITELLM_API_KEY`, 0600) con
  `providers.litellm.key_env`. Valores: `/root/sip-litellm-keys.json` (0600 root).
- Para cablear otro perfil: `wire-profile.py <config.yaml>` y añadir la variable.
- Crear claves con `rpm_limit` y `max_budget` + `budget_duration` en
  `/key/generate`; los límites viven en la DB, no en este repo.

**03-11-2026 (O7):** esta tabla es de los perfiles del contenedor único, antes de las zonas de la
Fase 7. Hoy: CODING (`hermes-coding*`) usa `sk-coding-20261103` (rotada; la de su `.env`) y RESEARCH
`sk-research-cloud`. `sk-research` está revocada y el perfil `research` de PERSONAL, archivado.
`sip-litellm` ya no está en la red `sip`: PERSONAL no llega al proxy (`operacion/o7/remedio-personal.sh`).

**Comprobado:** petición real por perfil con gasto atribuido a su clave; worker
kanban de `coding` por `sk-coding`; clave inválida → `401`; modelo no permitido →
`403`; `sk-research` → 10 × `200` y la 11.ª `429`; primario en `429` → Hermes
responde con el fallback directo `qwen3.8:27b`; prompts de 10k y 22k tokens sin
truncar, igual que en directo; `personal` no genera registros en el proxy; claves
ausentes de los logs del proxy y del volumen Hermes, salvo su `.env`.

**Tras el arranque no planificado del 01-11:** `coding` responde por `sk-coding`,
`personal` sigue sin registros en el proxy y claves y límites se conservan.

**Sin comprobar:** selección de `coding`/`research` en la WebUI; `research` tras ese
arranque; prompts por encima del contexto real (32768).

**Límite `tpm` de `sk-coding`:** lo dejó la sesión del 31-10, v2.4 no lo pide y daba
`429 Limit type: tokens` intermitentes. Eliminado el 01-11 con permiso del usuario.

**Rollback:** restaurar `perfiles-config-pre.tgz` de
`/root/sip-agent-backups/2026-11-01/fase6b/` y quitar `LITELLM_API_KEY` de los
`.env`. La DB previa está en `litellm-db-pre.sql.gz`, en el mismo directorio.

## Pendiente (con el usuario)

- Claves cloud (Bloque C): `GEMINI_API_KEY` y `KIMI_API_KEY`, desplegadas. Las guarda el usuario con `sudo bash set-provider-key.sh <NOMBRE>`. Recomendación y decisión de
  despliegue en `sip-config/research/README.md`. Tras cambiar el env hay que recrear el
  contenedor (`docker compose up -d`): `restart` no relee `env_file`.
