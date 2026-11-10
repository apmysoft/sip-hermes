"""Endurecimiento SIP de config.yaml para Hermes >= 0.22 (05-11). Idempotente; conserva comentarios.

Uso (con el python del venv de Hermes, que trae ruamel.yaml):  python endurecer-config.py <config.yaml>...
Fija valores nuevos por defecto de 0.22.x que chocan con v2.4:
- agent.disabled_toolsets incluye `connections` (la migración 44->45 lo añade a toda lista explícita de
  platform_toolsets; con esto no se añade y el resolutor lo resta al final).
- tools.connectors.enabled: false        (conectores remotos)
- nous.guest: false                      (inferencia de invitado en el portal de Nous = datos a su nube)
- auth.adopt_external_logins: false      (adoptar credenciales de otras CLI)
- security.allow_lazy_installs: false    (instalar paquetes al vuelo)
- updates.check: false                   (sin internet en las zonas; evita reintentos)
- tools.tool_search.enabled: "off"       (herramientas de plugins visibles; menos llamadas al modelo)
Escribe solo si cambia algo, de forma atómica y con el mismo modo y propietario.
"""
import os
import sys
import tempfile

from ruamel.yaml import YAML
from ruamel.yaml.scalarstring import DoubleQuotedScalarString as Q

FIJAR = [
    (("tools", "connectors", "enabled"), False),
    (("nous", "guest"), False),
    (("auth", "adopt_external_logins"), False),
    (("security", "allow_lazy_installs"), False),
    (("updates", "check"), False),
    (("tools", "tool_search", "enabled"), Q("off")),  # entre comillas: `off` suelto es False en YAML 1.1
]


def nodo(d, ruta):
    for k in ruta:
        if k not in d or not hasattr(d[k], "get"):
            d[k] = {}
        d = d[k]
    return d


def endurecer(path):
    y = YAML()
    y.preserve_quotes = True
    y.indent(mapping=2, sequence=4, offset=2)  # estilo de las config SIP (`  - x` bajo la clave)
    with open(path) as f:
        cfg = y.load(f) or {}
    cambios = []
    agent = nodo(cfg, ("agent",))
    dis = agent.get("disabled_toolsets")
    if dis is None:
        agent["disabled_toolsets"] = ["connections"]
        cambios.append("agent.disabled_toolsets = [connections]")
    elif "connections" not in dis:
        dis.append("connections")
        cambios.append("agent.disabled_toolsets += connections")
    for ruta, valor in FIJAR:
        padre = nodo(cfg, ruta[:-1])
        if padre.get(ruta[-1]) != valor:
            cambios.append(f"{'.'.join(ruta)}: {padre.get(ruta[-1])!r} -> {valor!r}")
            padre[ruta[-1]] = valor
    if cambios:
        st = os.stat(path)
        fd, tmp = tempfile.mkstemp(dir=os.path.dirname(path), prefix=".cfg-")
        with os.fdopen(fd, "w") as f:
            y.dump(cfg, f)
        os.chmod(tmp, st.st_mode & 0o7777)
        try:
            os.chown(tmp, st.st_uid, st.st_gid)
        except PermissionError:
            pass
        os.replace(tmp, path)
    print(path, "->", "; ".join(cambios) if cambios else "sin cambios")


if __name__ == "__main__":
    for p in sys.argv[1:]:
        endurecer(p)
