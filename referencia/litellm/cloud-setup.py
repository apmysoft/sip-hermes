#!/usr/bin/env python3
"""Crea la clave sk-research-cloud si falta y verifica la ruta cloud (root, en Neo).

La clave solo se guarda en /root/sip-litellm-research-cloud.env y no se imprime nunca.
Sale con 1 si falla alguna comprobación. Una llamada real a Gemini por ejecución.
"""
import json
import os
import subprocess
import urllib.error
import urllib.request

PROXY = "http://${NEO_TAILNET_IP}:4000"
ENV_FILE = "/root/sip-litellm.env"
KEYS_FILE = "/root/sip-litellm-keys.json"
CLOUD_ENV = "/root/sip-litellm-research-cloud.env"
CLOUD_MODEL = "gemini-3.5-flash-lite"
LOCAL_MODEL = "qwen3.8:27b"
KIMI_MODEL = "k3.1-pro"
ALLOWED = [CLOUD_MODEL, "gemini-3.8-flash", KIMI_MODEL, LOCAL_MODEL, "gpt-oss:20b"]


def read_env(path):
    with open(path) as f:
        return dict(l.rstrip("\n").split("=", 1) for l in f if "=" in l and not l.startswith("#"))


env = read_env(ENV_FILE)
secrets = [v for k, v in env.items() if k.endswith(("_KEY", "_PASSWORD", "_URL"))]


def scrub(text):
    for s in secrets:
        text = text.replace(s, "[REDACTED]")
    return text


def call(path, key, body=None):
    req = urllib.request.Request(PROXY + path, method="POST" if body else "GET")
    req.add_header("Authorization", "Bearer " + key)
    req.add_header("Content-Type", "application/json")
    data = json.dumps(body).encode() if body else None
    try:
        with urllib.request.urlopen(req, data, timeout=180) as r:
            return r.status, r.read().decode()
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode()


def chat(key, model):
    return call("/v1/chat/completions", key, {
        "model": model,
        "messages": [{"role": "user", "content": "Responde solo: OK"}],
        "max_tokens": 200,
    })


if not os.path.exists(CLOUD_ENV):
    status, body = call("/key/generate", env["LITELLM_MASTER_KEY"], {
        "key_alias": "sk-research-cloud",
        "models": ALLOWED,
        "rpm_limit": 10,
        "max_budget": 1,
        "budget_duration": "1d",
    })
    if status != 200:
        raise SystemExit(f"FAIL crear clave: {status} {scrub(body)[:300]}")
    fd = os.open(CLOUD_ENV, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w") as f:
        f.write("LITELLM_API_KEY=" + json.loads(body)["key"] + "\n")
    print("clave sk-research-cloud creada")

cloud_key = read_env(CLOUD_ENV)["LITELLM_API_KEY"]
secrets.append(cloud_key)
status, body = call("/key/update", env["LITELLM_MASTER_KEY"], {"key": cloud_key, "models": ALLOWED})
if status != 200:
    raise SystemExit(f"FAIL actualizar clave: {status} {scrub(body)[:300]}")
with open(KEYS_FILE) as f:
    zones = {i["zone"]: i["key"] for i in json.load(f)}
secrets += zones.values()

failed = 0


def check(name, ok, detail=""):
    global failed
    failed += not ok
    print(("PASS " if ok else "FAIL ") + name + (" · " + scrub(detail)[:300] if detail else ""))


status, body = chat(cloud_key, CLOUD_MODEL)
answer = ""
if status == 200:
    answer = json.loads(body)["choices"][0]["message"].get("content") or ""
check("cloud con sk-research-cloud", status == 200, f"{status} {answer or body}")

# Con la cuota mensual agotada, Kimi responde 429; eso ya prueba la ruta y la clave.
status, body = chat(cloud_key, KIMI_MODEL)
check("ruta a Kimi", status == 200 or (status == 429 and "monthly usage limit" in body), str(status))
status, body = chat(zones["coding"], KIMI_MODEL)
check("sk-coding sin Kimi", status in (401, 403), str(status))

status, body = chat(zones["coding"], CLOUD_MODEL)
check("sk-coding sin cloud", status in (401, 403), str(status))
status, body = chat(zones["research"], CLOUD_MODEL)
check("sk-research sin cloud", status in (401, 403), str(status))

status, body = chat(zones["coding"], LOCAL_MODEL)
check("HALO por el proxy con sk-coding", status == 200, str(status))

probe = ("import socket\ns=socket.socket();s.settimeout(4)\n"
         "try:\n s.connect(('${LAN_GATEWAY}',80));print('abierto')\n"
         "except Exception:\n print('cerrado')\n")
out = subprocess.run(["docker", "exec", "-i", "sip-litellm", "/app/.venv/bin/python3", "-"],
                     input=probe, capture_output=True, text=True).stdout.strip()
check("LiteLLM sin LAN", out == "cerrado", out)

probe = ("import urllib.request as u;"
         "print(u.urlopen('http://sip-litellm:4000/health/liveliness',timeout=5).status)")
out = subprocess.run(["docker", "exec", "-u", "1000", "hermes-webui", "python3", "-c", probe],
                     capture_output=True, text=True).stdout.strip()
check("hermes-webui alcanza el proxy", out == "200", out)

logs = subprocess.run(["docker", "logs", "sip-litellm"], capture_output=True, text=True)
text = logs.stdout + logs.stderr
check("claves ausentes de los logs", not any(s in text for s in secrets))

print("RESULTADO:", "OK" if not failed else f"{failed} fallos")
raise SystemExit(1 if failed else 0)
