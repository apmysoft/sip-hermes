# Almacenamiento acotado del worker HALO

Instalado y probado en HALO el 2026-10-08. El ext4 raíz de HALO no anuncia las funciones
quota/project; quota, setquota y repquota no están disponibles. Todas las escrituras
del sandbox ocurren bajo /srv/hermes-worker (home, workspace y tmp).

Mecanismo instalado: archivo ext4 de 32 GiB preasignados, root:root 0600, bajo
/var/lib/sip-hermes-worker (root:root 0700). mkfs.ext4 debe usar nodiscard para
conservar la preasignación, y -m 0 para no reservar bloques a root dentro del worker.
El espacio útil será menor que 32 GiB por los metadatos. Límite agregado de bloques
e inodos por capacidad del filesystem, no una cuota por archivo/directorio.
El archivo debe conservar su tamaño; no es un recurso accesible por el worker.

worker-storage.mount.in se instala bajo /etc/systemd/system con el nombre que
devuelva systemd-escape --path --suffix=mount /srv/hermes-worker. Montaje ext4
loop,nodev,nosuid y habilitación en multi-user.target. No depende de ssh.service:
un fallo del montaje debe impedir ejecutar el worker mediante su launcher, sin
bloquear el acceso administrativo del usuario. No se toca fstab ni el ext4 raíz.

El launcher comprueba mountpoint en el host antes de Bubblewrap y devuelve 126
si falta el montaje. El mountpoint es gestionado por root; la comprobación no
verifica el tamaño/identidad del filesystem, que debe comprobarse al instalar.
No instalar el nuevo launcher hasta que el filesystem esté montado y migrado.

Instalación manual por etapas: comprobar que no hay sesiones worker activas;
guardar copia root-only de datos, launcher y configuración previa; crear imagen;
montarla temporalmente y copiar home/workspace/tmp preservando propietarios y
permisos; comparar contenido antes de desmontar temporal; instalar/habilitar unit;
comprobar montaje y datos; instalar launcher; probar SSH y denegación sin montaje.
No borrar ni mover los directorios anteriores: el montaje los oculta y siguen
disponibles para rollback. Evitar escrituras simultáneas durante la migración.

Validación realizada: imagen 34359738368 bytes root:root 0600, directorio 0700,
UUID <uuid-del-volumen>. Unit validado, instalado 0644,
active/mounted y enabled; montaje ext4 con UUID esperado. Copia rsync checksum y
metadatos sin diferencias; home/workspace/tmp 0700 UID/GID 995:982. Launcher
instalado 0755 e idéntico al repositorio. Testigo sip-storage-test-20261008.txt
escrito 0600 y leído entre conexiones SSH en /workspace de 32 GiB.

Rechazo 126 sin montaje probado en namespace privado; montaje real intacto.
Ensayo ext4 de 32 MiB devuelve ENOSPC al escribir como worker; conservado y
desmontado en /var/tmp/sip-worker-enospc.gVUl7xCw. No se llenó el filesystem
operativo ni se midió rendimiento. Backup previo root-only:
/root/sip-worker-prestorage.SrrKVfZE; originales conservados bajo el montaje.
Reboot y cobertura de backups del nuevo filesystem pendientes.

Rollback requiere acordar interrupción de sesiones, restaurar launcher previo,
deshabilitar/desmontar el unit y recuperar datos que hayan cambiado desde la
migración. Los directorios ocultos conservan solo el estado anterior, no las
escrituras realizadas dentro de la imagen. No eliminar automáticamente imagen,
unit, backups ni datos y no restaurar datos antiguos sin revisión.
