#!/usr/bin/env python3
"""Traspaso nocturno de tareas de código a CODING, con verificador fuera del alcance del agente (root, en Neo).

Cola: /var/lib/sip-traspaso/cola/<id>/{tarea.json,mensaje.md}, propiedad de root. Por cada tarea, en orden:
  1. Despierta HALO por el servicio WOL si no responde.
  2. Manda mensaje.md a la API de CODING (conversación traspaso-<id>).
  3. Verifica por su cuenta, por el SSH del worker que ya usa CODING: las órdenes de `verificacion`
     (código de salida 0), que los ficheros cambiados estén en `permitidos`, que no haya ficheros nuevos
     o modificados fuera de ellos (también ignorados por git, como node_modules) y, si se pide, un commit
     y el árbol limpio.
  4. Si falla y quedan intentos, manda una revisión con las salidas reales y vuelve a verificar.
Resultado: hecho/<id>/ con informe.md, una línea en registro.jsonl y un aviso por sip-notify.
Nunca fusiona, sube ni borra: el resultado queda en el workspace del worker para revisarlo.

Uso: sip-traspaso.py run | check (sale con 1 si la cola está vacía, para ExecCondition)
"""
import fnmatch
import json
import os
import shlex
import shutil
import socket
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

BASE = Path(os.environ.get("SIP_TRASPASO_DIR", "/var/lib/sip-traspaso"))
COLA, HECHO, REGISTRO = BASE / "cola", BASE / "hecho", BASE / "registro.jsonl"
OUTBOX = Path(os.environ.get("SIP_NOTIFY_OUTBOX", "/var/lib/sip-notify/outbox"))
WOL = Path("${DOCKER_DATA}/hermes/workspace/_wol")
HALO = ("${HALO_TAILNET_IP}", 11434)
# La unidad lo recibe por LoadCredential (ProtectHome oculta /root); a mano, desde /root.
API_ENV = os.path.join(os.environ.get("CREDENTIALS_DIRECTORY", "/root"),
                       "coding-api.env" if "CREDENTIALS_DIRECTORY" in os.environ else "sip-coding-api.env")
PY_IMG = "python@sha256:57cd7c3a7a273101a6485ba99423ee568157882804b1124b4dd04266317710de"  # la del gateway
KEY = "/home/hermeswebui/.hermes/ssh"
SSH = ["docker", "exec", "-u", "993", "hermes-coding", "ssh", "-i", f"{KEY}/id_ed25519_halo_worker",
       "-o", f"UserKnownHostsFile={KEY}/known_hosts", "-o", "StrictHostKeyChecking=yes",
       "-o", "BatchMode=yes", "-o", "ConnectTimeout=15", "hermes-worker@${HALO_TAILNET_IP}"]
HASTA = int(os.environ.get("SIP_TRASPASO_HASTA", "7"))  # no empezar intentos a partir de esta hora
IGNORAR = [".git/*", "dist/*", "*/__pycache__/*", "__pycache__/*", "node_modules/.vite/*",
           "node_modules/.cache/*", "*.tsbuildinfo"]
MARCA = ".git/sip-traspaso-base"
TAIL = 1500


def log(*a):
    print(datetime.now().strftime("%H:%M:%S"), *a, flush=True)


def halo_up():
    try:
        socket.create_connection(HALO, timeout=5).close()
        return True
    except OSError:
        return False


def despertar():
    if halo_up():
        return "already_awake"
    rid = "traspaso-" + datetime.now().strftime("%Y%m%d-%H%M%S")
    tmp = WOL / "requests" / f".{rid}.tmp"
    tmp.write_text("{}\n")
    tmp.replace(WOL / "requests" / f"{rid}.json")
    res = WOL / "results" / f"{rid}.json"
    for _ in range(48):  # 240 s
        time.sleep(5)
        if res.exists():
            estado = json.loads(res.read_text()).get("status", "?")
            # La sonda del WOL es el puerto de Ollama; el SSH del worker tarda algo más.
            time.sleep(30 if estado == "awake" else 0)
            return estado
    return "sin_respuesta"


