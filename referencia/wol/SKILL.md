---
name: halo-wake
description: Despierta HALO cuando no responde y hace falta un modelo pesado. Úsala solo si una petición al modelo falla por HALO inaccesible o el usuario pide despertarlo.
---
# Despertar HALO

Sin herramientas especiales: el servicio del host hace el envío.

1. Crea `/workspace/_wol/requests/<fecha>-<slug>.json` con `{}`. El contenido se ignora.
2. Espera hasta 3 minutos y lee `/workspace/_wol/results/<fecha>-<slug>.json`.
3. Actúa según `status`:
   - `already_awake` o `awake`: HALO disponible; continúa.
   - `rate_limited`: se alcanzó el tope de 5 envíos por hora. No insistas; informa.
   - `timeout`: se envió, pero HALO no respondió. Informa y deja la tarea en espera.

**Nunca** uses un modelo cloud porque HALO no responda: las tareas personales se
encolan o se informa al usuario (fail-closed, v2.4).
