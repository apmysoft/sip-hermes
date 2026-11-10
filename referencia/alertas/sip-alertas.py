#!/usr/bin/env python3
"""Alertas de operación de SIP (v2.4 M.12). Cada hora, deterministas, sin LLM ni contenido personal.

Comprueba disco y RAM (80/90 %), egresos bloqueados de PERSONAL (hermes-webui), cuarentena por encima del
umbral, ráfagas de WOL, cuota cloud (429 en LiteLLM y claves por encima del 80 % de su presupuesto),
logins fallidos (WebUI de PERSONAL y CODING, Vaultwarden), SQLite de las zonas (bloqueos y WAL, S.12) y fallos del tiny de Neo (24 h). Avisa por la bandeja de sip-notify solo cuando
una alerta aparece o sube de nivel, y la recuerda como mucho una vez al día; avisa también cuando se
resuelve. --dry-run imprime todo sin avisar ni guardar estado.
"""
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

OUTBOX = Path(os.environ.get("SIP_NOTIFY_OUTBOX", "/var/lib/sip-notify/outbox"))
STATE = Path(os.environ.get("SIP_ALERTAS_STATE", "/var/lib/sip-alertas/estado.json"))
DISCOS = ["/", "${PARA_ROOT}", "${DOCKER_DATA}", "${STAGING_ROOT}", "${BACKUP_VAULT}", "${COLD_STORAGE}"]
CUARENTENA = Path("${STAGING_ROOT}/_cuarentena")
WOL_LOG = Path("/var/lib/sip-wol/sent.log")
UMBRAL = {
    "egresos_personal_h": 20,       # paquetes cortados de hermes-webui en 1 h
    "cuarentena_entradas": 100,
    "cuarentena_bytes": 1 << 30,
    "wol_h": 3,                     # el servicio corta en 5/h y ya avisa de rate_limited
    "llm_429_h": 10,
    "presupuesto": 0.8,
    "logins_fallidos_h": 5,
    "wal_bytes": 256 << 20,
}
VOLUMENES = Path("${DOCKER_DATA}/docker_root/volumes")
RECORDAR = 86400


def run(*cmd, stdin=None):
    return subprocess.run(cmd, input=stdin, capture_output=True, text=True, timeout=60).stdout


def montado(p):
    return run("findmnt", "-no", "TARGET", "--target", p).strip() == p or p == "/"


def discos():
    res = {}
    for p in DISCOS:
        if os.path.isdir(p) and montado(p):
            u = shutil.disk_usage(p)  # statvfs: no lee contenido
            pct = round(100 * u.used / (u.used + u.free))  # como df: sin los bloques reservados a root
            res[f"disco {p}"] = (2 if pct >= 90 else 1 if pct >= 80 else 0, f"{pct} % ocupado")
    return res


def ram():
    m = dict(l.split(":", 1) for l in Path("/proc/meminfo").read_text().splitlines())
    tot, disp = int(m["MemTotal"].split()[0]), int(m["MemAvailable"].split()[0])
    pct = round(100 * (tot - disp) / tot)
    return {"RAM": (2 if pct >= 90 else 1 if pct >= 80 else 0, f"{pct} % en uso")}


def ip_contenedor(nombre, red):
    return run("docker", "inspect", "-f", f'{{{{(index .NetworkSettings.Networks "{red}").IPAddress}}}}', nombre).strip()


def egresos_personal():
    ip = ip_contenedor("hermes-webui", "sip")
    k = run("journalctl", "-k", "--since", "-1h", "--no-pager", "-o", "cat")
    n = sum(1 for l in k.splitlines() if "sip-drop-sip " in l and f"SRC={ip} " in l) if ip else -1
    if n < 0:
        return {"egresos PERSONAL": (1, "no se pudo leer la IP de hermes-webui")}
    return {"egresos PERSONAL": (1 if n >= UMBRAL["egresos_personal_h"] else 0, f"{n} paquetes cortados en 1 h")}


def cuarentena():
    entradas = [p for p in CUARENTENA.iterdir()] if CUARENTENA.is_dir() else []
    tam = sum(f.stat().st_size for f in CUARENTENA.rglob("*") if f.is_file()) if entradas else 0
    alto = len(entradas) >= UMBRAL["cuarentena_entradas"] or tam >= UMBRAL["cuarentena_bytes"]
    return {"cuarentena": (1 if alto else 0, f"{len(entradas)} entradas, {tam // (1 << 20)} MiB")}


def wol():
    t = time.time()
    n = sum(1 for x in WOL_LOG.read_text().split() if t - float(x) < 3600) if WOL_LOG.exists() else 0
    return {"WOL": (1 if n >= UMBRAL["wol_h"] else 0, f"{n} envíos en 1 h")}


