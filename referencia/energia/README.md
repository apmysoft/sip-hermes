# Apagado de HALO por inactividad y a petición (05-11-2026)

Es la implantación de v2.4 §467 con las decisiones del usuario del 05-11:
- **apagado completo**, nunca suspensión;
- **automático tras 1 h** sin nada que lo impida, **con aviso por Telegram** (así el usuario puede apagar
  también el enchufe Tapo y las pantallas);
- no se apaga si hay **cualquier agente trabajando** (Claude Code, Codex, Copilot... en VS Code o en
  terminal);
- un navegador abierto sin más no lo impide;
- el apagado a petición, **solo desde PERSONAL**, informa antes de lo que está haciendo el equipo.

Despertar: sin cambios (WOL desde Neo, 24 s). Con el enchufe Tapo apagado el WOL no funciona. Al
encenderlo, HALO arranca solo (BIOS «restaurar al volver la corriente»).

## Cómo funciona

```
Neo (sip-wol)                                    HALO
sip-energia-auto.timer, cada 5 min ─ssh─────►  orden forzada (sip-energia) ─polkit─► sip-actividad (root)
  60 min sin bloqueos → apagar-auto ─ssh─────►  sip-apagar-auto (root): comprueba de nuevo y apaga en 20 s
  aviso «energia-» por sip-notify
PERSONAL → /workspace/_energia ─► sip-energia.path: estado | proponer (código por Telegram) | confirmar
  confirmar → apagar-usuario <huella> ─ssh───►  sip-apagar-usuario (root): solo si la huella coincide
```

**Qué impide el apagado automático** (`sip-actividad.py`, cada muestra):

| Clave | Cuándo |
|---|---|
| `teclado` | Teclado o ratón usados en los últimos 10 min (GNOME, `IdleMonitor`) |
| `audio` | Flujo de audio en marcha (PipeWire) de un programa que **no es un navegador**. Desde el 06-11 los navegadores no cuentan: una pestaña de AI Studio con la que se había enviado una nota de voz dejó un flujo «running» en silencio que bloqueó el apagado toda la tarde. Medir el nivel real con `pw-record` daba ceros también con sonido (2 intentos, regla 10). Contrapartida: una película en el navegador de más de 1 h sin tocar nada podría cortarse |
| `agente-*` | Proceso de un agente vivo y, además, su sesión escrita en los últimos 15 min (Claude Code, Codex, Gemini, Qwen Code, OpenCode, Copilot), comandos hijos en marcha o CPU |
| `cpu` | Programas del usuario por encima del 10 % de un núcleo (VS Code, compilaciones, renders). No cuentan los navegadores ni el escritorio (`gnome-shell`, PipeWire...) |
| `gpu` | Algo cargado en llama-swap (`/running`: modelo, Whisper-GPU, ComfyUI, embeddings) |
| `whisper` | Whisper de CPU transcribiendo |
| `ssh` | Sesión remota de cualquier usuario salvo `sip-energia` |
| `worker` | Procesos de `hermes-worker` (CODING trabajando en HALO) |

Solo informativo: programas abiertos (Firefox, VS Code, LibreOffice...) y agentes abiertos sin actividad.
**Privacidad:** solo nombres de programa y tiempos. Nunca títulos de ventana, rutas ni contenido; de las
sesiones de los agentes solo se mira la fecha de modificación.

**La hora sin actividad es continua y observada.** Cualquier bloqueo, o un hueco de más de 15 min sin
muestras (por ejemplo, Neo apagado), la pone a cero. Si Neo no responde, HALO no se apaga.

**A petición:** `proponer` guarda la huella (las claves de bloqueo que se le enseñan al usuario) y manda un
código de 6 cifras por Telegram (tema «Peticiones»). Con el código, la decisión del usuario manda aunque haya
algo activo, porque lo ha visto. Si al confirmar las claves son otras, no apaga y hay que proponer de nuevo.
El código caduca a los 10 min, admite 3 intentos y como máximo 10 fallos al día. Igual que el puente de stacks.

## Seguridad

- **Clave `sip-energia@neo`** (ROTACION.md):
  - con `from=` Neo, `command=` y `restrict` (sin terminal, reenvíos ni agente);
  - la orden forzada solo admite `estado`, `apagar-auto` y `apagar-usuario <16 hex>`;
  - la clave de host de HALO está fijada en Neo (`StrictHostKeyChecking=yes`);
  - no se ha tocado `sshd_config`.
