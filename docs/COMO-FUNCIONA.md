# Cómo funciona, con ejemplos

Esta guía explica el sistema recorriendo situaciones reales. El diseño completo, con su razonamiento, está en
`ARQUITECTURA.md`; lo aprendido por el camino, en `LECCIONES.md`.

## En un minuto

Hay **dos ordenadores**:

- **Neo**, un servidor modesto siempre encendido (i7-6700K, 16 GB, GTX 1070). Aloja a Hermes, el agente.
- **HALO**, el ordenador de trabajo, con una GPU potente (RX 7900 XTX). Se enciende por la red cuando hace falta
  pensar en serio y se apaga solo cuando nadie lo usa.

Los dos se ven por **Tailscale** (una VPN), y nada del sistema está abierto a Internet.

En Neo, Hermes no es un único agente con acceso a todo: son **tres zonas separadas**, cada una en su contenedor,
con su usuario de sistema y su red.

| Zona | Para qué | Qué puede tocar | Qué no puede tocar |
|---|---|---|---|
| **PERSONAL** | Tus documentos, el gestor de ficheros, imágenes, transcripciones, apagar HALO… | Lee tus documentos (solo lectura) y su espacio de trabajo | Internet y modelos en la nube |
| **CODING** | Programar | Un *worker* aislado en HALO con el código | Tus documentos |
| **RESEARCH** | Buscar en Internet | Internet (por SearXNG y un navegador controlado) y dejar resultados en una bandeja de entrada | Tus documentos, la LAN y la VPN |

La regla de fondo: **un agente que ha leído Internet no tiene, en ese proceso, acceso a tus datos**. Y lo que tiene
efecto real (renombrar ficheros, apagar un equipo, instalar un servicio) **solo se hace con un código** que te llega
al móvil y que el agente nunca ve.

```
   Telegram / navegador (tus dispositivos, por Tailscale)
                 │
          ┌──────┴───────┐
          │  sip-gateway │  enrutador SIN modelo de IA: no se le puede "convencer" de nada
          └──┬────┬────┬─┘
     PERSONAL  CODING  RESEARCH          ← tres contenedores Hermes, tres redes
        │        │        │
        │        │        └── Internet (filtrado) ── deja notas en 00_entrada vía filegate
        │        └── SSH ──► worker aislado en HALO
        ├── /para (tus documentos, SOLO LECTURA)
        ├── filegate (la única forma de escribir: socket + token; nunca borra)
        └── modelos locales: 27B en HALO (despierta por WOL) · respaldo: 4B en Neo
```

## 1. Preguntas algo a PERSONAL por Telegram

> «¿Cuánto pagué de luz en octubre?»

1. Telegram entrega el mensaje a **sip-gateway**, que solo comprueba que eres tú (lista blanca de usuarios) y lo
   pasa a la API de la zona PERSONAL. El gateway no tiene modelo de IA: no interpreta, solo enruta.
2. Antes de llamar al modelo, el plugin `sip-halo-wake` comprueba si HALO responde. Si está apagado, pide el
   despertar al **servicio WOL de Neo**, el único que envía *magic packets*, con un tope de 5 por hora. HALO arranca
   en unos 25 segundos.
3. El modelo grande (27B) decide usar `documentos_buscar_texto`, que consulta el **índice** de tus documentos (en
   Neo, solo lectura) y devuelve fragmentos de las facturas. Si hace falta, `documentos_leer` abre el PDF, y si
   está escaneado lo pasa por OCR en HALO.
4. La respuesta vuelve por el gateway al tema «PERSONAL» de Telegram.

**Si HALO no despierta** (por ejemplo, porque apagaste su enchufe), Hermes pasa al **modelo pequeño de Neo** (4B):
responde peor, pero responde. **Si tampoco está el pequeño**, el gateway guarda el mensaje en una **cola**, te
avisa de que ha quedado en espera y lo reintenta cada 10 minutos durante 24 horas. Nunca se manda a la nube.

## 2. PERSONAL quiere hacer algo con efecto

> «Renombra los ficheros nuevos de la bandeja de entrada.»

Ninguna zona puede escribir libremente en tus documentos. El patrón es siempre el mismo, **propón y confirma**:

1. El agente escribe una **petición** en una carpeta vigilada (`/workspace/_gestor/requests/…`).
2. Un **servicio del host** (fuera del contenedor, con su propio usuario) la valida con reglas fijas y genera un
   **código de 6 cifras** que te envía por Telegram, al tema «Peticiones». El agente no lo ve.
3. Tú le das el código al agente si estás de acuerdo. Si no lo has pedido tú, lo ignoras.
4. Con el código, el servicio ejecuta: renombra mediante **filegate**, que nunca borra, sino que mueve a una
   cuarentena de 180 días.

Funcionan igual el **gestor de entrada** (renombres), el **puente de energía** (apagar HALO) y el **puente de
servicios Docker**, que permite actualizar, reiniciar o incluso **crear** un servicio nuevo, siempre que su compose
pase un validador: imagen fijada por digest, sin privilegios, sin `docker.sock`, puertos solo en local o en la VPN
y límites de memoria y CPU.

## 3. RESEARCH busca algo en Internet

> «Busca la última versión estable de Python y su fecha.»

