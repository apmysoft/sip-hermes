# Nodo propio de ComfyUI: `sip_espera.py` (HALO, 07-11-2026)

**Problema:** llama-swap (planificador de GPU de HALO, un modelo a la vez) solo espera a la petición HTTP en curso
antes de cambiar de modelo. En ComfyUI, `POST /prompt` vuelve enseguida y el trabajo sigue después. Si llegaba una
petición de texto (PERSONAL, el redactor de sip-flujos…), llama-swap paraba ComfyUI a mitad del trabajo y la imagen
o la música se perdían.

**Arreglo:** la ruta `GET /sip/reservar/{client_id}?salida=images|audio&max=s`. El cliente (`sip-imagen` 1.1):
1. abre la reserva;
2. un segundo después envía `POST /prompt` con el mismo `client_id`;
3. recibe el fichero de salida en la respuesta de la reserva.

Siempre hay una petición abierta, así que llama-swap espera. El fichero viaja en la misma respuesta porque, al
cerrarla, llama-swap puede ceder la GPU, y el ComfyUI siguiente ya no tiene el historial, que vive en memoria.

La ruta solo lee la cola, el historial y la carpeta de salida (rutas comprobadas). No ejecuta nada ni acepta flujos,
y no registra nodos.

Coste asumido: mientras dura un trabajo de ComfyUI, las peticiones de texto esperan (de segundos a unos minutos).

## Instalación (HALO, root)

```sh
install -o sip-comfy -g sip-comfy -m 0644 sip_espera.py /opt/sip-comfyui/ComfyUI/custom_nodes/sip_espera.py
systemctl stop sip-comfyui   # si está en marcha; llama-swap lo arranca en la siguiente petición
```

Rollback: borrar el fichero y parar `sip-comfyui`. Sin él, `sip-imagen` 1.1 falla: la reserva da 404.

## Verificado (07-11)

- En local, con 2 peticiones de texto a `qwen3.8:27b` lanzadas a +0,5 s y +8 s:
  - FLUX 1344×768 en 62 s;
  - música de 30 s en 116 s;
  - ampliación ×4 en 19 s.
- Todos los trabajos completos, sin ningún `Stopping` entre `got prompt` y `Prompt executed`; el texto se atendió
  después (84–130 s).
- Antes del arreglo: `TimeoutError` y ComfyUI y el texto quitándose la GPU durante unos 5 minutos.
- **Primer diseño descartado** (`/sip/esperar/{prompt_id}`, abierto después de `/prompt`): el texto se colaba en el
  instante entre las dos peticiones.
