---
name: halo-energia
description: Consulta qué está haciendo HALO (el equipo de los modelos) y lo apaga cuando el usuario lo pide, con su código de confirmación. Úsala cuando el usuario quiera apagar HALO, saber si está encendido o qué está haciendo.
---
# Apagar HALO o ver qué está haciendo

No tienes acceso a HALO: trabajas con un puente de ficheros que atiende Neo.

- Peticiones: `/workspace/_energia/requests/<id>.json` (escríbelas con tu herramienta de ficheros)
- Resultados: `/workspace/_energia/results/<id>.json` (tardan unos segundos)

Usa ids como `energia-AAAAMMDD-HHMMSS`. Si un resultado no aparece en un minuto, díselo al usuario; no
reintentes en bucle.

HALO se apaga solo tras 1 hora sin actividad y avisa por Telegram. Esto es para cuando el usuario lo pida.

## Ver qué está haciendo (sin efecto)

`{"id":"...","action":"estado"}` → `bloqueos` (lo que está trabajando: agentes como Claude Code, un modelo
cargado, audio, teclado en uso...), `abierto` (programas abiertos, por ejemplo Firefox) y los minutos sin
actividad.

## Apagar (con consentimiento del usuario)

1. `{"id":"...","action":"proponer"}`. Al usuario le llega por Telegram un código de 6 cifras; tú **no** lo ves.
2. Cuéntale **lo que está activo** (`bloqueos`) y lo abierto. Si hay algo trabajando (por ejemplo «Claude Code
   trabajando» o un modelo cargado), adviértele de que se cortará.
3. Si quiere apagar, pídele el código. Con él: `{"id":"...","action":"confirmar","borrador":"<borrador>",
   "codigo":"123456"}`.
4. Si el resultado dice que lo que hacía HALO ha cambiado, vuelve a proponer y cuéntaselo de nuevo.
5. Al apagar, recuérdale la `nota` sobre el enchufe Tapo y el WOL.

Nunca inventes un código ni lo reutilices. Tres códigos erróneos anulan la petición. Apagado, HALO se
vuelve a encender solo cuando haga falta (WOL), salvo que el enchufe esté apagado.
