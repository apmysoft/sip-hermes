# Respaldo de PERSONAL con el tiny de Neo (v2.4 §H.3)

**Implantado y verificado el 06-11-2026** con el visto bueno del usuario, incluida la excepción de nftables.

v2.4, matriz «principal caído → acción»: *PERSONAL, HALO apagado/caído → Tiny en Neo; si el tiny también cae →
cola + informar. Jamás cloud.*

## Cómo funciona

1. PERSONAL usa `qwen3.8:27b-64k` en HALO. Si HALO no responde, `sip-halo-wake` pide WOL y espera hasta 210 s.
2. Si la llamada al modelo de HALO falla, Hermes activa el **primer** `fallback_providers`: `qwen3-4b-instruct`
   (proveedor `custom:tiny_neo`, 32K) en `http://172.29.0.1:11435/v1`.
3. `sip-tiny-personal.socket` escucha en la puerta de enlace de la red `sip` (172.29.0.1:11435) y
   `systemd-socket-proxyd` reenvía a llama-swap de Neo (`127.0.0.1:11434`), que sigue solo en loopback.

| Parte | Qué | Dónde |
|---|---|---|
| A | Tiny a 32K, KV q8_0, flash-attention, 1 slot (5,1 GB de VRAM en la GTX 1070) | `../llm-neo/llama-swap.yaml` |
| B | `sip-tiny-personal.socket` y `.service` (`FreeBind`; `IPAddressAllow` solo .200 y .201) | este directorio, `apply.sh` |
| C | nftables `sip-zones`, cadena `input`: `{172.29.0.200, 172.29.0.201} → 172.29.0.1 tcp 11435` | `nftables-sip.candidate.nft`, `apply.sh` |
| D | `providers.tiny_neo` y tiny como primer fallback, en el perfil `personal` de la WebUI y en `config.api.yaml` | `editar-config-fallback.py`, `apply-hermes.sh` |

**Por qué el tiny va primero:** Hermes 0.22.7 solo cambia una vez de proveedor por turno
(«Rebuilt-message restart limit (1) exceeded»). Con el tiny detrás de `gpt-oss:20b` y `qwen3.6:27b`, que están en
el mismo servidor que el principal y caen con él, no se llegaba nunca (primer intento de la prueba).

**Por qué no se regenera `config.api.yaml`:** `../personal-api/make-api-config.sh` fija una lista de herramientas
anterior a `imagen`, `procesar` y `delegation`. Se edita en el sitio (conserva el inodo del montaje).

## Verificado (06-11)

- 32K con un prompt sintético de 14.100 tokens y 4 herramientas: llamada correcta; 48 s en frío y 1,2 s con caché.
- Puerta: la WebUI y la API de PERSONAL llegan (`/v1/models` y chat); RESEARCH y Vaultwarden, no (el
  contador `sip-drop-in` sube).
- **Turno real por la API de PERSONAL con el llama-swap de HALO parado:** `Fallback activated: qwen3.8:27b-64k →
  qwen3-4b-instruct (custom:tiny_neo)`; 11.624 tokens de entrada, 32,5 s; turno de 69 s. Con HALO de vuelta, el
  siguiente turno usó `qwen3.8:27b-64k`.
- Sin probar: un turno por la WebUI (usa el mismo fichero del perfil `personal`) y el caso con HALO apagado de
  verdad (el WOL añadirá hasta 210 s).

## Límites conocidos

- Un 4B es un respaldo, no un sustituto: vale para preguntas y herramientas sencillas, no para tareas largas.
- Con `-np 1`, si PERSONAL usa el tiny mientras trabaja el gestor nocturno, uno espera al otro (el gestor se
  abstiene si se agota su tiempo).
- PERSONAL ve toda la API de llama-swap de Neo, que solo tiene el tiny; `/logs` no guarda contenido.

## Rollback

- D: `sh /root/sip-agent-backups/2026-11-06/tiny-personal/d/rollback.sh`
- B y C: `sh /root/sip-agent-backups/2026-11-06/tiny-personal/bc/rollback.sh`
- A: restaurar `/root/sip-agent-backups/2026-11-06/tiny-personal/llama-swap.yaml-pre` (`root:sip-llm 0640`) y
  reiniciar `llama-swap`.