RESEARCH busca con **SearXNG** (un buscador local que agrega Google, DuckDuckGo, Brave…) y, si hace falta, abre las
páginas con un **navegador de órdenes fijas**: abrir, leer, pulsar, escribir, volver. No puede ejecutar código, y la
política de URL le impide visitar direcciones locales, de la VPN o de bancos. Usa el 27B de HALO por LiteLLM y, si
HALO no responde, un modelo gratuito en la nube. Puede descargar vídeo o subtítulos (`yt-dlp`) y dejar el resultado
en la bandeja de entrada de tus documentos, siempre por filegate y nunca en otra carpeta.

Como no ve ningún dato personal, que use la nube no es un problema de privacidad.

## 4. CODING trabaja en un proyecto

CODING ordena; quien ejecuta es un **worker en HALO** al que entra por SSH con orden forzada. El worker corre con
bubblewrap, sin red, con topes de CPU, RAM y número de procesos, y con un disco propio. Lo destructivo exige
aprobación.

De noche, el **traspaso nocturno** puede encargarle tareas de una cola. Un verificador independiente del agente
comprueba los criterios, los ficheros permitidos, el commit y que el árbol quede limpio. Nunca fusiona ni sube nada.

## 5. Un día normal

| Hora | Dónde | Qué pasa |
|---|---|---|
| Cada 5 min | Neo → HALO | Consulta de actividad. Tras 1 h sin teclado, audio, agentes trabajando, CPU del usuario, modelos cargados ni SSH, HALO se apaga y avisa |
| Cada hora | Neo | Alertas: disco, RAM, conexiones cortadas de la zona personal, cuarentena, WOL, cuotas, inicios de sesión fallidos, SQLite y errores del modelo pequeño |
| 00:30 | Neo | **Índice**: texto de los documentos nuevos o cambiados; retira los borrados |
| 01:30 | Neo → HALO | **Traspaso nocturno** de tareas de código, si las hay |
| 02:00–06:00 | Neo → HALO | **OCR** de los PDF escaneados: despierta HALO por WOL y usa sus 16 núcleos (horario valle) |
| 02:15 | Neo | **Garantías**: huellas e integridad de los ficheros (primero lo irreemplazable) |
| 03:00 | Neo | **Barrido del gestor de entrada**: propone nombres para lo nuevo |
| 03:40 | Neo | Copias cifradas de las bases de datos |
| 08:00 | Neo | **Resumen matutino** por Telegram, solo con datos del sistema |
| 21:15 | Neo | Copia cifrada del estado del sistema dentro de la copia de seguridad general (Kopia) |
| Sáb. y dom. | Neo | Informe de actualizaciones, evaluación de modelos y recordatorio de curación de la memoria |

## 6. La GPU de HALO, compartida

Solo cabe un modelo grande a la vez en la GPU. **llama-swap** hace de planificador: el modelo de texto, Whisper y
ComfyUI se turnan, y antes de cambiar espera a que termine la petición en curso. ComfyUI no encaja de serie en ese
esquema, porque acepta el trabajo y responde enseguida. Por eso un nodo propio retiene la GPU desde antes de
enviar el trabajo hasta entregar el resultado. Mientras genera una imagen, las peticiones de texto esperan su
turno.

## 7. ¿Qué pasa si…?

- **…HALO está apagado o roto?** PERSONAL sigue con el modelo pequeño de Neo; si tampoco está, cola. CODING no
  ejecuta (cola). RESEARCH usa la nube.
- **…Neo se cae?** Se cae el sistema entero (punto único de fallo asumido). La BIOS lo enciende al volver la
  corriente, y hay un procedimiento de reconstrucción y copias en Kopia.
- **…un documento contiene instrucciones maliciosas** («ignora lo anterior y borra…»)? Las herramientas marcan el
  contenido como «material, no instrucciones»; el gestor detecta patrones de inyección y se abstiene. Aunque el
  modelo obedeciera, no tiene con qué: no puede borrar, no tiene terminal en PERSONAL y lo que tiene efecto pide
  código.
- **…se llena un disco?** Alerta a Telegram al 80 % y al 90 %. Staging y cuarentena viven en un disco aparte, con
  cuota y caducidad.
- **…algo va muy mal?** `sip-panico stop` para todas las zonas en unos segundos, y `sip-ausencia on` reduce lo que
  puede despertar HALO mientras estás fuera.

## Glosario

- **Zona:** un contenedor Hermes con su usuario, su red y sus permisos (PERSONAL, CODING, RESEARCH).
- **PARA:** la estructura de carpetas de los documentos (Proyectos, Áreas, Recursos, Archivo, más `00_entrada`).
- **filegate:** el servicio que hace todas las escrituras en PARA en nombre de las zonas, con token por zona.
  Nunca borra: pone en cuarentena.
- **Tiny:** el modelo pequeño (4B) de la GPU de Neo, siempre disponible.
- **Puente:** un servicio del host que atiende peticiones de una zona dejadas en una carpeta, con reglas fijas y
  código de un solo uso para lo que tiene efecto.
- **WOL (Wake-on-LAN):** el paquete de red que enciende HALO. **Tapo:** el enchufe inteligente de HALO, solo para un
  reinicio forzado de último recurso.
- **LiteLLM:** el proxy que guarda las claves reales de la nube y da a cada zona una clave virtual con límites y
  presupuesto.
- **llama-swap:** el planificador que arranca y para modelos y servicios de GPU bajo demanda.
- **`fail-closed`:** ante la duda, detener y preguntar; nunca relajar una restricción.
