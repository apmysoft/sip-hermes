#!/usr/bin/env python3
"""Resumen matutino de SIP (v2.4 Fase 9). Solo datos del sistema, sin contenido personal.

Los datos se recogen de forma determinista; el tiny de Neo (llama-swap, 127.0.0.1:11434) solo redacta
un titular de una línea a partir de ellos. Si el tiny falla, el resumen sale sin titular.
Entrega: bandeja de sip-notify (Telegram), con su tope de 1000 caracteres. --dry-run solo imprime.
"""
import calendar
import json
import os
import socket
import sqlite3
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

VOL = Path("${DOCKER_DATA}/docker_root/volumes")
ZONES = {
    "PERSONAL": [VOL / "hermes_hermes-home/_data"] + sorted(
        (VOL / "hermes_hermes-home/_data/profiles").glob("*")),
    "CODING": [VOL / "sip-coding_home/_data"],
    "RESEARCH": [VOL / "sip-research_hermes-research-home/_data"],
}
GESTOR_DB = "/var/lib/sip-gestor-entrada/state.db"
HALO = ("${HALO_TAILNET_IP}", 11434)
LLM_URL = os.environ.get("SIP_LLM_URL", "http://127.0.0.1:11434/v1/chat/completions")
OUTBOX = Path(os.environ.get("SIP_NOTIFY_OUTBOX", "/var/lib/sip-notify/outbox"))
# Unidades fallidas conocidas que no indican un problema (restos de la ISO de instalación).
IGNORE_UNITS = {"casper-md5check.service"}


def run(*cmd, stdin=None):
    return subprocess.run(cmd, input=stdin, capture_output=True, text=True, timeout=60).stdout


def failed_units():
    out = run("systemctl", "--failed", "--no-legend", "--plain")
    units = [l.split()[0] for l in out.splitlines() if l.strip() and l.split()[0] not in IGNORE_UNITS]
    # filegate@ es una instancia por conexión: que falle es una petición rechazada, no un servicio caído.
    gate = [u for u in units if u.startswith("filegate@")]
    return [u for u in units if u not in gate], len(gate)


def age(ts):  # segundos desde una marca RFC 3339 de Docker (UTC)
    return time.time() - calendar.timegm(time.strptime(ts[:19], "%Y-%m-%dT%H:%M:%S"))


def bad_containers():
    ids = run("docker", "ps", "-aq").split()
    out = run("docker", "inspect", "-f",
              "{{.Name}}|{{.State.Status}}|{{.State.ExitCode}}|{{.RestartCount}}|{{.State.StartedAt}}|"
              "{{.State.FinishedAt}}|{{if .State.Health}}{{.State.Health.Status}}{{end}}", *ids) if ids else ""
    bad = []
    for line in out.splitlines():
        name, status, code, restarts, started, finished, health = line.lstrip("/").split("|")
        # En bucle de reinicios el contenedor pasa ratos como running: lo delata el contador.
        if status == "restarting" or (int(restarts) > 0 and age(started) < 3600):
            bad.append(f"{name} (reiniciándose, {restarts} reinicios)")
        elif status == "running" and health == "unhealthy":
            bad.append(f"{name} (no sano)")
        elif status == "exited" and code != "0" and age(finished) < 86400:
            # Solo fallos recientes: un contenedor parado hace semanas es una parada manual.
            bad.append(f"{name} (falló, código {code})")
    return bad


def halo_on():
    try:
        socket.create_connection(HALO, timeout=3).close()
        return True
    except OSError:
        return False


def pending_writes():
    res = {}
    for zone, homes in ZONES.items():
        n = sum(1 for h in homes for k in ("memory", "skills")
                for _ in (h / "pending" / k).glob("*.json") if (h / "pending" / k).is_dir())
        if n:
            res[zone] = n
    return res


def gestor_pending():
    db = sqlite3.connect(f"file:{GESTOR_DB}?mode=ro", uri=True)
    rows = db.execute("select p.batch, count(*) from proposals p where not exists "
                      "(select 1 from decisions d where d.batch = p.batch) "
                      "and p.batch not in (select batch from discarded) group by 1").fetchall()
    return len(rows), sum(n for _, n in rows)


