# Piezas de referencia

Son los ficheros que funcionan en el montaje original: servicios en Python, unidades systemd, reglas de nftables,
composes, plugins y skills de Hermes y los `apply.sh` con los que se desplegó cada pieza. Están anonimizados (ver
la tabla de marcadores en el `README.md` de la raíz).

**No son un instalador.** Cada carpeta da por hecho lo que montaron las anteriores (usuarios, redes, filegate) y los
`apply.sh` tienen rutas y nombres del montaje original. Léelos como receta: comprueban antes, guardan copia de lo
que cambian, aplican y verifican al final. Muchos README tienen fechas y notas de estado («verificado el…»): se
dejan porque cuentan cómo se comprobó cada pieza.

Algunos ficheros son **candidatos** (`*.candidate.nft`, `candidato-*`): versiones probadas antes de pasar a
producción, que se conservan como ejemplo del proceso.

## Índice

### Base y seguridad
| Carpeta | Qué es |
|---|---|
| `filegate/` | Única vía de escritura en los documentos: socket Unix, token por zona, nunca borra (cuarentena), TTL y cuota. Incluye las reglas nftables de las zonas y su prueba |
| `tailscale/` | Política de la ACL (*deny by default*) |
| `lan-docker/` | Cortafuegos entre las redes Docker de las zonas y la LAN |
| `halo/` | Worker de CODING en el equipo con GPU: shell forzada, bubblewrap, AppArmor, disco propio, SSH solo por la VPN |
| `sandbox-runner/` | Contenedor SSH endurecido para ejecutar código de las zonas |
| `vaultwarden/` | Gestor de contraseñas del agente, solo en la VPN |

### Zonas de Hermes
| Carpeta | Qué es |
|---|---|
| `hermes/` | Imagen, compose, endurecimiento de la configuración y plugins: `sip-documentos` (índice y lectura de PARA), `sip-imagen`, `sip-medios`, `sip-transcribir` |
| `personal-api/` | La zona PERSONAL como API para el gateway, con su cortafuegos |
| `coding/` | Zona CODING: compose, cortafuegos, skills y ejecutor |
| `research/` | Zona RESEARCH: navegador de órdenes fijas, SearXNG, yt-dlp y la prueba O3 |
| `memoria/` | Memoria con aprobación de escritura y curación semanal |
| `gateway/` | `sip-gateway`: Telegram → zonas sin LLM, temas por zona, cola de PERSONAL |

### Modelos y GPU
| Carpeta | Qué es |
|---|---|
| `llm-halo/`, `gpu-halo/` | llama.cpp + llama-swap en el equipo con GPU, y cómo comparten la GPU el texto, Whisper y ComfyUI |
| `llm-neo/`, `tiny-personal/` | El modelo pequeño del servidor y su uso como respaldo de PERSONAL |
| `litellm/` | Proxy con claves virtuales, límites y presupuesto por zona |
| `modelos/` | Enrutado, candidatos y evaluación semanal de modelos |
| `comfyui/` | ComfyUI con el nodo que reserva la GPU en llama-swap durante la generación |
| `whisper/`, `voz/`, `piper/` | Transcripción y notas de voz |
| `medios/` | API de medios en el equipo con GPU: OCR, audio y vídeo |

### Puentes con código de un solo uso
| Carpeta | Qué es |
|---|---|
| `gestor-entrada/` | Propone nombres para lo que entra en `00_entrada`; aplica por lotes aprobados |
| `energia/`, `wol/` | Encendido por WOL (único emisor, con tope) y apagado por inactividad o a petición |
| `stacks/puente/` | Actualizar, reiniciar o crear servicios Docker con un validador de compose |

### Datos
| Carpeta | Qué es |
|---|---|
| `indice/` | Índice SQLite FTS5 de los documentos y OCR nocturno delegado al equipo con GPU |
| `garantias/` | Huellas e integridad de los ficheros, con prioridad para lo irreemplazable |

### Operación
| Carpeta | Qué es |
|---|---|
| `notify/`, `avisos/` | Avisos deterministas a Telegram por temas |
| `alertas/` | Alertas horarias |
| `resumen/` | Resumen matutino |
| `traspaso/` | Tareas de código nocturnas con verificador independiente |
| `actualizaciones/` | Parches automáticos e informe semanal |
| `operacion/` | Modo pánico, modo ausencia, copias cifradas dentro de Kopia, simulacro de restauración y runbooks |
| `herramientas/` | Catálogo de herramientas de las zonas y sus conexiones |
