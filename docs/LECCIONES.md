# Lecciones de montar un agente de IA en casa con datos personales

Lo aprendido durante la implantación (octubre–noviembre de 2026), destilado del diario de trabajo.

**Contexto:**
- **Servidor siempre encendido:** i7-6700K, 16 GB, GTX 1070 de 8 GB.
- **Equipo de trabajo con GPU:** Ryzen 9 5950X, 32 GB, RX 7900 XTX de 24 GB.
- **Hermes Agent** en tres zonas aisladas: personal, código e investigación.

Cada lección sigue el mismo esquema: **qué pasó**, **por qué**, **qué se hizo** y **qué aplicar en tu montaje**. Las
cifras son medidas reales.

---

## A. Modelos e inferencia local

### 1. Un puerto ocupado dejó al modelo pequeño dos días sin funcionar, y nadie se enteró
- **Qué pasó:** el resumen matutino salió sin titular y el gestor de ficheros generó lotes inútiles, pero systemd
  marcaba todo como correcto.
- **Por qué:** llama-swap da a cada modelo un puerto a partir de 5800, y un servicio doméstico nuevo empezó a usar
  justo ese. El modelo moría al arrancar y los servicios que lo llamaban recibían un error 500, lo gestionaban y
  terminaban «bien».
- **Qué se hizo:** `startPort` explícito en la configuración de llama-swap y una alerta horaria que cuenta los 500
  del servidor de modelos.
- **Para tu montaje:** vigila los **resultados** (errores del servidor de modelos, lotes vacíos), no solo el código
  de salida de los servicios. Y fija siempre los puertos.

### 2. Ollama → llama.cpp + llama-swap mereció la pena
- **Qué pasó:** migrar los 9 modelos llevó una tarde, con todas las pruebas de herramientas, razonamiento,
  *streaming* y visión.
- **Por qué:** llama.cpp permite decodificación especulativa (MTP) y control fino por modelo.
- **Resultado:** un 27B denso pasó de 54–67 a **77 tokens/s** en la misma GPU. llama-swap añade grupos (qué modelos
  pueden convivir), arranque bajo demanda con TTL y alias para conservar los nombres antiguos.
- **Para tu montaje:** si tienes una sola GPU y varios usos, un planificador como llama-swap simplifica mucho.

### 3. La GPU compartida perdía las imágenes a medias
- **Qué pasó:** mientras ComfyUI generaba una imagen, llegaba una petición de texto y la imagen se perdía.
- **Por qué:** llama-swap espera a que termine la **petición HTTP** en curso antes de cambiar de modelo, pero
  ComfyUI acepta el trabajo (`POST /prompt`) y responde enseguida. El planificador lo creía libre.
- **Qué se hizo:** un nodo propio de ComfyUI que abre una petición **antes** de enviar el trabajo y la mantiene hasta
  devolver el fichero en esa misma respuesta. El primer intento (esperar después de enviar) dejaba un hueco de
  milisegundos por el que se colaba el texto.
- **Para tu montaje:** cualquier servicio asíncrono detrás de un planificador por peticiones necesita algo así.

### 4. ComfyUI y el escritorio no caben a la vez sin cuidado
- **Qué pasó:** ComfyUI moría por falta de memoria (OOM), y una vez se quedó sin memoria todo el equipo.
- **Por qué:** dos causas. Un IDE con decenas de demonios de compilación (Gradle, ~11 GB) llenaba la RAM y la swap.
  Y la caché de modelos de ComfyUI conservaba el modelo de la imagen anterior, de 20 GB, al cargar el siguiente.
- **Qué se hizo:**
  - ComfyUI con límite de 24 GB y **sin swap**, para que no empuje tu sesión a disco;
  - `OOMScoreAdjust=1000`: si falta memoria, muere ComfyUI y no tus aplicaciones;
  - `--disable-pinned-memory` y `--cache-none`.
- **Para tu montaje:** en un equipo de uso personal, protege antes al usuario que a la IA.

### 5. Editar texto en imágenes necesita los valores de referencia
- **Qué pasó:** Qwen-Image-Edit escribió «PANCERÍA» en vez de «PANADERÍA».
- **Por qué:** se usaban 20 pasos y `cfg` 2,5, copiados de otro flujo.
- **Qué se hizo:** 40 pasos y `cfg` 4 (los de referencia del modelo). Texto correcto con dos semillas distintas, a
  cambio de tardar el doble (~5,5 min).
- **Para tu montaje:** antes de dar por malo un modelo, prueba sus parámetros de referencia.

### 6. El agente necesita más contexto del que parece
- **Qué pasó:** con el equipo grande apagado, la zona personal pasó al modelo pequeño y, en una conversación larga,
  falló al «compactar».