def cuota():
    errs = subprocess.run(["docker", "logs", "--since", "1h", "sip-litellm"], capture_output=True, text=True,
                          timeout=60)
    texto = errs.stdout + errs.stderr  # LiteLLM escribe sus errores en stderr
    n429 = sum(1 for l in texto.splitlines() if "429" in l or "RateLimitError" in l)
    sql = ('select key_alias, spend, max_budget from "LiteLLM_VerificationToken" '
           'where max_budget is not null and max_budget > 0')
    out = run("docker", "exec", "-i", "sip-litellm-db", "sh", "-c",
              'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -AtF"|"', stdin=sql)
    altas = [f"{a} {float(s):.2f}/{float(m):.2f} $" for a, s, m in (l.split("|") for l in out.splitlines() if l.count("|") == 2)
             if float(s) >= UMBRAL["presupuesto"] * float(m)]
    return {"cuota cloud (429)": (1 if n429 >= UMBRAL["llm_429_h"] else 0, f"{n429} errores 429 en 1 h"),
            "presupuesto LiteLLM": (1 if altas else 0, ", ".join(altas) or "todas las claves por debajo del 80 %")}


def logins():
    n = 0
    for c in ("hermes-webui", "hermes-coding"):
        r = subprocess.run(["docker", "logs", "--since", "1h", c], capture_output=True, text=True, timeout=60)
        for l in (r.stdout + r.stderr).splitlines():
            if '"/api/auth/login"' in l and ('"status": 401' in l or '"status": 429' in l):
                n += 1
    r = subprocess.run(["docker", "logs", "--since", "1h", "vaultwarden"], capture_output=True, text=True, timeout=60)
    n += sum(1 for l in (r.stdout + r.stderr).splitlines() if "Username or password is incorrect" in l)
    return {"logins fallidos": (1 if n >= UMBRAL["logins_fallidos_h"] else 0, f"{n} en 1 h (WebUI y Vaultwarden)")}


def sqlite():
    """S.12 de v2.4: state.db de cada zona sin bloqueos y con el WAL acotado (solo tamaños y logs)."""
    n = 0
    for c in ("hermes-webui", "hermes-coding", "hermes-coding-api", "hermes-research"):
        r = subprocess.run(["docker", "logs", "--since", "1h", c], capture_output=True, text=True, timeout=60)
        n += sum(1 for l in (r.stdout + r.stderr).splitlines() if "database is locked" in l)
    wal = [p for pat in ("*/_data/state.db-wal", "*/_data/profiles/*/state.db-wal") for p in VOLUMENES.glob(pat)]
    grandes = [f"{p.relative_to(VOLUMENES).parts[0]}/{p.parent.name} {p.stat().st_size >> 20} MiB"
               for p in wal if p.stat().st_size >= UMBRAL["wal_bytes"]]
    return {"SQLite bloqueos": (1 if n else 0, f"{n} «database is locked» en 1 h"),
            "SQLite WAL": (1 if grandes else 0, ", ".join(grandes) or f"{len(wal)} WAL por debajo de 256 MiB")}


def tiny():
    """Tiny de Neo (llama-swap, gestor y resumen): fallos de arranque o 500 en las últimas 24 h.

    Pasiva, sin peticiones de prueba: no carga el modelo en la GPU. Los consumidores lo llaman a
    diario, así que un fallo se ve en menos de un día. Ventana de 24 h para no avisar y resolver
    cada hora. Caso real: choque de puerto con JDownloader (04-11 a 06-11), sin aviso.
    """
    lineas = run("journalctl", "-u", "llama-swap.service", "--since", "-24h", "--no-pager",
                 "-o", "short-iso").splitlines()
    # Cada petición fallida deja «status=500»; un arranque fallido, además, «starting … failed».
    malas = [l for l in lineas if "status=500" in l] or [l for l in lineas if "failed" in l]
    if not malas:
        return {"tiny de Neo": (0, "sin fallos en 24 h")}
    return {"tiny de Neo": (1, f"{len(malas)} petición(es) con error en 24 h; última {malas[-1][:19]}")}


def recoger():
    res = {}
    for fn in (discos, ram, egresos_personal, cuarentena, wol, cuota, logins, sqlite, tiny):
        try:
            res.update(fn())
        except Exception as e:  # una fuente rota es una alerta en sí misma, no un fallo de todo
            res[f"comprobación {fn.__name__}"] = (1, f"no se pudo comprobar ({type(e).__name__})")
    return res


def main():
    res = recoger()
    if "--dry-run" in sys.argv:
        for k, (nivel, txt) in res.items():
            print(f"{['ok', 'AVISO', 'CRÍTICO'][nivel]:8} {k}: {txt}")
        return 0
    try:
        previo = json.loads(STATE.read_text())
    except (OSError, ValueError):
        previo = {}
    ahora, nuevo, lineas = time.time(), {}, []
    for k, (nivel, txt) in res.items():
        p = previo.get(k, {"nivel": 0, "aviso": 0})
        avisar = nivel > p["nivel"] or (nivel and ahora - p["aviso"] > RECORDAR)
        if avisar:
            lineas.append(f"- {['', 'AVISO', 'CRÍTICO'][nivel]} {k}: {txt}")
        elif p["nivel"] and not nivel:
            lineas.append(f"- resuelto {k}: {txt}")
        nuevo[k] = {"nivel": nivel, "aviso": ahora if avisar else (p["aviso"] if nivel else 0)}
    if lineas:
        texto = "SIP alertas\n" + "\n".join(lineas)
        stamp = int(ahora)
        tmp = OUTBOX / f".alertas-{stamp}.tmp"
        tmp.write_text(texto[:1000] + "\n")
        tmp.replace(OUTBOX / f"alertas-{stamp}.txt")
        print(texto)
    else:
        print("sin cambios")
    STATE.write_text(json.dumps(nuevo))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
