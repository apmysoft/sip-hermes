# Runbook M.14: reconstrucción de Neo e integridad de binarios

Neo es el punto único de fallo aceptado (v2.4). Este runbook dice qué hace falta para levantar SIP en un
Neo nuevo, en qué orden, y qué falta hoy para que se pueda.

## Qué hay y dónde (03-11-2026)

| Pieza | Origen para reconstruir | ¿Cubierto hoy? |
| --- | --- | --- |
| Código, unidades, scripts y configs sin secretos | Este repositorio (GitHub) | ✅ |
| Datos personales (PARA) | Kopia, `${PARA_ROOT}`, diario 22:00 | ✅ (O11 sin hacer) |
| Estado de Hermes (`.hermes` de las tres zonas: sesiones, memoria, skills) | `sip-estado-*.tar.gz.age` (ver abajo) | 🟡 desde el 03-11; entra en Kopia con el snapshot de las 22:00 (sin comprobar en Kopia) |
| DB de LiteLLM (gasto, claves virtuales) | Copia cifrada diaria en `/var/backups/sip-litellm/`; la última va en `sip-estado` | 🟡 ídem |
| Log de auditoría de filegate | `/var/log/filegate/audit.log`, en `sip-estado` | 🟡 ídem |
| Cuarentena y staging | `${STAGING_ROOT}`, en `sip-estado` | 🟡 ídem |
| Directorios de despliegue (`~/sip-fase7-*`, `/opt/sip-litellm`) | Repo + `.env` | 🟡 los `.env` solo están en Neo |
| Secretos (`/root/*.env`, tokens de filegate, claves SSH) | Ninguno: se regeneran (runbook M.13) | — por diseño |

`sip-kopia-estado.timer` (21:15, root) deja cada noche
`${PARA_ROOT}/01_proyectos/Implementación SIP + Hermes agent/_copias-sip-estado/sip-estado-<fecha>.tar.gz.age`
(usuario 0700/0600, sin ACL de filegate ni `hermes-ro`; conserva 3) y KopiaUI lo copia a las 22:00. Cifrado
con la passphrase de `/root/sip-hermes-backup.pass` (también en el gestor del usuario: sin ella no se
restaura). Ver `kopia/`. O11 pendiente.

## Orden de restauración

1. Ubuntu, usuarios y grupos de `sip-config/IDENTIDADES.md` (UID/GID fijos: los volúmenes dependen de
   ellos). Discos con sus montajes; LUKS si se aplica.
2. Tailscale (a mano): unir el equipo y comprobar que la política del repo (`sip-config/tailscale/`)
   está aplicada en la consola.
3. Docker desde el repositorio de Ubuntu noble; `nftables` de `sip-config/filegate/nftables-sip.nft` y
   los firewalls por zona (`*/apply-firewall.sh`).
4. filegate (`sip-config/filegate/`), tokens nuevos y la integridad de abajo. Suite `test-filegate.sh`.
5. Restaurar desde Kopia el último `sip-estado-*.tar.gz.age`; `age -d -o /tmp/e.tar.gz <fichero>` y
   `tar -xzpf /tmp/e.tar.gz -C /var/tmp` (como root: conserva UID y modos). Copiar
   `sip-estado/{personal,coding,research}` a los `_data` de sus volúmenes, `filegate-log` a
   `/var/log/filegate`, `almacen-extra` a `${STAGING_ROOT}` y restaurar la DB de LiteLLM con la cabecera
   de `sip-litellm-backup.sh`. Con la red de las zonas aún parada.
6. LiteLLM (`/opt/sip-litellm`) con claves nuevas → RESEARCH → CODING → gateway → WebUI. Imágenes **por
   digest**, las del repo.
7. Servicios del host: `notify`, `wol`, `gestor-entrada`, `resumen`, `actualizaciones`, `modelos`,
   `memoria`, `traspaso`, `operacion/retencion`, cada uno con su `apply*.sh`.
8. Pruebas: O5, O8, O13 y un turno por zona. Anotar el tiempo total (RTO).

## Integridad de binarios

- Todo lo que ejecuta o carga root es root:root (755 los ejecutables, 644 las unidades). Comprobación:

  ```sh
  find /usr/local/bin /usr/local/sbin /etc/systemd/system -maxdepth 2 \( ! -user root -o -perm /022 \) ! -type l
  ```

  Debe salir vacío. El 03-11 salieron 5 ficheros de `usuario` (corregidos con `integridad/apply.sh`).
- filegate verifica su sha256 antes de cada conexión (`ExecStartPre` de
  `/etc/systemd/system/filegate@.service.d/10-integridad.conf`) contra `/etc/sip-integridad/filegate.sha256`
  (root, 0600). **Al actualizar filegate a propósito:** instalar el binario y regenerar el manifiesto con
  `sha256sum /usr/local/bin/filegate.sh > /etc/sip-integridad/filegate.sha256`. Si no, filegate no
  arranca y no responde a nadie.
- El gateway es un contenedor fijado por digest: su integridad es el digest, no un sha256 en el host.
