# Estado actual

> Plantilla. Una foto concisa de lo que **está** funcionando, no un diario (para eso están las notas). Actualízala
> al cerrar cada bloque y separa siempre lo verificado de lo que solo está desplegado o diseñado.

Última actualización: AAAA-MM-DD · Fase: _N (nombre)_

## Progreso

_X %_ del alcance del documento de arquitectura, implantado **y verificado**. Justificación breve y principales
pendientes.

## Desplegado y verificado

### Servidor

| Pieza | Estado | Cómo se verificó |
|---|---|---|
| Zona PERSONAL | activa | O1 y O5 en verde (fecha) |
| filegate | activo | `rm` directo falla con EPERM; cuarentena 180 días |
| … | | |

### Equipo con GPU

| Pieza | Estado | Cómo se verificó |
|---|---|---|
| llama-swap (bind a la VPN) | activo | inalcanzable desde la LAN |
| … | | |

### Red y seguridad

- Redes Docker y nftables por zona: …
- ACL de la VPN: …

## Desplegado sin verificar del todo

- …

## Pendiente

- …

## Problemas conocidos

- …

## Ventana del agente

- Sudo temporal hasta: AAAA-MM-DD
- Al cerrar: rotar lo apuntado en `ROTACION.md`, retirar privilegios, borrar copias con valores.
