# Servicio WOL de HALO (Fase 5, v2.4 M.11)

Único emisor de magic packets hacia HALO. Corre en el host de Neo, fuera de los
contenedores, con el usuario `sip-wol` y sin privilegios.

## Flujo

1. Hermes (perfil `personal`, skill `halo-wake`) crea un fichero en
   `/workspace/_wol/requests/`. El contenido se ignora.
2. `sip-wol-halo.path` lanza `sip-wol-halo.service`, que retira la petición y deja
   el estado en `/workspace/_wol/results/<id>.json`.

| Estado | Significado |
|---|---|
| `already_awake` | HALO responde en `:11434`; no se envía nada ni se gasta cupo |
| `awake` | Se envió y HALO respondió antes de 180 s |
| `timeout` | Se envió y HALO no respondió a tiempo |
| `rate_limited` | Tope de 5 envíos por hora; línea de alerta en el journal |

MAC, broadcast y tope están fijos en el script. La red de la unidad solo admite
`${HALO_TAILNET_IP}` (sonda) y `${LAN_BROADCAST}` (envío). Sin cambios en nftables.

## Verificado el 01-11-2026

- Desde el contenedor: `already_awake`, sin paquete enviado.
- Bajo las mismas restricciones de red y con sonda a un puerto cerrado: 6 peticiones
  → 5 envíos y 1 `rate_limited`. `tcpdump` en HALO recibió esos 5 paquetes con la
  MAC correcta, y uno manual añadido para cerrar la captura.
- Aceptación: Hermes `personal` invocó la skill y devolvió `already_awake`.

## Despertar automático sin LLM: plugin `sip-halo-wake` (02-11)

`halo-wake` necesita un modelo, y todos los de Hermes viven en HALO: con HALO apagado,
el agente no puede invocarla. Por eso el disparador es el plugin `plugin/sip-halo-wake`,
en el hook `pre_llm_call`, que corre antes de cada turno y sin LLM:

- Si el modelo del turno es local (etiqueta Ollama `nombre:tag`) y `${HALO_TAILNET_IP}:11434`
  no responde, crea una petición en `requests/` y espera el resultado hasta 210 s.
- Un cerrojo en `/tmp` hace que varias sesiones esperen un único despertar.
- Corre en el proceso de Hermes y no en el terminal del agente, así que también sirve en los
  perfiles con backend `ssh`.
- Si el resultado es `timeout` o `rate_limited`, añade al turno un aviso para que el agente
  informe y no use cloud en tareas personales.
- La sonda se puede redirigir con `SIP_HALO_PROBE_PORT` para las pruebas.

Instalado en el perfil raíz y en los 5 perfiles de `hermes-webui` con `plugin/apply-plugin.sh`
(copia previa en `/root/sip-agent-backups/2026-11-02/halo-wake/`, rollback en su cabecera).
`hermes-research` no lo lleva: no monta `/workspace/_wol`, y su modelo principal es cloud.

El tiny de Neo no hace falta para despertar. Usarlo como respuesta provisional mientras HALO
arranca exigiría abrir `llama-swap` más allá de loopback; es una decisión de exposición aparte.

## Prueba de despertar real (la hace el usuario)

Con HALO apagado limpiamente, desde Neo:

```bash
sudo docker exec -u 1000 hermes-webui sh -c 'echo {} > /workspace/_wol/requests/prueba.json'
sudo docker exec -u 1000 hermes-webui sh -c 'sleep 180; cat /workspace/_wol/results/prueba.json'
```

Debe devolver `awake`; también vale comprobar que HALO arranca antes de esos 3 minutos.

## Plugin verificado el 02-11-2026

- Función aislada con la sonda en un puerto cerrado: petición creada, el servicio contesta
  `already_awake` (sin envío), resultado leído y borrado; modelo cloud, sin acción.
- Turnos reales `hermes -p personal -z` y `hermes -p coding -z` con la sonda forzada: el hook
  se disparó en ambos (dos peticiones en el journal) y respondieron `OK`.
- Sin observar en un turno lanzado desde la WebUI, aunque usa los mismos perfiles.

## Sin verificar

- **Despertar real con HALO apagado por este servicio.** Requiere al usuario, porque
  apagar HALO corta la sesión del agente. El WOL de Neo a HALO se verificó en
  Fase 0 con `wakeonlan`.
- La skill solo funciona en `personal`: con backend `ssh`, `/workspace` es el de HALO.
- ~~La línea de alerta solo queda en el journal~~: desde el 02-11, `timeout` y `rate_limited` avisan
  por Telegram con `sip-config/notify/` para encender el enchufe en Tapo (verificado con `timeout` forzado).
- **No hay cola de tareas pesadas:** el servicio despierta HALO, pero reanudar el
  trabajo sigue dependiendo de quien lo pidió.

## Instalación y rollback

`sudo sh apply.sh` en Neo, con los ficheros junto al script. Rollback en su cabecera.
Skill: `SKILL.md`, instalada como `skills/halo-wake` en el árbol global y en los perfiles.

## Modo ausencia (03-11)

Con la marca `/var/lib/sip-ausencia/activa` (la crea `sip-ausencia on`, `sip-config/operacion/ausencia/`),
las peticiones del plugin (prefijo `plugin-`) reciben `ausencia` sin envío; las explícitas de la skill se
atienden igual. Verificado con HALO despierto (`ausencia` y `already_awake`).
