# Vaultwarden — gestor de secretos SIP

Reapertura del aplazamiento del Bloque 5 (27-10-2026): necesidad concreta de
almacén seguro (passphrase de backups cifrados de `.hermes`, Fase 2) y de
destino para la migración de contraseñas de Firefox/Chrome a infra propia.

## Acceso

- URL: `https://neo.${TAILNET_DOMAIN}` (TLS por `tailscale serve`;
  MagicDNS + HTTPS Certificates deben estar habilitados en la consola).
- El contenedor solo escucha en `127.0.0.1:8222` del host; no hay exposición
  LAN ni WAN. La ACL `usuario→sip:*` ya cubre el acceso.
- Comprobación de salud: `curl http://127.0.0.1:8222/alive` en Neo.

## Secretos

- `/root/sip-vaultwarden.env` (root 0400): `ADMIN_TOKEN` (hash argon2 en
  formato PHC). **Ojo:** Docker Compose interpola variables en `env_file`:
  las `$` del PHC deben ir **dobladas (`$$`)** en este fichero o el contenedor
  recibe el valor vacío ("invalid admin token"). Verificar tras regenerar:
  `docker exec vaultwarden env | grep ^ADMIN_TOKEN | cut -c1-14` → `$argon2id…`
  (y login de prueba en `/admin`).
- `/root/sip-vaultwarden-admin-token.txt` (root 0400): token admin en claro,
  **temporal** — guardarlo en Vaultwarden tras el alta y borrar el fichero.
- Master password: lo crea el usuario; registrar en `ROTACION.md`.
- Regenerar el ADMIN_TOKEN (ej. rotación): generar PHC con
  `python3 -c "from argon2 import PasswordHasher as P; print(P().hash(open('/root/sip-vaultwarden-admin-token.txt').read().strip()))"`
  y escribirlo con `$$`, re-crear el contenedor.

## Operación

- Deploy: `docker compose -f sip-config/vaultwarden/docker-compose.yml up -d`.
- Logs: `docker logs vaultwarden`.
- serve: `docker exec tailscale tailscale serve --bg --https=443 http://127.0.0.1:8222`;
  revertir con `docker exec tailscale tailscale serve --https=443 off`.
- Backup: `db.sqlite3` del volumen `sip-vaultwarden_vw-data`; copia cifrada
  puntual con la passphrase de backups (mismo esquema age que `.hermes`);
  cobertura periódica en Kopia → Fase 10.

## Migración de contraseñas (guión del usuario)

1. **Firefox**: `about:logins` → ⋯ → *Exportar contraseñas* (CSV).
   **Chrome**: `chrome://password-manager/settings` → *Exportar contraseñas*.
2. En la web de Vaultwarden: *Ajustes* → *Importar datos* → formato Bitwarden
   (CSV) → seleccionar el fichero.
3. Revisar duplicados y borrados; comprobar que las entradas abren.
4. **Borrar el CSV** (`shred -u` o mover a papelera y vaciar). El CSV existe
   en claro solo durante este proceso: no subirlo a nada, hacerlo en local.
5. Desactivar el gestor integrado de los navegadores y la sync de contraseñas
   de Google/Mozilla (ya no son la fuente de verdad).

## Rollback

`docker compose down` (volumen conservado), `tailscale serve --https=443 off`,
y retirar los ficheros de `/root`. Sin impacto en otros servicios.

## Acceso desde el propio Neo (03-11)

Neo no resuelve `neo.${TAILNET_DOMAIN}`: Tailscale corre en contenedor y el host no usa MagicDNS. La
extensión de Firefox en Neo daba «NetworkError». Arreglo: `${NEO_TAILNET_IP} neo.${TAILNET_DOMAIN}` en
`/etc/hosts` (copia previa en `/root/sip-agent-backups/2026-11-03/hosts/`). Rollback: quitar la línea.
