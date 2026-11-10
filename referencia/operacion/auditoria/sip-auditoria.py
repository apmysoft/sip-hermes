#!/usr/bin/env python3
"""Auditoría trimestral de SIP (v2.4 Fase 10: O4, O7 con logs de LiteLLM, O10, integridad M.14, rotación M.13).

En Neo como root (sip-auditoria.timer). Nunca imprime un valor secreto: O7 carga los secretos reales de sus
ubicaciones legítimas, solo en memoria, y busca coincidencias exactas fuera de ellas (volúmenes de Hermes,
logs de Docker de SIP, log de filegate, journal de las unidades SIP). Informe completo en
/var/lib/sip-auditoria/informe-<fecha>.txt (root 0600) y resumen por la bandeja de sip-notify.
--sin-aviso: no deja nada en la bandeja (pruebas).
"""
import glob
import hashlib
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

import yaml

V = Path("${DOCKER_DATA}/docker_root/volumes")
HOMES = [V / "hermes_hermes-home/_data", V / "sip-coding_home/_data", V / "sip-research_hermes-research-home/_data"]
FUENTES_SECRETOS = [*glob.glob("/root/sip-*.env"), "/root/sip-litellm-keys.json", "/root/sip-hermes-backup.pass",
                    *glob.glob("/etc/filegate/tokens/*.tok"), *[str(h / ".env") for h in HOMES]]
CONTENEDORES = ["hermes-webui", "hermes-coding", "hermes-coding-api", "hermes-research", "hermes-sandbox-runner",
                "sip-litellm", "sip-litellm-db", "sip-gateway", "vaultwarden", "hermes-perm-guardian"]
NO_SECRETO = {"UID", "GID", "HERMES_WORKSPACE", "TZ", "LANG"}
NOMBRE_SECRETO = re.compile(r"KEY|TOKEN|SECRET|PASS|AUTH|CRED", re.I)
OUT = Path("/var/lib/sip-auditoria")
OUTBOX = Path("/var/lib/sip-notify/outbox")
# O4: nombres que el terminal puede ver sin ser secretos (huella GPG pública, una ruta, una variable vacía).
O4_PERMITIDOS = {"GPG_KEY", "TERMINAL_SSH_KEY", "TERMINAL_DOCKER_SHARED_CONTAINER_KEY"}
O4_PRUEBA = r'''
import json, os, sys
sys.path.insert(0, os.getcwd())
from hermes_cli.env_loader import load_hermes_dotenv
load_hermes_dotenv()
import tools.terminal_tool as T
cmd = "printenv | cut -d= -f1 | grep -iE 'key|token|secret|pass|auth'; test -r ~/.hermes/.env && echo ENV_LEGIBLE; true"
print(json.loads(T.terminal_tool(command=cmd, task_id="auditoria")).get("output"))
'''


def run(*cmd, stdin=None, timeout=300):
    r = subprocess.run(cmd, input=stdin, capture_output=True, text=True, timeout=timeout)
    return r.stdout + r.stderr


def secretos():
    """{valor: nombre} desde las ubicaciones legítimas. Los valores no salen de este proceso."""
    s = {}
    for f in FUENTES_SECRETOS:
        p = Path(f)
        if not p.is_file():
            continue
        txt = p.read_text(errors="ignore")
        if p.suffix == ".json":
            def walk(o, ruta):
                if isinstance(o, dict):
                    for k, v in o.items():
                        walk(v, f"{ruta}.{k}")
                elif isinstance(o, list):
                    for i, v in enumerate(o):
                        walk(v, f"{ruta}[{i}]")
                elif isinstance(o, str) and len(o) >= 16:
                    s[o] = f"{p.name}{ruta}"
            d = json.loads(txt)
            walk(d, "")
            for i, e in enumerate(d if isinstance(d, list) else []):  # nombre legible: la zona de la clave
                if isinstance(e, dict) and e.get("key") in s:
                    s[e["key"]] = f"clave virtual de {e.get('zone', i)}"
        elif p.suffix in (".tok", ".pass"):
            if len(txt.strip()) >= 12:
                s[txt.strip()] = p.name
        else:
            for l in txt.splitlines():
                if l.lstrip().startswith("#"):
                    continue  # la plantilla de .env de Hermes trae cientos de ejemplos comentados
                k, sep, v = l.partition("=")
                k, v = k.strip(), v.strip().strip('"\'')
                if (sep and k not in NO_SECRETO and NOMBRE_SECRETO.search(k) and len(v) >= 12
                        and not v.startswith(("/", "http", "REDACTED"))):
                    s[v] = f"{p.parent.name}/{p.name}:{k}"
    return s


def o7(sec):
    """Coincidencias exactas de secretos reales fuera de su sitio. Devuelve [(nombre, dónde)]."""
    legitimos = {str(Path(f).resolve()) for f in FUENTES_SECRETOS}
    claves = [(v.encode(), n) for v, n in sec.items()]
    hallazgos, revisados = [], 0
    for h in HOMES:
        for raiz, _, fs in os.walk(h):
            for f in fs:
                p = Path(raiz) / f
                if str(p.resolve()) in legitimos or p.is_symlink() or not p.is_file():
                    continue
                try:
                    if p.stat().st_size > 20 << 20:
                        continue
                    datos = p.read_bytes()
                except OSError:
                    continue
                revisados += 1
                hallazgos += [(n, str(p.relative_to(V))) for v, n in claves if v in datos]
    for c in CONTENEDORES:
        logs = run("docker", "logs", c)
        hallazgos += [(n, f"logs de Docker de {c}") for v, n in sec.items() if v in logs]
    for f in glob.glob("/var/log/filegate/*"):
        datos = Path(f).read_bytes()
        hallazgos += [(n, f) for v, n in claves if v in datos]
    j = run("journalctl", "--since", "-100d", "--no-pager", "-o", "cat", "-u", "sip-*", "-u", "filegate*")
    hallazgos += [(n, "journal de las unidades SIP") for v, n in sec.items() if v in j]
    return hallazgos, revisados


