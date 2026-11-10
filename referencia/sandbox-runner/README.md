# Runner aislado de ejecución — red `sandbox`

Contenedor SSH endurecido, unido **solo** a la red Docker `sandbox`
(`172.30.0.0/24`, `internal=true`), sin puertos publicados. Punto de
ejecución de código no confiable con egress de red cero. Es la alternativa al
candidato "backend Docker nativo de Hermes" registrado en 99-NOTAS, que
requería montar `docker.sock` en el WebUI (regla 5 de v2.4: prohibido).

## Fronteras de aislamiento

1. **Red:** `internal=true` (Docker no NATa esa red hacia fuera) + drop total
   del origen 172.30/24 en `table inet sip-zones` + el propio bridge Docker
   descarta lo que no sea de la subred. Doble candado registrado en 1B.
2. **Excepción de entrada:** con la confirmación del usuario, nftables admite
   `sip (172.29) → sandbox (172.30) tcp/2222`, para que Hermes llegue por SSH.
   El runner **no puede iniciar** ninguna conexión (drop de origen 172.30).
3. **Contenedor:** `cap_drop: [ALL]` con una única reposición (`NET_ADMIN`, necesaria
   para la ruta de vuelta a `sip`; ver `entrypoint.sh`), `no-new-privileges`,
   `read_only` con tmpfs en `/run` y `/tmp`, límites de mem/CPU/pids, usuario
   `sandbox` (UID 1001) sin sudo. sshd: solo clave pública, sin forwarding, sin
   TTY, sin túnel, sin root, `AllowUsers sandbox`, puerto 2222 (sin
   CAP_NET_BIND_SERVICE no se puede bindear <1024 con todas las caps caídas).

## Ficheros

- `Dockerfile` — debian bookworm-slim **pin por digest** + openssh-server/client.
- `sshd_config` — endurecimiento descrito arriba.
- `entrypoint.sh` — host keys ed25519 persistentes en volumen (primer arranque
  las genera), `/run/sshd` en tmpfs, sshd en primer plano (`-D -e`).
- `docker-compose.yml` — servicio `runner`, red `sandbox` externa, sin `ports`.

## Volúmenes

- `runner-workspace` → `/workspace` (persistencia del trabajo; UID 1001).
- `runner-ssh-hostkeys` → `/etc/ssh/hostkeys` (identidad estable entre recreaciones).
- `runner-authkeys` → `/home/sandbox/.ssh` (solo lectura); contiene
  `authorized_keys` con la clave pública `id_ed25519_sandbox_runner.pub`.

## Cableado previsto en Hermes (Bloque 4b, aún no activado)

El backend SSH de Hermes apuntaría al runner (`sandbox:2222`, usuario
`sandbox`) en el config del perfil que se decida. **Pendiente conocido:** el
adaptador desplegado (`/opt/sip-ssh-client/bin/ssh`) fija
`IdentityFile=…/id_ed25519_halo_worker`; para usar el runner hará falta una
variante del adaptador que seleccione `id_ed25519_sandbox_runner`. El ensayo
de este bloque usa la clave directamente, sin adaptador.

## Hallazgos Bloque 4a · tres capas de filtrado cruzado

El SYN **sip → sandbox:2222** debe atravesar tres capas; la excepción prevista
solo en `inet sip-zones` no bastaba:

1. **`table ip raw` PREROUTING (Docker 29, prioridad raw):** anti-spoofing por
   IP de contenedor **con puertos publicados** (`daddr 172.29.0.2 iifname !=
   br-sip drop`). Bloquea que el runner hable con la IP del WebUI. No afecta al
   SYN hacia el runner (no publica puertos) ni al flujo Ollama (masquerade:
   el return va a `${NEO_TAILNET_IP}` y conntrack de-NATea después de raw).
   **No requiere excepción** para este flujo (verificado).
2. **`inet sip-zones` forward (priority −50):** la excepción
   `sip → 172.30/24 tcp dport 2222 accept` está versionada en
   `sip-config/filegate/nftables-sip.nft`.
3. **`ip filter` FORWARD → DOCKER-INTERNAL (Docker, priority 0):**
   `saddr != 172.30/24 oifname br-sandbox drop` — mata el SYN porque el filtro
   corre antes del masquerade y el origen aún es 172.29.x. Solución: ACCEPT en
   **`DOCKER-USER`** (cadena vacía que Docker ejecuta la primera en filter
   FORWARD y nunca vacía; un ACCEPT ahí termina el hook y salta
   DOCKER-INTERNAL). Regla:
   `iptables -t filter -I DOCKER-USER 1 -s 172.29.0.0/24 -d 172.30.0.0/24 -p tcp --dport 2222 -j ACCEPT`.
   Es runtime: la reaplica `sip-docker-user-ssh.service` tras `docker.service`
   (script idempotente `sip-docker-user-ssh.sh`).

Datos del flujo real: el SYN sale de sip **masqueradeado** a `172.30.0.1`; el
runner ve conexiones desde `172.30.0.1` y el SYN-ACK vuelve a esa IP, donde
conntrack lo de-NATea en PREROUTING y se reenvía al cliente. Nota operativa:
`nft -f <fichero>` con una tabla existente **añade** reglas duplicadas en vez
de sustituir; para recargar `sip-zones` hay que vaciar las cadenas primero.

## Verificación (Bloque 4a)

- Desde dentro del runner: todo egress falla (WAN, DNS, 172.29, tailnet) y el
  contador `sip-drop-sandbox` crece.
- Desde un contenedor desechable en la red `sip` con la clave RO: SSH al
  runner OK (`id` → UID 1001), workspace persistente; sin clave → rechazo
  publickey; forwarding/TTY rechazados por sshd.
- `hermes-webui` no se recrea ni se toca su config en este bloque.

## Rollback

```bash
cd ~/sip-inventario/sip-config/sandbox-runner && docker compose down
sudo nft -f /root/sip-agent-backups/2026-10-26/bloque4a-runner/nftables-sip.nft.bak
# retirar la clave del volumen Hermes y la línea de ROTACION.md si se creó
```

Copia previa del bloque: `/root/sip-agent-backups/2026-10-26/bloque4a-runner/`
(config.yaml, composes y ruleset nft en ejecución, con SHA256SUMS).