def remoto(ws, cmd, timeout=1800):
    """Ejecuta cmd en el workspace del worker. Devuelve (código, salida combinada)."""
    full = f"cd {shlex.quote(ws)} && ( {cmd} ) 2>&1"
    try:
        r = subprocess.run(SSH + [full], capture_output=True, text=True, timeout=timeout)
        return r.returncode, r.stdout + r.stderr
    except subprocess.TimeoutExpired:
        return 124, f"(timeout de {timeout} s)"


def coding(conv, texto, timeout_s):
    """Un turno en la API de CODING, como ask-coding.sh. Devuelve el texto de la respuesta."""
    code = (
        "import json, os, sys, urllib.request\n"
        "body = json.dumps({'model': 'hermes-agent', 'input': sys.stdin.read(), 'conversation': os.environ['CONV']})\n"
        "req = urllib.request.Request('http://10.24.0.10:8642/v1/responses', body.encode(), {\n"
        "    'Authorization': 'Bearer ' + os.environ['API_SERVER_KEY'], 'Content-Type': 'application/json'})\n"
        "with urllib.request.urlopen(req, timeout=int(os.environ['TMO'])) as r:\n"
        "    d = json.load(r)\n"
        "print(''.join(c.get('text', '') for o in d.get('output', []) if o.get('type') == 'message'\n"
        "              for c in o.get('content', [])).strip() or '(sin texto; estado %s)' % d.get('status'))\n")
    cmd = ["docker", "run", "--rm", "-i", "--network", "gw-coding", "--read-only", "--cap-drop", "ALL",
           "--user", "65534:65534", "--env-file", API_ENV, "-e", f"CONV={conv}", "-e", f"TMO={timeout_s}",
           "--entrypoint", "python3", PY_IMG, "-c", code]
    try:
        r = subprocess.run(cmd, input=texto, capture_output=True, text=True, timeout=timeout_s + 60)
        return r.stdout.strip() or ("(error de la API) " + r.stderr.strip()[-500:])
    except subprocess.TimeoutExpired:
        return f"(la API no respondió en {timeout_s} s)"


def cambiados(ws, base):
    """Ficheros cambiados desde base: commits, árbol, nuevos y también los ignorados por git."""
    _, a = remoto(ws, f"git diff --name-only {shlex.quote(base)}; git ls-files --others --exclude-standard; "
                      f"find . -path ./.git -prune -o -type f -newer {MARCA} -print | sed 's|^\\./||'")
    return sorted({l.strip() for l in a.splitlines() if l.strip()})


def verificar(t, base):
    ws, fallos, salidas = t["workspace"], [], []
    for c in t["verificacion"]:
        rc, out = remoto(ws, c)
        salidas.append(f"$ {c}\n(código {rc})\n{out[-TAIL:]}")
        if rc != 0:
            fallos.append(f"`{c}` terminó con código {rc}")
    fuera = [f for f in cambiados(ws, base)
             if not any(fnmatch.fnmatch(f, p) for p in t["permitidos"] + IGNORAR + t.get("ignorar", []))]
    if fuera:
        fallos.append("ficheros cambiados fuera de los permitidos: " + ", ".join(fuera[:20]))
    if t.get("commit", True):
        _, head = remoto(ws, "git rev-parse HEAD")
        if head.strip() == base:
            fallos.append("no hay commit nuevo")
        _, st = remoto(ws, "git status --porcelain")
        if st.strip():
            fallos.append("el árbol no está limpio:\n" + st.strip()[:500])
    return fallos, salidas


def revision(fallos, salidas):
    return ("Revisión automática del verificador: la tarea NO está terminada.\n\nFallos:\n"
            + "\n".join("- " + f for f in fallos)
            + "\n\nSalidas reales de la verificación:\n\n" + "\n\n".join(salidas)
            + "\n\nCorrige solo lo necesario, sin tocar ficheros fuera de los permitidos ni las pruebas, "
              "vuelve a ejecutar los criterios y haz commit cuando todos pasen.")


def modelo():
    r = subprocess.run(["docker", "exec", "hermes-coding-api", "sh", "-c",
                        "sed -n '/^model:/,/^[a-z]/p' /home/hermeswebui/.hermes/config.yaml"],
                       capture_output=True, text=True)
    return next((l.split(":", 1)[1].strip() for l in r.stdout.splitlines() if "default:" in l), "?")


