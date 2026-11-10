#!/usr/bin/env python3
# Cuarentena de duplicados y basura de un lote (como sip-gestor). Uso: cuarentena-dups.py <json> <ejecutar|simular>
import hashlib, json, subprocess, sys
from pathlib import Path

js, modo = sys.argv[1], sys.argv[2]
d = json.load(open(js))
it = {x["item"]: x for x in d["items"]}
# duplicado -> ítem que se queda (None = basura, se van todos)
QUITAR = {int(k): v for k, v in json.loads(sys.argv[3]).items()}


def sha(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for c in iter(lambda: f.read(1 << 20), b""):
            h.update(c)
    return h.hexdigest()


ok = fallos = 0
for n, keep in QUITAR.items():
    x = it[n]
    p = Path(x["ruta"])
    if p.is_symlink() or not p.is_file() or sha(p) != x["hash"]:
        print(f"#{n}: no coincide o no existe; no se toca"); fallos += 1; continue
    if keep is not None:
        k = it[keep]
        kp = Path(k["ruta"])
        if kp == p or kp.is_symlink() or not kp.is_file() or sha(kp) != x["hash"]:
            print(f"#{n}: el original #{keep} no está intacto; no se toca"); fallos += 1; continue
    motivo = f"{d['lote']} #{n}: " + (f"duplicado de #{keep}" if keep else "basura de torrent")
    if modo != "ejecutar":
        print(f"#{n}: listo ({motivo})"); ok += 1; continue
    r = subprocess.run(["sudo", "-n", "/usr/local/bin/sip-gestor-filegate", "quarantine", str(p), motivo],
                       capture_output=True, text=True, timeout=60)
    salida = (r.stdout + r.stderr).strip()
    if r.returncode == 0 and salida.startswith("OK"):
        print(f"#{n}: en cuarentena · {salida[:120]}"); ok += 1
    else:
        print(f"#{n}: ERROR {salida[:200]}"); fallos += 1
print(f"{modo}: {ok} ok, {fallos} fallos")
