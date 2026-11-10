# Actualizaciones (v2.4 Fase 9)

Estado a 02-11-2026: **desplegado y verificado** en Neo. Propuesta aprobada por el usuario el 01-11 y
confirmada el 02-11.

## Política

| Qué | Cómo |
| --- | --- |
| Parches de seguridad de Ubuntu en Neo | Automáticos (`unattended-upgrades`), sin reinicio |
| Núcleo, NVIDIA, Docker/containerd en Neo | Excluidos; aparecen en el informe semanal |
| Paquetes de Mint y de repositorios de terceros | Manual (no entran en los automáticos) |
| HALO (Ubuntu 24.04) | Se deja su configuración por defecto: seguridad de Ubuntu, sin reinicio |
| Imágenes Docker | Informe semanal; se actualizan servicio a servicio con aprobación |
| Hermes Agent y WebUI | Informe semanal; imágenes propias, actualización con pruebas de contrato |

## Neo: `unattended-upgrades`

Neo es Linux Mint 22.3 (base Ubuntu noble): el `50unattended-upgrades` del paquete usa
`${distro_id}=Linuxmint`, que admitiría Mint. `52sip-unattended-upgrades` vacía sus listas (`#clear`) y
solo admite `origin=Ubuntu,archive=noble-security`, con exclusiones `linux-`, `.*nvidia.*`, `docker`,
`containerd`, sin reinicio automático y sin borrar dependencias. Instalación: `apply-neo.sh` (copia previa
de `/etc/apt/apt.conf.d` en `/root/sip-agent-backups/<fecha>/`; rollback en su cabecera).

## Informe semanal

`sip-updates-report.timer` (sábados a las 10:00), sin LLM, no aplica nada. Instalación: `apply-report.sh`.
Prueba sin enviar: `/usr/local/sbin/sip-updates-report.py --dry-run`.

- apt pendiente, separando lo excluido de los automáticos; parches instalados en la semana; reinicio
  pedido.
- Docker: compara el digest local de la etiqueta de origen (`RepoTags`) con el del registro (`buildx
  imagetools`). Una consulta fallida cuenta como «sin comprobar», nunca como «al día». Las imágenes
  construidas en Neo (`hermes-*`, `ant-and-hopper-*`) no se consultan.
- Hermes Agent (`hermes --version`) y WebUI (primera versión del CHANGELOG) frente a la última release
  en GitHub.

## Verificado el 02-11-2026

- `apply-neo.sh`: configuración efectiva con solo `noble-security` y las cuatro exclusiones;
  `unattended-upgrade --dry-run`: nada que instalar ahora.
- Informe: ejecución real del servicio y aviso `enviado`; 15 servicios con versión nueva de su etiqueta;
  Hermes Agent v0.21.3 frente a v0.22.5, WebUI v0.52.76 frente a v0.52.544.
- Docker Hub devolvió `429 Too Many Requests` tras las pruebas repetidas (cupo anónimo); esas imágenes
  salen como «sin comprobar». Una vez por semana no debería alcanzarse el cupo.

## Pendiente

- ~~Repositorio de Docker de Neo~~: desde el 02-11, `linux/ubuntu noble` (misma clave) y paquetes
  reinstalados desde él (Docker 29.9.2, containerd 2.4.2), verificado.
- ~~`torproxy`~~: sustituido el 02-11 por `dockurr/tor` fijada por digest (`sip-config/torproxy/apply.sh`).
- HALO no entra en el informe: Neo no tiene acceso a HALO como administrador.
