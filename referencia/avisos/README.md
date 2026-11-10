# Avisos de tareas en segundo plano (PERSONAL → sip-gateway)

Decisión del usuario del 05-11: en lugar de subir el límite global de Hermes (420 s por herramienta,
`timeouts.tools.sequential_call`), las tareas largas se ejecutan en segundo plano y avisan al terminar.

## Flujo

1. `audio_transcribir` (plugin `sip-transcribir` 1.1) lanza la transcripción en un hilo propio y espera
   hasta 300 s (`SIP_TAREA_ESPERA`). Si acaba antes, devuelve el texto como siempre.
2. Si no ha acabado, devuelve `{"en_segundo_plano": true, "tarea": "<12 hex>"}` y el agente se lo dice
   al usuario y termina el turno. El estado vive en `/workspace/tareas/<id>.json`, con un latido cada
   60 s, para que la WebUI y la API sepan distinguir «en curso» de «interrumpida».
3. Al terminar, si existe `SIP_AVISOS_DIR` (solo en la API de PERSONAL), el plugin escribe
   `/avisos/<id>.json`, que contiene solo `{"v":1,"id","herramienta","estado"}`.
4. `sip-gateway` revisa `/avisos/p` cada ≤ 20 s. Lo que hace con cada fichero:
   - **lo borra siempre**;
   - **solo acepta exactamente ese formato**: id de 12 hex, herramienta de la lista, estado `ok|error`,
     ≤ 512 bytes, fichero normal y no enlace;
   - **acepta como mucho 12 avisos por hora y zona**;
   - **avisa al usuario** en el tema de la zona («⏰ … te paso el resultado»);
   - **encola para PERSONAL**, en la conversación actual del usuario, un mensaje del sistema que construye
     el propio gateway y que le pide recoger el resultado con `tarea_resultado(id)`.
5. `tarea_resultado(id)` también sirve si el usuario pregunta por la tarea, también desde la WebUI.

## Aislamiento

- **Buzón:** `/var/lib/sip-avisos/personal`, propiedad de `978:1000` con modo `1770`.
  - El gateway (978) es el dueño y borra.
  - La API (1000:1000) escribe por grupo.
  - El modo sticky impide que nadie más borre.
  - El grupo 1000 (`usuario`) no tiene otros miembros.
- **Nada de texto libre llega al gateway.** Nunca reenvía contenido del buzón: los mensajes que manda al
  usuario y a la zona son plantillas suyas.
- **Lo peor que puede hacer una zona comprometida** es provocar hasta 12 turnos por hora de sí misma y
  12 mensajes fijos al usuario.
- **La WebUI no monta el buzón.** Sus tareas no avisan por Telegram; se recogen con `tarea_resultado`.

## Despliegue y vuelta atrás

`sudo sh sip-config/avisos/apply.sh` en Neo, desde el checkout actualizado y sin turnos en curso en el
gateway. Deja una copia previa y `rollback.sh` en `/root/sip-agent-backups/<fecha>/avisos/`.