- **Por qué:** un turno de un asistente con ~40 herramientas consume entre 6.500 y 12.000 tokens por llamada, y hasta
  ~25.000 si usa varias. Hermes solo compacta con modelos de al menos 64K.
- **Qué se hizo:** el modelo pequeño (4B Q4) pasó a 64K con caché KV q8: **7,7 de 8 GB** de VRAM.
- **Para tu montaje:** mide los tokens reales de tus turnos antes de elegir el contexto. El tamaño del modelo
  importa menos que eso.

### 7. Solo se cambia de proveedor una vez por turno
- **Qué pasó:** la cadena de respaldo «modelo grande → otros dos del mismo equipo → modelo pequeño» nunca llegaba al
  pequeño.
- **Por qué:** Hermes 0.22 se rinde tras el primer cambio de proveedor en un turno, y los dos primeros respaldos caían
  junto al principal porque estaban en el mismo servidor.
- **Qué se hizo:** el respaldo **independiente** (otro equipo) pasó a ser el primero de la cadena.
- **Para tu montaje:** ordena los respaldos por independencia de fallo, no por calidad.

### 8. Los planes gratuitos de la nube no sirven para un agente
- **Qué pasó:** la zona de investigación fallaba casi siempre con «quota exceeded».
- **Por qué:** unas 20 peticiones al día por modelo, y **cada paso del agente** (pensar, buscar, leer) es una
  petición.
- **Qué se hizo:** investigación con el 27B local, y la nube solo de respaldo. Los turnos tardan unos 15 s y no hay
  límites.
- **Para tu montaje:** si la tarea no toca datos personales, lo local suele ser mejor que lo gratuito.

### 9. Comprueba que el servidor no recorta el contexto
- **Qué pasó:** un modelo para código MoE de 30B falló 6 de 6 pilotos reales.
- **Por qué:** en parte, el servidor recortaba el contexto sin avisar.
- **Qué se hizo:** contexto explícito y cambio a un 27B denso a 64K: 3 de 3 entregas correctas, con más tiempo por
  tarea (40–50 min).
- **Para tu montaje:** registra el número de tokens que recibe el modelo y compáralo con el que envías.

## B. Seguridad y arquitectura

### 10. Zonas de verdad, no perfiles
- **Por qué:** los perfiles de un mismo proceso no son una frontera de seguridad.
- **Qué se hizo:** un contenedor por zona, con usuario Unix, red Docker y nftables propios. La zona personal no tiene
  Internet. Trampa encontrada: el DNS de Docker lo resuelve el host, **fuera** del cortafuegos; se cierra con `dns:`
  apuntando a la pasarela del bridge.
- **Para tu montaje:** comprueba desde dentro de cada contenedor lo que puede alcanzar de verdad (resolución de
  nombres incluida).

### 11. Una sola puerta de escritura, que nunca borra
- **Qué se hizo:** filegate, un servicio con socket Unix y token por zona. Valida rutas y transiciones y, en lugar de
  borrar, mueve a una cuarentena de 180 días. La zona personal monta los documentos en solo lectura.
- **Para tu montaje:** que el agente pueda borrar definitivamente es un riesgo que no compensa casi nunca.

### 12. Consentimiento con código, no menos capacidad
- **Idea:** la barrera no es quitarle herramientas al agente, sino exigir **consentimiento explícito** para lo que
  tiene efecto.
- **Cómo:** el agente propone; un servicio del host valida y te envía un código de 6 cifras por Telegram; tú se lo
  das. El modelo nunca ve el código, y tres intentos erróneos anulan la propuesta.
- **Dónde se usa:** renombrar ficheros, apagar el equipo, actualizar, reiniciar o crear servicios.

### 13. Dejar que el agente cree servicios Docker, con un validador
- **Qué se hizo:** un compose solo se acepta si cumple todo esto:
  - la imagen va fijada por digest;
  - no usa `privileged`, `cap_add`, dispositivos, `network_mode`, `docker.sock` ni redes externas;
  - monta solo dentro de su propia carpeta;
  - publica puertos solo en local o en la VPN;
  - tiene límites de memoria, CPU y procesos.
- **Trampa:** la zona no tiene Internet y no podía averiguar el digest; lo resuelve el host con una consulta sin
  efecto.

### 14. Los agentes afirman cosas que no han hecho
- **Qué pasó:** el asistente dijo haber guardado una nota en una carpeta en la que no puede escribir, y dio por
  verificada una prueba antes de hacerla.
- **Para tu montaje:** contrasta lo que dice el agente con los registros. Diseña las herramientas para que devuelvan
  pruebas (ruta, tamaño, código HTTP) y no solo «hecho».

