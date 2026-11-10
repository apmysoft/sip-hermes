#!/usr/bin/env python3
"""Evaluación semanal de modelos (v2.4 Fase 9, decisión 11). Propone; nunca cambia nada.

1. Métricas deterministas de los últimos 7 días desde LiteLLM (llamadas, % de fallos, latencia mediana,
   gasto por modelo), más el inventario de Ollama en HALO y los modelos configurados en LiteLLM.
2. RESEARCH (por su API, como /r) recibe esas cifras y comprueba en fuentes oficiales si hay versiones
   nuevas o retiradas de los modelos en uso. Devuelve una propuesta corta; decide el usuario.
Informe completo en /var/lib/sip-model-eval/<fecha>.md; resumen por sip-notify (1000 caracteres).
Solo salen hacia RESEARCH (cloud) nombres de modelos y cifras de uso, nada personal.
"""
import json
import os
import re
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

LITELLM_CONFIG = Path("/opt/sip-litellm/litellm.config.yaml")
HALO_MODELS = "http://${HALO_TAILNET_IP}:11434/v1/models"  # 05-11: /v1 (Ollama y llama-swap), antes /api/tags de Ollama
RESEARCH_ENV = "/root/sip-research-api.env"
IMG = "python@sha256:57cd7c3a7a273101a6485ba99423ee568157882804b1124b4dd04266317710de"  # 3.12-slim
OUT_DIR = Path("/var/lib/sip-model-eval")
OUTBOX = Path(os.environ.get("SIP_NOTIFY_OUTBOX", "/var/lib/sip-notify/outbox"))

SQL = """select coalesce(nullif(model_group, ''), nullif(model, ''), '(sin modelo)'), count(*),
 round(100.0 * sum(case when status = 'failure' then 1 else 0 end) / count(*)),
 coalesce(round((percentile_cont(0.5) within group (order by request_duration_ms)
   filter (where status = 'success') / 1000.0)::numeric, 1), 0),
 round(sum(spend)::numeric, 3)
 from "LiteLLM_SpendLogs" where "startTime" > now() - interval '7 days' group by 1 order by 2 desc"""

PROMPT = """Evaluación semanal de modelos de SIP. No cambies nada: solo propón.

Modelos configurados en LiteLLM: {configured}
Modelos locales en HALO (Ollama, GPU AMD de 32 GB): {halo}
Uso de los últimos 7 días (modelo | llamadas | % fallos | latencia mediana en s | gasto en $):
{metrics}
Las filas marcadas «no configurado» son peticiones erróneas de clientes (nombres que no existen o pruebas
de autenticación), no modelos: no propongas nada sobre ellas. Con menos de {min_calls} llamadas las cifras
no son significativas: no bases ninguna propuesta en ellas.

Con el navegador, consulta fuentes oficiales de las cuatro familias en uso: Google AI (Gemini), Moonshot
(Kimi), Qwen y Ollama (la biblioteca de modelos). Responde en español, en menos de 700 caracteres y sin
markdown:
1. Versiones nuevas o anuncios de retirada que afecten a los modelos en uso, con su fuente. Di qué
   familias no pudiste comprobar.
2. Como mucho 3 cambios propuestos (sustituir, añadir o retirar un modelo), cada uno con su motivo
   basado en las cifras o en la fuente. Si no hay nada que justifique un cambio, dilo: «sin cambios».
No inventes versiones: si no puedes comprobar algo, dilo."""
MIN_CALLS = 20


def run(*cmd, stdin=None, timeout=120):
    r = subprocess.run(cmd, input=stdin, capture_output=True, text=True, timeout=timeout)
    if r.returncode != 0:
        raise RuntimeError(f"{cmd[0]} {cmd[1] if len(cmd) > 1 else ''}: {r.stderr.strip()[:200]}")
    return r.stdout


def metrics():
    out = run("docker", "exec", "-i", "sip-litellm-db", "sh", "-c",
              'psql -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$POSTGRES_DB" -AtF"|"', stdin=SQL)
    return [l.split("|") for l in out.splitlines() if l.count("|") == 4]


def configured():
    return re.findall(r"^\s*-\s*model_name:\s*(\S+)", LITELLM_CONFIG.read_text(), re.M)


def halo_models():
    try:
        with urllib.request.urlopen(HALO_MODELS, timeout=5) as r:
            return [m["id"] for m in json.load(r)["data"]]
    except OSError:
        return None  # HALO apagado: no se despierta para esto


def ask_research(text):
    """Un turno en RESEARCH desde un contenedor desechable en gw-research; la clave va por --env-file."""
    code = r'''
import json, os, sys, urllib.request
body = json.dumps({"model": "hermes-agent", "input": sys.stdin.read(),
                   "conversation": "sip-model-eval-" + os.environ["WEEK"]})
req = urllib.request.Request("http://10.22.0.10:8642/v1/responses", body.encode(), {
    "Authorization": "Bearer " + os.environ["API_SERVER_KEY"], "Content-Type": "application/json"})
with urllib.request.urlopen(req, timeout=1500) as r:
    d = json.load(r)
print("".join(c.get("text", "") for o in d.get("output", []) if o.get("type") == "message"
              for c in o.get("content", [])).strip())
'''
    return run("docker", "run", "--rm", "-i", "--network", "gw-research", "--read-only", "--cap-drop", "ALL",
               "--user", "65534:65534", "--env-file", RESEARCH_ENV, "-e", "WEEK=" + time.strftime("%F-%H%M"),
               "--entrypoint", "python3", IMG, "-c", code, stdin=text, timeout=1600).strip()


def main():
    m = metrics()
    conf = configured()
    halo = halo_models()
    names = {c.split("/")[-1] for c in conf}
    table = "\n".join(" | ".join(r) + ("" if r[0].split("/")[-1] in names else " | no configurado")
                      for r in m) or "(sin uso)"
    prompt = PROMPT.format(configured=", ".join(conf), halo=", ".join(halo) if halo else "HALO apagado",
                           metrics=table, min_calls=MIN_CALLS)
    if "--solo-metricas" in sys.argv:
        print(prompt)
        return 0
    try:
        proposal = ask_research(prompt) or "(RESEARCH no devolvió texto)"
    except Exception as e:  # sin propuesta, el informe sale igual con las cifras
        proposal = f"(RESEARCH no respondió: {e})"

    date = time.strftime("%F")
    OUT_DIR.mkdir(mode=0o700, exist_ok=True)
    report = OUT_DIR / f"{date}.md"
    report.write_text(f"# Evaluación de modelos {date}\n\n## Datos enviados a RESEARCH\n\n{prompt}\n\n"
                      f"## Propuesta de RESEARCH\n\n{proposal}\n")

    top = ", ".join(f"{r[0].split('/')[-1]} {r[1]}/{r[2]}%" for r in m
                    if r[0].split("/")[-1] in names)[:200] or "sin uso"
    text = (f"Evaluación semanal de modelos (nada se cambia sin tu decisión)\n"
            f"Uso 7 días (llamadas/% fallos): {top}\n\n{proposal}")[:950]
    text += f"\n\nInforme: {report}"
    stamp = int(time.time())
    tmp = OUTBOX / f".modelos-{stamp}.tmp"
    tmp.write_text(text + "\n")
    tmp.replace(OUTBOX / f"modelos-{stamp}.txt")
    print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
