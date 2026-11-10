# Fase 7 — Gateway y canales: propuesta sin desplegar

Estado a 02-11-2026. **Verificado:** una zona puede servir como API (`hermes gateway run` con
`API_SERVER_*`, en un contenedor desechable de `research`): `200` con clave, `401` con clave errónea y
respuesta real del modelo. Solo probado en local dentro del contenedor. `nftables-sip.candidate.nft`
solo ha pasado `nft -c`. **Sin probar:** todo lo demás de este documento.

## Qué pide v2.4

Telegram con allowlist por UID, sin grupos ni entrada de P1, y confirmaciones destructivas con TOTP.
Dashboard solo por tailnet. El gateway monta solo su propio estado, sin PARA, terminal ni claves cloud,
y enruta llamando a cada zona como servicio, con política determinista: el LLM no decide fronteras.

## Diseño propuesto

| Pieza | Diseño |
|---|---|
| `hermes-gateway` | Contenedor propio (UID propio, `read_only`, sin capacidades), con token y allowlist en su `.env` |
| Red `gateway` | `10.21.0.0/24`: solo Telegram por 443 y DNS |
| Enlaces a zonas | Una red Docker `internal` por zona. La zona expone su API solo ahí, con clave propia |
| Enrutado | Plugin con el hook `pre_gateway_dispatch`, sin LLM: `/r` RESEARCH, `/c` CODING y, por defecto, PERSONAL |
| TOTP | Hermes no trae TOTP para confirmar acciones en el gateway. Hay que construirlo o aplazar las acciones destructivas por Telegram |

## Límite actual

PERSONAL y CODING viven en el contenedor compartido `hermes-webui`, con el `.env` de `coding` y
`research` al alcance de `personal`. Si Telegram entra por ahí, un mensaje de RESEARCH y uno personal
comparten proceso, lo que v2.4 prohíbe. Separarlos afecta a la WebUI y al tablero kanban, que es una
base única entre perfiles.

## Decisiones del usuario

1. **Separación de zonas. Aceptada (02-11):** primero RESEARCH por Telegram, ya aislado; después sacar
   CODING, porque también le permite usar cloud; y dejar PERSONAL en la WebUI hasta verlo funcionar.
2. **Comandos o modelo. Aceptada (02-11):** comandos deterministas (`/r`, `/c`), con zona recordada
   hasta el siguiente comando y la zona indicada en cada respuesta. Un modelo puede sugerir zona, nunca
   decidirla.
3. **Firewall.** Aplicar el candidato de este directorio, como el anterior.
4. **Datos de Telegram.** Crear el bot con `@BotFather`, averiguar tu UID con `@userinfobot` y guardar
   ambos en Neo, nunca en el chat. En curso, guiado paso a paso.
5. **TOTP. Aceptada (02-11):** nada destructivo por Telegram en esta fase; TOTP solo cuando haga falta.

## Desplegado el 02-11: `sip-gateway` con RESEARCH

Decisión del usuario: enrutador propio. Piezas: `sip_gateway.py`, `docker-compose.yml`,
`apply-gateway.sh`; RESEARCH expone su API con `../research/apply-api.sh`.

**Verificado:**
- Firewall aplicado por el usuario: 17/17 PASS, reversión cancelada; vigente = candidato.
- API de RESEARCH en `10.22.0.10:8642`: herramientas de `api_server` = `browser`, `entrada` (por defecto
  traería `terminal`, `file`, `code_execution`...); `401` sin clave o con clave mala, `200` con la buena;
  cerrada desde la red `research`; conversación de dos turnos con memoria por nombre.
- Lógica de enrutado con Telegram simulado: zona recordada, `/nueva`, CODING no conectado, otros UID y
  grupos descartados, mensajes sin texto rechazados.
- Contenedor: UID 978, solo lectura, alcanza solo la API de RESEARCH y Telegram.

**Verificado por el usuario (02-11):** `/ayuda`, `/r`, seguimiento sin comando con memoria y `/c` (no conectado) desde el móvil. Respuestas en 9 s y 2 s con `gemini-3.5-flash-lite` (cloud vía LiteLLM, `sk-research-cloud`); unas 3-4 peticiones de cupo por mensaje.

**Aviso de Hermes aceptado:** la API advierte de terminal local sin sandbox; no aplica porque
`api_server` no tiene `terminal` ni `file`. Cron de Hermes corre en RESEARCH sin la herramienta `cronjob`.

## Propuesta del 02-11: enrutador propio en lugar del gateway de Hermes (aceptada)

`pre_gateway_dispatch` es síncrono: reenviar a una zona y esperar minutos bloquearía el gateway, o
exigiría hilos y detalles internos que cambian en v0.22. La API de zona ya guarda la conversación por
nombre (Responses API, `conversation`). Propuesta: `sip-gateway`, un programa pequeño propio (Python sin
dependencias, long polling de Telegram) que:

- solo acepta el UID permitido, sin grupos;
- enruta por comando (`/r`, `/c`), recuerda la zona y la indica en cada respuesta, sin LLM;
- llama a la API de la zona por su red `internal` (`gw-research`, 10.22.0.0/24) con clave propia;
- no tiene modelo, terminal, PARA ni claves cloud; solo su estado y el token del bot.

Se pierde lo que trae el gateway de Hermes: adjuntos, voz, streaming y botones de aprobación. Para
RESEARCH no hacen falta al principio. Pedido del usuario a encajar aquí: **separar por categorías**
avisos de sistema, peticiones y conversaciones. **Hecho el 04-11** con temas en el chat privado (el
bot ya tiene `has_topics_enabled: True`). `sip-notify` crea los temas «Avisos» y «Peticiones».
Desde la tarde del 04-11 (pedido del usuario) cada zona tiene su tema: el gateway crea «RESEARCH» y
«CODING» la primera vez (ids en `state.json`). Lo escrito en el tema de una zona va a esa zona sin
comando, y la respuesta sale siempre en el tema de la zona, aunque el comando se escriba en otro sitio.
Si un tema se borra, la respuesta sale en el general y el tema se recrea en el siguiente mensaje. Cada
zona tiene su propia cola, así que una respuesta lenta de RESEARCH no retiene a CODING. El script del
contenedor está en `~/sip-fase7-gateway/`; copias en `/root/sip-agent-backups/2026-11-04/telegram-temas/`
y `…/temas-zona/`. **Verificado:** el usuario escribió en los dos temas, y se crearon; las cuatro respuestas
constan como enviadas en el log del gateway. **Falta** que el usuario confirme que las ve en su tema. El tema «Conversaciones» (del primer diseño) ya no se usa.

## Firewall de Fase 7

`apply-firewall.sh` + `nftables-sip.candidate.nft` (pasa `nft -c` el 02-11). Crea `gateway` (solo Telegram
y DNS) y `gw-research` (`internal`, sin reenvío ni acceso al host). Sin `br_netfilter`, el tráfico dentro
de un bridge no pasa por nftables: el enlace se cierra con `internal` y con el `drop` de entrada al host.
Sonda probada sobre la red `research`. Lo aplica el usuario.

**v0.22 cambia el gateway:** uno solo para todos los perfiles. El plugin de enrutado tendría que
revalidarse al actualizar Hermes (ver 99-NOTAS, 02-11).