def o10():
    fs = [HOMES[0] / "config.yaml", *sorted((HOMES[0] / "profiles").glob("*/config.yaml")),
          HOMES[1] / "config.yaml", HOMES[2] / "config.yaml"]
    malos = []
    for f in fs:
        c = yaml.safe_load(f.read_text()) or {}
        a = c.get("approvals") or {}
        modos = [a.get(k) for k in ("mode", "cron_mode", "single_query_mode", "unattended_mode")]
        if c.get("command_allowlist") or "off" in modos or "yolo" in modos:
            malos.append(f"{f.relative_to(V)}: allowlist={c.get('command_allowlist')} modos={modos}")
    return malos, len(fs)


def o4():
    zonas = {
        "CODING": ["docker", "exec", "-i", "-u", "993", "-w", "/opt/hermes-agent", "-e", "HOME=/home/hermeswebui",
                   "hermes-coding-api", "/app/venv/bin/python", "-"],
        "PERSONAL": ["docker", "exec", "-i", "-u", "1000", "-w", "/opt/hermes-agent", "-e", "HOME=/home/hermeswebui",
                     "-e", "HERMES_HOME=/home/hermeswebui/.hermes/profiles/personal", "hermes-webui",
                     "/app/venv/bin/python", "-"],
    }
    malos = []
    for z, cmd in zonas.items():
        out = run(*cmd, stdin=O4_PRUEBA, timeout=120)
        vistos = {l.strip() for l in out.splitlines() if l.strip() and l.strip().isupper() or l.strip() == "ENV_LEGIBLE"}
        extra = sorted(vistos - O4_PERMITIDOS)
        if extra:
            malos.append(f"{z}: el terminal ve {', '.join(extra)}")
    for p in ("cli", "api_server"):
        out = run("docker", "exec", "-u", "995", "hermes-research", "hermes", "tools", "list", "--platform", p)
        activas = sorted(l.split()[2] for l in out.splitlines() if "✓" in l)
        if set(activas) - {"browser", "entrada"}:
            malos.append(f"RESEARCH {p}: herramientas {activas}")
    return malos


def integridad():
    malos = run("find", "/usr/local/bin", "/usr/local/sbin", "/etc/systemd/system", "-maxdepth", "2",
                "(", "!", "-user", "root", "-o", "-perm", "/022", ")", "!", "-type", "l").split()
    ok = subprocess.run(["sha256sum", "--status", "--strict", "-c", "/etc/sip-integridad/filegate.sha256"]).returncode == 0
    return malos + ([] if ok else ["filegate: sha256 distinto del manifiesto"])


def main():
    t0, fecha = time.time(), time.strftime("%Y-%m-%d")
    sec = secretos()
    fugas, revisados = o7(sec)
    apr, nconf = o10()
    term = o4()
    integ = integridad()
    lineas = [
        f"Auditoría trimestral de SIP, {fecha}",
        f"O7: {len(sec)} secretos reales buscados en {revisados} ficheros, logs de {len(CONTENEDORES)} "
        f"contenedores, filegate y journal → " + (f"{len(fugas)} FUGA(S)" if fugas else "0 fugas"),
        *[f"  - {n} en {d}" for n, d in fugas],
        f"O10: {nconf} configs → " + ("; ".join(apr) if apr else "allowlist vacía, sin off/yolo"),
        "O4: " + ("; ".join(term) if term else "RESEARCH sin terminal; CODING y PERSONAL sin secretos en el terminal"),
        "Integridad: " + (", ".join(integ) if integ else "todo root:root y filegate con su sha256"),
        "Rotación (M.13): revisa ROTACION.md y rota lo que toque este trimestre (claves cloud, virtuales, tokens).",
        f"({round(time.time() - t0)} s)",
    ]
    informe = "\n".join(lineas)
    OUT.mkdir(mode=0o700, exist_ok=True)
    f = OUT / f"informe-{fecha}.txt"
    f.write_text(informe + "\n")
    f.chmod(0o600)
    print(informe)
    problemas = bool(fugas or apr or term or integ)
    if "--sin-aviso" not in sys.argv:
        resumen = ("SIP: auditoría trimestral con PROBLEMAS\n" if problemas else "SIP: auditoría trimestral sin problemas\n")
        resumen += "\n".join(l for l in lineas[1:7]) + f"\nInforme: {f}"
        tmp = OUTBOX / f".auditoria-{int(t0)}.tmp"
        tmp.write_text(resumen[:1000] + "\n")
        tmp.replace(OUTBOX / f"auditoria-{int(t0)}.txt")
    return 1 if problemas else 0


if __name__ == "__main__":
    raise SystemExit(main())