- **Polkit `51-sip-energia.rules`:** `sip-energia` solo puede hacer `start` de las tres unidades oneshot de
  root. Las tres deciden por sí mismas, y la de apagado vuelve a tomar la muestra.
- **Unidades de Neo como `sip-wol`:** red limitada a `${HALO_TAILNET_IP}`, sin capacidades, y escritura solo en
  `_energia` y en la bandeja de avisos.
- **Puente:** el contenido de las peticiones solo elige una de tres acciones. Se abre con `O_NOFOLLOW` y como
  fichero regular, y la petición se retira siempre.

## Ficheros

| Fichero | Destino |
|---|---|
| `halo/sip-actividad.py` | HALO `/usr/local/sbin/` |
| `halo/sip-actividad.service`, `halo/sip-apagar-auto.service`, `halo/sip-apagar-usuario.service` | HALO `/etc/systemd/system/` (sin `enable`) |
| `halo/orden` | HALO `/usr/local/lib/sip-energia/orden` |
| `halo/51-sip-energia.rules` | HALO `/etc/polkit-1/rules.d/` |
| `halo/sip-energia.tmpfiles` | HALO `/etc/tmpfiles.d/sip-energia.conf` (`/run/sip-energia`, `/run/sip-energia-pet`) |
| `neo/sip-energia.py` | Neo `/usr/local/sbin/` |
| `neo/sip-energia-auto.{service,timer}`, `neo/sip-energia.{service,path}` | Neo `/etc/systemd/system/` |
| `neo/halo-energia/SKILL.md` | skill de PERSONAL (raíz y perfil `personal`) |

Instalación:
1. En Neo: `sudo sh neo/apply.sh clave` imprime la clave pública.
2. En HALO: `sudo sh halo/apply.sh <pub>`.
3. En Neo: `sudo sh neo/apply.sh instalar "${HALO_TAILNET_IP} ssh-ed25519 …"`.

Copias previas y `rollback.sh` en `/root/sip-agent-backups/<fecha>/energia-{halo,neo}/` de cada equipo.

## Verificado (05-11)

- Muestra real con el usuario trabajando: «Claude Code trabajando», «programas del usuario usando CPU» y
  «teclado en uso». Codex y Copilot salen abiertos sin actividad, y Firefox solo como información. La
  conexión de Neo no cuenta como sesión remota.
- Desde Neo, `sip-wol` sin sesión:
  - `estado` responde;
  - una orden no permitida da `orden no permitida`;
  - la clave no da terminal;
  - `apagar-auto` con bloqueos da `no procede`;
  - `apagar-usuario` con otra huella da «ha cambiado»;
  - una huella mal formada se rechaza.
- `sip-energia-auto` registra cada 5 min `HALO: N bloqueo(s), M/60 min`.
- Puente desde el contenedor de PERSONAL (uid 1000):
  - `estado` responde;
  - `proponer` envía el código por Telegram (se anuló después);
  - `confirmar` con un código erróneo se rechaza.
- Turno real de PERSONAL por `sip-gateway` («¿qué está haciendo HALO?»): usó el puente (`estado`) y
  respondió en 44 s.
- Decisión de apagado simulada (muestra fija y apagado sustituido): apaga con 60 min y sin bloqueos, no a
  los 59 min, no con un agente trabajando; a petición, solo con la misma huella.
- Ningún fichero huérfano con el uid y gid 997/984, que antes eran de `ollama` y ahora tiene `sip-energia`.

**Apagado a petición real ✅ (06-11, 00:01):** el usuario lo pidió a PERSONAL y dio el código; HALO se apagó y volvió
a arrancar a las 00:03 sin unidades fallidas. **Sin verificar:** el apagado automático (la noche del 06-11).

## Registro

`journalctl -u sip-energia-auto` (Neo) apunta en cada consulta qué bloquea, p. ej. `HALO: 3 bloqueo(s), 0/60 min sin actividad [agente-Claude Code, cpu, teclado]` (desde el 06-11).

## Ajustes pendientes

- El umbral de CPU (10 % de un núcleo) no se ha medido con VS Code abierto y sin hacer nada. Si impide apagar
  sin motivo, `journalctl -u sip-energia-auto` muestra cuántos bloqueos hay, y el estado de HALO
  (`/run/sip-energia/estado.json`) dice cuáles.