def procesar(d):
    t = json.loads((d / "tarea.json").read_text())
    tid, ws = d.name, t["workspace"]
    reg = {"id": tid, "inicio": datetime.now().isoformat(timespec="seconds"), "modelo": modelo(),
           "workspace": ws, "intentos": []}
    reg["halo"] = despertar()
    if reg["halo"] not in ("already_awake", "awake"):
        return reg | {"resultado": "halo_no_disponible"}
    rc, base = remoto(ws, f"git rev-parse HEAD && touch {MARCA}")
    if rc != 0:
        return reg | {"resultado": "workspace_invalido", "detalle": base[-300:]}
    base = base.split()[0]
    reg["base"] = base
    texto = (d / "mensaje.md").read_text()
    fallos = ["sin intentar"]
    for n in range(1, int(t.get("max_intentos", 2)) + 1):
        if datetime.now().hour >= HASTA and datetime.now().hour < 20:
            reg["detalle"] = f"ventana agotada (a partir de las {HASTA}:00)"
            break
        t0 = time.time()
        respuesta = coding(f"traspaso-{tid}", texto, int(t.get("timeout_min", 120)) * 60)
        fallos, salidas = verificar(t, base)
        reg["intentos"].append({"n": n, "segundos": round(time.time() - t0), "fallos": fallos,
                                "informe_modelo": respuesta[-TAIL:]})
        log(tid, f"intento {n}:", "OK" if not fallos else f"{len(fallos)} fallos")
        if not fallos:
            break
        if respuesta.startswith("(error de la API)"):
            # Fallo de infraestructura, no del modelo: no gastar más intentos.
            reg["resultado"] = "error_api"
            break
        texto = revision(fallos, salidas)
    reg.setdefault("resultado", "ok" if not fallos else "fallo")
    _, reg["head"] = remoto(ws, "git log --oneline -1")
    return reg


def informe(reg):
    l = [f"# Traspaso {reg['id']}: {reg['resultado'].upper()}", "",
         f"- Modelo: `{reg['modelo']}` · inicio {reg['inicio']} · HALO: {reg.get('halo')}",
         f"- Workspace: `{reg['workspace']}` · base `{reg.get('base', '?')[:12]}` · ahora: {reg.get('head', '').strip()}"]
    if reg.get("detalle"):
        l.append(f"- Detalle: {reg['detalle']}")
    for i in reg["intentos"]:
        l += ["", f"## Intento {i['n']} ({i['segundos'] // 60} min)", "",
              "Fallos del verificador: " + ("ninguno" if not i["fallos"] else ""),
              *[f"- {f}" for f in i["fallos"]], "", "Informe del modelo (no es evidencia):", "",
              "```", i["informe_modelo"], "```"]
    return "\n".join(l) + "\n"


def avisar(regs):
    lineas = ["Traspaso nocturno:"]
    for r in regs:
        mins = sum(i["segundos"] for i in r["intentos"]) // 60
        lineas.append(f"- {r['id']}: {r['resultado']} ({len(r['intentos'])} intentos, {mins} min)")
    lineas.append("Informes en /var/lib/sip-traspaso/hecho/. Nada fusionado ni subido.")
    txt = "\n".join(lineas)[:950]
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    tmp = OUTBOX / f".traspaso-{stamp}.tmp"
    tmp.write_text(txt + "\n")
    tmp.replace(OUTBOX / f"traspaso-{stamp}.txt")


def pendientes():
    return sorted(p for p in COLA.iterdir() if p.is_dir() and (p / "tarea.json").exists()) if COLA.exists() else []


def main():
    if sys.argv[1:] == ["check"]:
        return 0 if pendientes() else 1
    if sys.argv[1:] != ["run"]:
        print(__doc__)
        return 2
    regs = []
    for d in pendientes():
        if datetime.now().hour >= HASTA and datetime.now().hour < 20:
            log("ventana agotada; quedan tareas en cola")
            break
        log("tarea", d.name)
        reg = procesar(d)
        regs.append(reg)
        with REGISTRO.open("a") as f:
            f.write(json.dumps(reg, ensure_ascii=False) + "\n")
        if reg["resultado"] == "halo_no_disponible":
            log("HALO no disponible; la tarea sigue en cola")
            break
        dst = HECHO / d.name
        shutil.move(str(d), str(dst))
        (dst / "informe.md").write_text(informe(reg))
        log(d.name, reg["resultado"])
    if regs:
        avisar(regs)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
