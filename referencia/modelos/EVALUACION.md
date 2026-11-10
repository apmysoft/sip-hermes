# Evaluación semanal de modelos (v2.4 Fase 9, decisión 11)

Estado a 02-11-2026: **desplegada y verificada** en Neo (`sip-model-eval.timer`, domingos a las 4:00).
Propone; nunca cambia nada. La decisión es del usuario.

## Diseño

1. **Métricas deterministas** (sin LLM): de `LiteLLM_SpendLogs`, los últimos 7 días por modelo
   (llamadas, % de fallos, latencia mediana de los aciertos, gasto). Se marcan como «no configurado» los
   nombres que no están en `litellm.config.yaml` (peticiones erróneas o pruebas de autenticación). Se
   añaden el inventario de Ollama en HALO (sin despertarlo) y los modelos configurados.
2. **Propuesta de RESEARCH**: un turno por su API desde un contenedor desechable en `gw-research`, con la
   clave por `--env-file`. Revisa fuentes oficiales con el navegador y propone como mucho 3 cambios. No
   basa nada en menos de 20 llamadas.
3. Informe completo en `/var/lib/sip-model-eval/<fecha>.md` (root, 0700) y resumen por `sip-notify`.

Hacia RESEARCH (cloud) solo salen nombres de modelos y cifras de uso.

**Desviación de v2.4:** v2.4 pone este cron en el agente (cron nativo de Hermes). Aquí lo dispara un
timer de systemd, porque las cifras están en la DB de LiteLLM, a la que RESEARCH no debe acceder, y
porque RESEARCH no entrega en Telegram. El agente solo redacta la propuesta. **Aceptada por el usuario el
02-11-2026.**

Instalación: `apply-eval.sh`. Prueba sin LLM ni envío: `/usr/local/sbin/sip-model-eval.py --solo-metricas`.

## Verificado el 02-11-2026

- Ejecución real del servicio: `success` y aviso enviado.
- Primera propuesta mala: proponía retirar `gpt-4o`, que no está configurado, y `k3.1-pro` con 3
  llamadas. Corregido marcando los nombres no configurados y fijando el mínimo de 20 llamadas.
- Segunda: «sin cambios», bien razonado. Corregido también un error de SQL que `psql` no reportaba
  (`round(double precision)`); ahora va con `ON_ERROR_STOP`.

## Limitaciones

- RESEARCH solo pudo consultar Google AI; dice no haber comprobado Kimi, Qwen ni Ollama. El informe lo
  indica cada semana. A revisar si se repite.
- `gemini-3.8-flash` tiene una latencia mediana de ~130 s en sus aciertos; seguramente son turnos largos
  del navegador, no lentitud del modelo. Sin investigar.

## Candidatos en observación

- **Qwen3.8-Flash-Next** (revisado el 04-11; **corregido el 05-11** tras analizar el vídeo de Jorge Marfil
  «¿La IA más potente ya funciona en un PC normal?», 31-10-2026, transcripción obtenida con `yt-dlp`).
  MoE multimodal: 125B que calculan (512 expertos, 10+1 activos, ~6B por token) + 51B de tabla n-grama
  (embedding de grupos de 3 palabras en la capa 2, idea de DeepSeek «Conditional memory via scalable
  lookup») + 4B de MTP; arquitectura `qwen4xp` (vista previa de Qwen4). 262K de contexto.
  - **Error del 04-11:** se descartó porque el fichero (72–90 GB) no cabe en VRAM+RAM. No hace falta:
    llama.cpp mapea el fichero, la tabla n-grama se queda en el SSD (se sabe de antemano qué filas leer)
    y los expertos en RAM. Soporte en la rama principal de llama.cpp; MTP integrado el 01-10. No en Ollama.
  - **Medido por el autor** (RTX 3060 12 GB, Ryzen 6 núcleos, 61 GB DDR4, Q3 de 82 GB): generación 16,5 tok/s
    de serie y **24,4 con un hilo por núcleo físico** (con 12 hilos, 65 % del tiempo en espera). RAM: ≥24 GB
    para generar a ~22 tok/s; lectura de prompt >100 tok/s con ≥40 GB, 34 con 32 GB, 15 con 24 GB. MTP: +1 tok/s
    en su equipo, ×1,55 en DGX Spark. Laboratorio de 3 tareas con trampas: 17/17 (igual que Opus 5; Qwen3.6-35B
    14/17), a 16–60 min por tarea. Uso que propone: 3.8 planifica y revisa, 3.6 ejecuta.
  - **Para HALO** (24 GB VRAM, 32 GB DDR4, 16 núcleos): generación previsiblemente ≥20 tok/s; **lectura del
    prompt ~34 tok/s** → un prompt de Hermes de 20–30k tokens, 10–15 min: no apto para chat en PERSONAL.
    **Encaje: planificador/revisor del traspaso nocturno de CODING** (la latencia no importa; cubre el
    pendiente de comparar con un modelo más capaz). Con 64 GB de RAM, la lectura del prompt pasaría de 100 tok/s.
  - **Prueba propuesta (sin decidir):** llama.cpp (Vulkan/ROCm) en HALO con el Q3 (~82–90 GB de descarga),
    `-t 16`, medir generación y lectura de un prompt real de CODING; luego una tarea del traspaso.
  - Cautelas: medidas de una persona en 3 tareas; cuantizado a 3 bits; vista previa experimental; la
    comparación con Opus es impresión del autor. Versión alojada (~0,16/0,47 $ por M): solo para RESEARCH.
