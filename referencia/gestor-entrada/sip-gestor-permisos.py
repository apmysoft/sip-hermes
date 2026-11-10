#!/usr/bin/env python3
"""sip-gestor-permisos.py — da lectura de grupo a las peticiones de Hermes antes de que las lea el puente.

La herramienta de ficheros de Hermes crea con modo 0600 explícito: el ACL por defecto no sirve y
sip-gestor no puede leer la petición. Esto corre como usuario (uid 1000, el mismo usuario que Hermes en el
contenedor: no da más acceso del que Hermes ya tiene) justo antes de sip-gestor-bridge.service, y solo
añade g+r a ficheros regulares *.json de requests/ cuyo dueño es este usuario y cuyo grupo es sip-gestor.

Sin seguir enlaces: cada componente desde ${DOCKER_DATA}/hermes se abre con O_NOFOLLOW y los ficheros
con O_NOFOLLOW + fchmod.
"""
import grp
import os
import stat
import sys

BASE = "${DOCKER_DATA}/hermes"
CAMINO = ("workspace", "_gestor", "requests")
FLAGS_DIR = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW


def main():
    gid = grp.getgrnam("sip-gestor").gr_gid
    dfd = os.open(BASE, FLAGS_DIR)
    for parte in CAMINO:
        nuevo = os.open(parte, FLAGS_DIR, dir_fd=dfd)
        os.close(dfd)
        dfd = nuevo
    hechos = 0
    for nombre in os.listdir(dfd):
        if nombre.startswith(".") or not nombre.endswith(".json"):
            continue
        try:
            fd = os.open(nombre, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=dfd)
        except OSError:
            continue
        try:
            st = os.fstat(fd)
            if (stat.S_ISREG(st.st_mode) and st.st_uid == os.getuid() and st.st_gid == gid
                    and not st.st_mode & stat.S_IRGRP):
                os.fchmod(fd, stat.S_IMODE(st.st_mode) | stat.S_IRGRP)
                hechos += 1
        finally:
            os.close(fd)
    os.close(dfd)
    if hechos:
        print(f"lectura de grupo en {hechos} petición(es)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
