# Canal de avisos del host a Telegram (02-11)

Avisos deterministas, sin LLM: cualquier servicio del host deja un fichero de texto en
`/var/lib/sip-notify/outbox` y `sip-notify.path` lanza `sip-notify.service`, que lo envía al UID
permitido y lo retira. No es el gateway de Hermes (Fase 7): no lee mensajes ni ejecuta nada.

- **Usuario:** `sip-notify`, sin login. Bandeja `root:sip-notify 2770`; quien escriba debe estar en el
  grupo `sip-notify` (hoy, `sip-wol`).
- **Secreto:** `/root/sip-telegram.env` (0600 root), entregado por `LoadCredential`; el usuario no lo
  puede leer fuera del servicio. Se guarda con `sip-config/gateway/set-telegram.sh`.
- **Red de la unidad:** solo `localhost` (resolvedor) y los rangos publicados de Telegram. Sin cambios en
  nftables.
- **Tope:** 12 avisos por hora; el resto se descarta con línea `<4>` en el journal.
- **Temporales:** el escritor crea `.<nombre>.tmp` dentro de la bandeja y renombra. Los `ReadWritePaths`
  son montajes distintos y un rename desde otro directorio da `EXDEV`. Los temporales huérfanos de más
  de 60 s se borran.

## Consumidores

| Origen | Cuándo | Texto |
|---|---|---|
| `sip-wol-halo` | WOL acaba en `timeout` o `rate_limited` | Enciende el enchufe de HALO en la app Tapo |
| `sip-energia` (05-11) | HALO se apaga por inactividad o a petición (`energia-`, «Avisos»); código para apagar a petición (`wol-apagar-`, «Peticiones») | Qué seguía abierto y la nota del enchufe Tapo y el WOL |

## Verificado el 02-11-2026

- Aviso directo en la bandeja: enviado y recibido por el usuario (confirmado el 02-11).
- WOL de punta a punta con `timeout` forzado (sonda a puerto cerrado, espera de 5 s, estado de prueba
  para no gastar cupo): aviso enviado y recibido. El primer intento falló con `EXDEV`; corregido.
- Unidad real del WOL tras el cambio: `already_awake`, sin aviso.

## Sin hacer

- Control del enchufe Tapo: aplazado por el usuario; de momento solo el aviso.

## Temas (04-11-2026)

Los avisos van a temas del chat privado: «Peticiones» si el fichero empieza por `gestor-`, `memoria-`,
`wol-` o `claude-` (esperan algo del usuario) y «Avisos» el resto. Los ids se guardan en
`/var/lib/sip-notify-state/temas.json` y los temas se crean la primera vez. Si un tema da error (p. ej.
borrado), el aviso sale sin tema y se borra el fichero para recrearlos. **Verificado:** temas creados y
dos avisos de prueba (`alertas-` y `claude-`) enviados sin recurrir al envío sin tema; el usuario los ve
en su tema. Desde el 04-11 por la tarde ya no crea «Conversaciones»: cada zona tiene su tema, que crea
el gateway.

## Instalación y rollback

`sudo sh apply.sh` en Neo, con `../wol` al lado. Rollback en su cabecera; copia previa en
`/root/sip-agent-backups/2026-11-02/notify/`.
