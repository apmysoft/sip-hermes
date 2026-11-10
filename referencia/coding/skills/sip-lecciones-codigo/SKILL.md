---
name: sip-lecciones-codigo
description: Úsala SIEMPRE antes de cualquier tarea de código y antes de dar algo por terminado. Reglas verificadas en tareas reales de SIP: ficheros grandes, imports, interfaces externas, verificación e informe.
---
# Lecciones de código (SIP)

Cada regla sale de un fallo o un acierto real, verificado por un revisor (pilotos del 02 y 03-11-2026).
No son opiniones: cuando un modelo las incumplió, la tarea se perdió.

## Antes de empezar

1. **Comprueba dónde estás.** El repositorio está bajo `/workspace`. Ejecuta `pwd` y `ls` antes de editar.
   Nunca edites rutas que no hayas visto existir (fallo real: se intentó editar
   `/var/lib/hermes-worker/src/App.tsx`, que no existía).
2. **Lee la especificación entera y lista los criterios de aceptación** como comandos que vas a ejecutar.

## Ficheros grandes (más de ~1.500 líneas)

3. **No los leas enteros:** la lectura corta a 2.000 líneas y abandonarás. Usa `wc -l`, `grep -n` para
   localizar y `read_file` por rangos (fallo real: abandono con `App.tsx` de 3.180 líneas).
4. **Edita con `patch` sobre fragmentos pequeños. Nunca reescribas el fichero completo con `write_file`**
   (fallo real: `App.tsx` quedó en 20 líneas, −3.162).
5. **Tras tocar imports, comprueba que cada símbolo usado sigue importado** y pasa el typechecker antes de
   seguir (fallo real: se borraron 5 imports en uso y `tsc` dio 6 errores).

## Interfaces externas

6. **No inventes el formato de una herramienta externa** (CLI, API, JSON). Mira `--help`, la
   documentación o un ejemplo real; si no puedes, dilo (fallo real: se leyó `item["uri"]`, un campo que
   `bw` no tiene, y las pruebas pasaban contra un mock inventado).
7. Las pruebas de integración usan un **falso ejecutable** que imite el formato real, no un mock interno.

## Verificación e informe

8. **Ejecuta tú cada criterio y pega la salida real, sin resumir.** Un informe que no coincide con lo que da
   el comando es el peor fallo posible: el revisor deja de fiarse de todo.
9. **Si un criterio falla, la tarea no está terminada.** No lo achaques al entorno sin una prueba (fallo
   real: 6 de 8 pruebas fallando y se dio por terminado).
10. **Nunca modifiques ni debilites las pruebas o los criterios** para que pasen.
11. Si el plan de la especificación no llega al objetivo, **mide qué falta** (por ejemplo, analiza el
    bundle) y extiende lo mínimo, declarándolo en el informe (acierto real: se descubrieron dos modales que
    arrastraban `recharts` y se pasaron a carga diferida).
12. Antes del commit: `git diff --stat` solo con los ficheros esperados, `git status --short` limpio y sin
    ficheros temporales.

## Recetas verificadas

- **Dividir un bundle de Vite/React:** `React.lazy` + `<Suspense>` en cada uso; `manualChunks` como
  **función** por ruta de `node_modules` (la forma objeto dejó chunks vacíos); busca dependencias pesadas
  que entren por componentes no diferidos (modales). Criterio: tamaño del chunk de entrada y ningún aviso.

## Cómo crece esta skill

La mantiene el revisor (no el agente) tras cada tarea revisada: fuente en el repositorio SIP,
`sip-config/coding/skills/`. Si descubres algo que debería estar aquí, dilo en tu informe final con la
etiqueta `LECCIÓN:`; no edites esta skill.
