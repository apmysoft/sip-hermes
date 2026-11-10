# Registro de credenciales para rotación

> Plantilla. Cada credencial, clave o secreto que se crea, se toca o **se ve** durante la implantación tiene una fila.
> **Nunca el valor:** solo nombre, equipo y ubicación. Al cerrar la ventana de trabajo con el agente, recorre la
> columna «Acción al cierre».

| Fecha | Nombre | Equipo | Ubicación (modo y propietario) | Uso | Acción al cierre |
|---|---|---|---|---|---|
| AAAA-MM-DD | Sudo temporal del agente | servidor | `/etc/sudoers.d/90-agent-temp` (0440 root) | Implantación asistida | Caduca solo; comprobar que se borró |
| AAAA-MM-DD | Tokens de filegate por zona | servidor | `/etc/filegate/tokens/*.tok` (0440 root:filegate) | Escritura en PARA por zona | Rotar |
| AAAA-MM-DD | Clave maestra de LiteLLM | servidor | `/root/litellm.env` (0600 root) | Proxy de modelos en la nube | Rotar |
| AAAA-MM-DD | Clave virtual de una zona | servidor | `.env` de la zona (0600) + hash en la base de LiteLLM | Límites y presupuesto por zona | Rotar si se vio |
| AAAA-MM-DD | Token del bot de Telegram | servidor | fichero de secretos del gateway (0400) | Gateway y avisos | Rotar si se vio |
| AAAA-MM-DD | Frase de paso de las copias cifradas (age) | servidor + gestor de contraseñas | `/root/backup.pass` (0400 root) | Copias del estado | Conservar; probar restauración |
| AAAA-MM-DD | Clave SSH del worker | servidor → equipo GPU | volumen de la zona CODING (0600) | Orden forzada al worker | Rotar |

## Vistas por error

Si un valor apareció en una salida (terminal, registro, conversación con un agente), anótalo aquí con la fecha y
rótalo, aunque parezca inofensivo.

| Fecha | Nombre | Dónde apareció | Rotada |
|---|---|---|---|
| | | | |