### 15. Privilegios temporales para el agente que te ayuda a montarlo
- **Qué se hizo:**
  - **sudo con caducidad:** un fichero en `sudoers.d` más un timer que lo retira en una fecha; el agente no puede
    renovárselo;
  - **registro de rotación:** apunta toda credencial que el agente crea, toca o **ve** (nombre y lugar, nunca el
    valor);
  - **copia previa y vuelta atrás** antes de cada cambio.

## C. systemd, Docker y operación

### 16. `RuntimeMaxSec` no limita los servicios `oneshot`
- **Por qué:** en los servicios `oneshot`, el límite que cuenta es `TimeoutStartSec`. systemd lo avisa, pero solo en
  el registro.
- **Para tu montaje:** revisa `systemd-analyze verify` en las unidades nuevas.

### 17. Las unidades `.path` entran en bucle si la petición se queda
- **Qué hacer:** retira siempre el fichero de la carpeta vigilada, también cuando falla. Si no, llegas a
  `unit-start-limit-hit` y el puente deja de responder.

### 18. Ficheros montados sueltos en Docker: no cambies el inodo
- **Qué hacer:** edita con `cat > fichero` o con escritura `r+`. `sed -i`, `mv` o `git checkout` crean un inodo nuevo
  y el contenedor sigue viendo el viejo hasta que lo recreas.

### 19. Edita la configuración que se usa de verdad
- **Qué pasó:** Hermes copia su configuración inicial al volumen la primera vez y después usa esa. Se cambió la copia
  del repositorio durante un buen rato sin ningún efecto.
- **Para tu montaje:** busca qué fichero lee el proceso en marcha antes de editar.

### 20. Arranque tras reinicio y la IP de la VPN
- **Qué pasó:** lo que publica puertos en la IP de Tailscale no arrancaba tras reiniciar, porque la VPN aún no
  tenía IP.
- **Qué se hizo:** una unidad que espera a la IP y luego arranca esos contenedores, verificada en reinicios
  reales.

### 21. Antes de una prueba destructiva, programa la vuelta atrás
- **Qué se hizo:** para probar la cola sin modelos, se paró todo después de programar su restauración con
  `systemd-run --on-active=11m`, porque los privilegios del agente caducaban esa misma noche.

## D. Documentos e índice

### 22. Los nombres de fichero que no son UTF-8 rompen SQLite
- **Por qué:** Python representa esos bytes como «sustitutos» y SQLite los rechaza (`surrogates not allowed`). Una
  sola pasada del índice se caía entera.
- **Qué se hizo:** saltarlos y contarlos (había 2 entre 489.000).

### 23. Protege los borrados por carpeta, no por proporción
- **Qué pasó:** la regla «no borrar del índice si falta más de la mitad» bloqueaba un borrado masivo legítimo.
- **Qué se hizo:** conservar solo las entradas de carpetas que no se pudieron leer. Así se distingue un disco medio
  montado de un borrado real, y lo borrado sale del índice esa misma noche.

### 24. Un disco duro con medio millón de ficheros es lento de recorrer
- **Cifras:** solo recorrer ~490.000 ficheros tarda **unos 100 minutos**, aunque no haya nada nuevo.
- **Qué se hizo:**
  - timeouts dimensionados a eso;
  - buscar por nombre consultando las rutas del índice, en lugar de recorrer el disco: de 60 s (cortada) a 0,3 s.

### 25. El OCR, al equipo potente y en horario valle
- **Qué se hizo:**
  - a las 02:00, el servidor despierta al equipo con GPU por WOL y le envía los PDF escaneados (como
    `documento.pdf`: el nombre real no sale del servidor);
  - el equipo los procesa con 12 hilos y se apaga solo una hora después: **487 PDF en 80 minutos**;
  - los libros (PDF de más de 100 páginas) entran solo por título.
- **Resultado:** el índice de ~18.000 documentos ocupa 385 MB.
- **Trampa:** con todos los hilos (32) a la vez, un PDF enorme agotó la memoria del servicio.

### 26. Comprobar la integridad empezando por lo irreemplazable
- **Qué se hizo:** huellas de todos los ficheros y revisión rotatoria cada noche, por prioridad: documentos, fotos,
  libros, audio, comprimidos y, al final, vídeo.
- **Por qué:** con 4,4 TB, 3,2 de ellos en vídeo, empezar por orden alfabético habría tardado meses en proteger lo
  importante.
- **Primera noche:** 13.440 huellas y 77 ficheros dañados encontrados.

## E. Escritorio (Ubuntu)

### 27. Al quitar snaps, revisa los paquetes de contenido
- **Por qué:** `snap remove` protege las bases en uso (`core22`…), pero **no** los paquetes de contenido (`gnome-*`,
  `mesa-*`, temas) que otros snaps tienen conectados.
- **Qué hacer:** revisa `snap connections` de los snaps que quedan antes de limpiar.
