# Runbook M.13: rotación de emergencia de credenciales

Cuándo: sospecha de fuga (O7 con un hallazgo vivo, un log con una clave o un equipo comprometido), robo
del móvil o pérdida de un equipo o disco. El inventario de qué existe y dónde está es `ROTACION.md`
(nombres y rutas, nunca valores). Orden de v2.4: **revocar en el proveedor → sustituir en LiteLLM →
reiniciar agentes → verificar las dummies**.

## 1. Cortar

| Caso | Primer paso |
| --- | --- |
| Robo o pérdida del móvil | Desde otro dispositivo: Telegram → Ajustes → Dispositivos → cerrar la sesión. Corta `/r` y `/c` |
| Neo, HALO o un disco robados | Consola de Tailscale: quitar los equipos afectados. Los discos de datos llevan LUKS (si ya está aplicado; ver 99-NOTAS) |
| Clave cloud filtrada | Revocarla en la consola del proveedor (Google AI Studio, Kimi Code) antes que nada |
| Incidente en curso | `sip-stop` (modo pánico, M.15): para las zonas y deja el gateway solo para avisar |

## 2. Rotar, por tipo

| Credencial (ver `ROTACION.md`) | Cómo se rota | Verificación |
| --- | --- | --- |
| Claves cloud (`GEMINI_API_KEY`, `KIMI_API_KEY`) | Nueva en el proveedor; `sip-config/litellm/set-provider-key.sh` (no la muestra) | Llamada por `sk-research-cloud`; la antigua da `401` en el proveedor |
| `LITELLM_MASTER_KEY` | Nuevo valor en `/root/sip-litellm.env`; recrear `sip-litellm` | `/key/info` con la nueva; la antigua da `401` |
| Claves virtuales (`sk-coding`, `sk-research`, `sk-research-cloud`) | `/key/regenerate` (o borrar y crear con los mismos límites); actualizar el `.env` de cada zona; reiniciar su contenedor | La antigua da `401`; turno real por zona |
| `API_SERVER_KEY` de RESEARCH y CODING | Regenerar el fichero de `/root/`; recrear la API de la zona; relanzar `sip-config/gateway/apply-gateway.sh` | `/r` y `/c` desde Telegram |
| `TELEGRAM_BOT_TOKEN` | BotFather → `/revoke`; `sip-config/gateway/set-telegram.sh`; actualizar `/root/sip-telegram.env` (avisos) | `/r` responde; `sip-notify` envía |
| Tokens de filegate | Nuevo `.tok` por zona en `/etc/filegate/tokens/` (root:filegate 0440) escrito sobre el mismo fichero, no con `mv`: `hermes-research` monta `research.tok` por bind y el bind sigue al inodo antiguo | Sonda de cada zona; el antiguo da `ERROR token invalido` |
| Claves SSH (`id_ed25519_halo_worker`, `id_ed25519_sandbox_runner`, HALO → Neo) | `ssh-keygen` nueva; sustituir en `authorized_keys` del destino; borrar la antigua del destino | Turno de CODING con terminal; `sip-traspaso` (usa la de `halo_worker`) |
| Contraseñas de las WebUI | Nuevo valor en el `.env` del contenedor; recrear; guardarla en Vaultwarden | Login |
| Passphrase de backups (age) | Nueva en `/root/sip-hermes-backup.pass`; las copias antiguas siguen con la anterior: guardarla aparte hasta que caduquen | Ciclo cifrar → descifrar |
| `POSTGRES_PASSWORD` (DB de LiteLLM) | `ALTER USER` en `sip-litellm-db` y el `.env`; recrear `sip-litellm` | `/health/readiness` |

## 3. Comprobar

1. O7 (`sip-config/operacion/README.md`): ninguna clave viva en `.hermes`, logs de LiteLLM ni logs de
   Docker.
2. Las zonas solo tienen dummies o claves virtuales con límites: `sk-coding` y `sk-research` sin cloud.
3. Anotar en `ROTACION.md` cada credencial rotada (fecha, nombre y ubicación) y en 99-NOTAS el incidente.