def spend_24h():
    sql = ('select coalesce(t.key_alias, \'master\'), count(*), round(sum(s.spend)::numeric, 2) '
           'from "LiteLLM_SpendLogs" s left join "LiteLLM_VerificationToken" t on t.token = s.api_key '
           'where s."startTime" > now() - interval \'1 day\' group by 1 order by 1')
    out = run("docker", "exec", "-i", "sip-litellm-db", "sh", "-c",
              'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -AtF"|"', stdin=sql)
    return [l.split("|") for l in out.splitlines() if l.count("|") == 2]


def apt_upgradable():
    out = run("apt", "list", "--upgradable")
    pk = [l for l in out.splitlines() if "/" in l]
    return len(pk), sum(1 for l in pk if "-security" in l)


def unit_result(unit):
    out = run("systemctl", "show", unit, "-p", "Result", "-p", "ExecMainExitTimestamp", "--value")
    res, _, ts = out.partition("\n")
    return res.strip(), ts.strip()


def safe(fn, default):
    try:
        return fn()
    except Exception as e:  # una fuente rota no debe impedir el resto del resumen
        print(f"<4>{fn.__name__}: {e}", file=sys.stderr)
        return default


def collect():
    facts = []
    units, gate = safe(failed_units, (None, 0))
    cont = safe(bad_containers, None)
    facts.append("Servicios: " + ("no se pudo comprobar" if units is None or cont is None else
                 "todo en marcha" if not units and not cont else
                 "; ".join(filter(None, [
                     units and "unidades fallidas: " + ", ".join(units),
                     cont and "contenedores con problemas: " + ", ".join(cont)]))))
    if gate:
        facts.append(f"Filegate: {gate} conexión(es) fallida(s) pendientes de revisar")
    facts.append("HALO: " + ("encendido" if halo_on() else "apagado"))
    pw = safe(pending_writes, None)
    facts.append("Memoria/skills por revisar: " + ("no se pudo comprobar" if pw is None else
                 ", ".join(f"{z} {n}" for z, n in pw.items()) if pw else "ninguna"))
    gp = safe(gestor_pending, None)
    facts.append("Gestor de entrada: " + ("no se pudo comprobar" if gp is None else
                 f"{gp[0]} lote(s) sin aprobar ({gp[1]} propuestas)" if gp[0] else "sin lotes pendientes"))
    sp = safe(spend_24h, None)
    facts.append("Modelos 24 h: " + ("no se pudo comprobar" if sp is None else
                 ", ".join(f"{k} {n} llamadas/{c} $" for k, n, c in sp) if sp else "sin uso"))
    up = safe(apt_upgradable, None)
    facts.append("Actualizaciones Neo: " + ("no se pudo comprobar" if up is None else
                 f"{up[0]} paquetes ({up[1]} de seguridad)"))
    res, ts = safe(lambda: unit_result("sip-litellm-backup.service"), ("", ""))
    facts.append("Backup LiteLLM: " + (f"{res} ({ts})" if res else "sin dato"))
    return facts


def headline(facts):
    body = {
        "model": "qwen3-4b-instruct",
        "temperature": 0.1,
        "max_tokens": 60,
        "messages": [
            {"role": "system", "content":
             "Eres el asistente de sistemas de un servidor doméstico. Escribe UNA sola frase en "
             "español, de menos de 20 palabras, con lo más importante que el usuario debe atender "
             "hoy según los datos. Si todo está bien, dilo. No inventes nada que no esté en los datos."},
            {"role": "user", "content": "\n".join(facts)},
        ],
    }
    req = urllib.request.Request(LLM_URL, json.dumps(body).encode(),
                                 {"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=180) as r:
        text = json.load(r)["choices"][0]["message"]["content"].strip()
    return " ".join(text.split())[:200]


def main():
    facts = collect()
    title = safe(lambda: headline(facts), None)
    text = (f"Buenos días. {title}\n\n" if title else "Buenos días (sin titular: tiny no disponible).\n\n")
    text += "\n".join("- " + f for f in facts)
    if "--dry-run" in sys.argv:
        print(text)
        print(f"({len(text)} caracteres)")
        return 0
    stamp = int(time.time())
    tmp = OUTBOX / f".resumen-{stamp}.tmp"
    tmp.write_text(text + "\n")
    tmp.replace(OUTBOX / f"resumen-{stamp}.txt")
    print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
