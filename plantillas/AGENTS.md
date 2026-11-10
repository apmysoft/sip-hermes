# Instrucciones para el agente de implantación

> Plantilla. Es el fichero de reglas que se dio al agente de programación (con sudo temporal) que ayudó a montar
> el sistema. Ponlo en la raíz de tu repositorio de inventario y adáptalo: rutas, equipos y plazos.

## Objetivo del repositorio

Este repositorio documenta y guía la implantación del sistema. Gran parte del trabajo se hace ejecutando órdenes
en los servidores, no solo editando ficheros. El agente actúa como guía técnica y mantiene la documentación
sincronizada con el estado real.

## Forma de trabajo

1. Explica brevemente qué se pretende conseguir.
2. Da solo el siguiente paso, o un grupo pequeño de órdenes muy relacionadas.
3. Espera la salida real antes de continuar y analízala.
4. No supongas que algo funcionó si no has visto su resultado.
5. Adapta el siguiente paso al estado observado.

## Fuente de verdad

Distingue siempre entre estado **diseñado**, **documentado** y **verificado**. La salida real de las órdenes manda
sobre los planes y los documentos antiguos. Nada está implantado solo porque aparezca en el plan.

## Documentación

- `ESTADO-ACTUAL.md`: una foto concisa del estado real (servicios, redes, persistencias, seguridad, pendientes,
  incidencias). No es un diario.
- `NOTAS.md`: la bitácora. Qué se hizo, qué se comprobó, resultado, incidencias, decisiones y pendientes. No reescribas
  el histórico; cuando algo del plan se complete, actualiza su estado.
- ADR o documento de arquitectura: solo para decisiones significativas (contexto, decisión, alternativas, razones,
  consecuencias).

## Antes de tocar nada

1. Lee `ESTADO-ACTUAL.md`, las notas relevantes y los ADR relacionados.
2. Inspecciona los ficheros reales implicados.
3. Si la documentación y el sistema se contradicen, dilo y verifica antes de cambiar nada.

## Cambios

- Identifica qué ficheros vas a tocar y por qué. Limita el cambio al objetivo; nada de refactorizar de paso.
- Antes de tocar un equipo: copia previa de lo que cambies (en `/root/agent-backups/<fecha>/`), vuelta atrás escrita
  y, si se puede, un `apply.sh` que verifique al final.
- Después: muestra el `git diff`, explica qué cambió y ejecuta las comprobaciones.

## Confirmación obligatoria

Pide confirmación para todo lo destructivo o que afecte al acceso: formatear, `fstab`, sudoers, cortafuegos, apagar o
deshabilitar SSH, la VPN o Docker, reiniciar, borrados definitivos y copias de seguridad.

## Nunca

- Leer o listar los discos de datos personales y de copias (salvo rutas de prueba que se indiquen).
- Leer claves privadas ni mostrar valores de `.env` o secretos: comprueba existencia, modo y propietario.
- Poner secretos en commits, registros o notas. Usa variables, marcadores o `REDACTED`.
- Tocar el fichero de sudo temporal del agente ni su temporizador de caducidad.
- Relajar el cortafuegos, la ACL de la VPN, filegate, cuotas o límites del worker. Si crees que hace falta,
  propónlo y espera.
- Cambiar la consola de la VPN: el agente prepara el fichero de política en el repo y el propietario lo aplica.

## Registro de credenciales

Apunta en `ROTACION.md` cada credencial, clave o secreto que hayas creado, tocado o **visto** (nombre y ubicación,
nunca el valor).

## Si algo falla

Si un paso falla dos veces, para y explícalo. No escales a cambios más amplios.

## Git

Sin autorización explícita, no hagas `commit`, `push`, `reset --hard`, `clean`, `rebase` ni reescrituras del
historial. No borres ficheros ni descartes cambios ajenos. Al terminar, muestra `git status --short`.

## Criterio de terminado

Escribir ficheros o ejecutar órdenes no es terminar: hace falta evidencia de que funciona (servicio activo,
comportamiento, persistencia tras reinicio, permisos, conectividad, política de seguridad, pruebas, estado de git).

## Cierre de cada bloque

1. Resume qué quedó realmente implantado.
2. Actualiza `ESTADO-ACTUAL.md` y las notas (y el ADR si hubo decisión).
3. Muestra el `git diff`, haz commit (si está autorizado) y muestra `git status --short`.
4. Propón el siguiente paso, sin ejecutarlo.

**Principio:** cambio pequeño → ejecución → comprobación → documentación → siguiente cambio.
