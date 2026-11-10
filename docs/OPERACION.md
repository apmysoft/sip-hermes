# Operación diaria

Cómo se mantiene el sistema una vez montado. Los horarios están en `COMO-FUNCIONA.md` (sección «Un día
normal») y las piezas, en `referencia/`.

## Lo que corre solo

- **Timers del servidor:**
  - alertas cada hora;
  - índice (00:30), traspaso nocturno (01:30), OCR en el equipo con GPU (02:00–06:00), garantías (02:15) y barrido
    del gestor (03:00);
  - copias cifradas de las bases (03:40) y del estado completo para Kopia (21:15);
  - resumen matutino (08:00);
  - informe de actualizaciones (sábado), evaluación de modelos y curación de memoria (domingo);
  - auditoría trimestral.
- **Parches de seguridad automáticos** en el servidor, sin núcleo, NVIDIA ni Docker, que se deciden a mano.
- **Energía:** el equipo con GPU se apaga tras 1 h sin actividad y se enciende por WOL cuando hace falta.

## Vigilancia

**Telegram es el panel.** Tres temas de avisos:
- **«Avisos»:** alertas y resultados de tareas.
- **«Peticiones»:** códigos de confirmación, enchufe del equipo con GPU…
- **«Redacción»:** el motor de automatismos.

Las alertas avisan cuando algo aparece o sube de nivel, lo recuerdan una vez al día y avisan cuando se resuelve. Lo
que vigilan:
- disco y RAM (80 % y 90 %);
- conexiones cortadas de la zona personal (si sube, alguien intenta salir);
- tamaño de la cuarentena;
- ráfagas de WOL;
- errores 429 y presupuesto de LiteLLM;
- inicios de sesión fallidos en las WebUI y en Vaultwarden;
- bloqueos de SQLite y WAL grandes;
- errores del servidor del modelo pequeño (lección 1).

**Comprobaciones a mano útiles:**

```sh
systemctl list-timers | grep sip                 # qué ha corrido y cuándo toca
systemctl --failed                               # unidades caídas
journalctl -u <servicio> --since yesterday -o cat
docker ps --format '{{.Names}} {{.Status}}'      # estado de las zonas
curl -s http://${HALO_TAILNET_IP}:11434/running  # qué modelo ocupa la GPU
```

## Incidentes

- **Algo hace cosas raras:** `sip-panico stop` para las zonas y los puentes en segundos. Solo queda el gateway,
  para avisarte. `sip-panico start` lo vuelve a levantar.
- **Te vas de viaje:** `sip-ausencia on` (y `off` al volver) reduce los automatismos, no despierta al equipo con GPU salvo petición
  explícita y envía un latido diario.
- **El servidor se cuelga:** el enchufe inteligente hace un reinicio forzado, como último recurso. La BIOS lo
  arranca al volver la corriente y unas unidades esperan a la VPN antes de levantar lo que publica en ella.
- **Un modelo no responde:** la zona personal pasa al modelo pequeño y, si tampoco está, a la cola de Telegram.
  Revisa `journalctl -u llama-swap` en el equipo afectado.
- **Una clave se ha visto o filtrado:** sigue el runbook de rotación. El registro de rotación dice qué existe y dónde.

## Copias y restauración

- **Kopia** hace la copia diaria general en un disco aparte, fuera del alcance de cualquier zona.
- **Cada noche** se genera una copia **cifrada (age)** del estado de las zonas, de LiteLLM y del motor de
  automatismos, dentro de lo que copia Kopia.
- **Prueba de restauración (O11):** recupera un `sip-estado-*` desde KopiaUI, descífralo y pasa el simulacro
  (`simulacro-o11.sh`): comprueba la integridad de cada base y arranca una zona restaurada en un entorno aparte.

## Rotación de credenciales

- **Registro de rotación:** apunta cada credencial (nombre, lugar, cuándo se creó, se tocó o se vio), nunca su valor.
- **Inventario de identidades:** qué usuario Unix, token o clave usa cada pieza.
- **Al cerrar una ventana de trabajo con un agente:** revisa qué ha visto, rota lo necesario, retira sus privilegios
  temporales y borra las copias que contengan valores.

## Actualizaciones

- **Imágenes y binarios:** fijados por digest o sha256. El informe semanal dice qué tiene versión nueva y tú decides.
  Cada actualización, con copia y vuelta atrás.
- **Hermes:** se prueba primero una imagen candidata con una copia del volumen y después se cambia. Así se pasó de la
  0.21 a la 0.22, que exigió adaptar el navegador de RESEARCH.
- **Sistema operativo del equipo con GPU:** subir de versión mayor rompe los entornos de Python y los binarios
  compilados. Hazlo planificado, con copia y una lista de comprobación, no desde el aviso.

## Mantenimiento semanal (15 minutos)

- Revisa los avisos de la semana y el informe de actualizaciones.
- Cuarentena: ¿algo que recuperar o que dejar caducar?
- Memoria y skills: aprueba o rechaza lo pendiente (las zonas no guardan nada sin revisión).
- Garantías: el informe de ficheros dañados y duplicados.
