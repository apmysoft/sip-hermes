# Inventario de identidades

> Plantilla. Qué usuario, token o clave usa cada pieza y con qué alcance. Principio: **el agente tiene cuentas
> propias con permisos mínimos, nunca las tuyas.** Los valores no se apuntan aquí; la rotación va en `ROTACION.md`.

| Identidad | Equipo | Tipo | Alcance | Credencial | Rotación |
|---|---|---|---|---|---|
| `hermes-personal` (UID:GID) | servidor | Usuario de zona (contenedor) | Lee PARA (ACL solo lectura); escribe por filegate; sin Internet | Token filegate `personal` | Al cierre |
| `hermes-coding` | servidor | Usuario de zona | Worker por SSH; nada de PARA | Clave SSH del worker, clave virtual LiteLLM | Al cierre |
| `hermes-research` | servidor | Usuario de zona | Internet filtrado; deja notas en `00_entrada` por filegate | Clave virtual LiteLLM con presupuesto | Al cierre |
| `filegate` | servidor | Usuario de sistema sin login | Única escritura en PARA; nunca borra | — | n/a |
| `sip-wol` | servidor | Usuario de sistema sin login | Enviar WOL al equipo GPU (con tope por hora) | — | n/a |
| `sip-notify` | servidor | Usuario de sistema sin login | Enviar avisos a Telegram desde una carpeta de salida | Token del bot | Si se ve |
| `sip-gateway` | servidor | UID de contenedor | Enrutar Telegram → zonas, sin LLM | Token del bot, claves de las API de zona | Si se ve |
| `hermes-worker` | equipo GPU | Usuario sin sudo, shell forzada | Ejecutar en su workspace con bubblewrap, sin red | `authorized_keys` con orden forzada | Al cierre |
| `sip-llm` | equipo GPU | Usuario de sistema sin login | Servidor de modelos (llama-swap) | — | n/a |
| Cuenta de correo del agente | nube | Cuenta propia del agente | Altas de servicios para el agente; sin datos personales | En tu gestor de contraseñas | Anual |
