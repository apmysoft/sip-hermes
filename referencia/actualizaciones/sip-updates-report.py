#!/usr/bin/env python3
"""Informe semanal de actualizaciones de Neo (v2.4 Fase 9). Sin LLM; no aplica nada.

- apt: lo pendiente, separando lo excluido de los parches automáticos (núcleo, NVIDIA, Docker),
  y lo que unattended-upgrades instaló en la última semana.
- Docker: imágenes en uso cuya etiqueta de origen apunta ya a otro digest en el registro.
  Se decide servicio a servicio (las fijadas por digest no se mueven solas).
- Hermes Agent y Hermes WebUI: versión instalada frente a la última publicada en GitHub.
Entrega: bandeja de sip-notify (Telegram, tope de 1000 caracteres). --dry-run solo imprime.
"""
import json
import os
import re
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

OUTBOX = Path(os.environ.get("SIP_NOTIFY_OUTBOX", "/var/lib/sip-notify/outbox"))
UU_LOG = Path("/var/log/unattended-upgrades/unattended-upgrades.log")
EXCLUDED = re.compile(r"^(linux-|.*nvidia|docker|containerd)")
HERMES_CT = "hermes-webui"
# Imágenes construidas en Neo (no están en ningún registro): Hermes va por su versión; el resto, aparte.
LOCAL_IMAGES = re.compile(r"^(hermes-|ant-and-hopper-)")


def run(*cmd, timeout=60):
    return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout).stdout


def safe(fn, default):
    try:
        return fn()
    except Exception as e:  # una fuente rota no debe impedir el resto del informe
        print(f"<4>{fn.__name__}: {e}", file=sys.stderr)
        return default


def apt_pending():
    names = [l.split("/")[0] for l in run("apt", "list", "--upgradable").splitlines() if "/" in l]
    held = [n for n in names if EXCLUDED.match(n)]
    return len(names), held


def uu_last_week():
    if not UU_LOG.exists():
        return 0
    since = time.strftime("%Y-%m-%d", time.localtime(time.time() - 7 * 86400))
    n = 0
    for line in UU_LOG.read_text(errors="replace").splitlines():
        # "2026-11-03 06:35:12,123 INFO Packages that were upgraded: a b c" (o en español)
        if line[:10] >= since and re.search(r"(Packages that were upgraded|Paquetes actualizados):", line):
            n += len(line.split(":", 3)[-1].split())
    return n


def docker_updates():
    names = run("docker", "ps", "--format", "{{.Names}}").split()
    seen, out, failed = {}, [], 0
    for name in sorted(names):
        img = run("docker", "inspect", "-f", "{{.Image}}", name).strip()
        if img not in seen:
            info = json.loads(run("docker", "image", "inspect", img))[0]
            tags = [t for t in info.get("RepoTags") or [] if "/" in t or ":" in t]
            digests = info.get("RepoDigests") or []
            seen[img] = None
            if tags and digests and not LOCAL_IMAGES.match(tags[0]):
                tag = tags[0]
                repo = tag.rsplit(":", 1)[0]
                local = {d.split("@")[1] for d in digests if d.split("@")[0] == repo}
                remote = run("docker", "buildx", "imagetools", "inspect", tag,
                             "--format", "{{.Manifest.Digest}}", timeout=30).strip()
                if not remote.startswith("sha256:"):
                    failed += 1  # sin respuesta del registro: no se da por actualizada
                    print(f"<4>sin digest remoto para {tag}", file=sys.stderr)
                elif local and remote not in local:
                    seen[img] = tag
        if seen[img]:
            out.append(name)
    return out, failed


def latest_release(repo):
    req = urllib.request.Request(f"https://api.github.com/repos/{repo}/releases/latest",
                                 headers={"Accept": "application/vnd.github+json"})
    with urllib.request.urlopen(req, timeout=15) as r:
        return json.load(r)["tag_name"]


def hermes_versions():
    agent = re.search(r"v[\d.]+", run("docker", "exec", HERMES_CT, "/app/venv/bin/hermes", "--version"))
    webui = re.search(r"## \[(v[\d.]+)\]", run("docker", "exec", HERMES_CT, "grep", "-m1", r"^## \[v",
                                              "/app/CHANGELOG.md"))
    return [("Hermes Agent", agent and agent.group(0), safe(lambda: latest_release("NousResearch/hermes-agent"), "?")),
            ("Hermes WebUI", webui and webui.group(1), safe(lambda: latest_release("nesquena/hermes-webui"), "?"))]


WHISPER_VER = "v1.9.5"  # sip-whisper en HALO (sip-config/whisper/install-halo.sh); actualizar al cambiarla


def herramientas_versions():
    """yt-dlp (RESEARCH) y whisper.cpp (HALO): conviene tenerlas al día (YouTube cambia a menudo)."""
    ytdlp = run("docker", "exec", "-e", "PYTHONPATH=/opt/yt-dlp", "hermes-research", "python3", "-m",
                "yt_dlp", "--version").strip()
    with urllib.request.urlopen("https://pypi.org/pypi/yt-dlp/json", timeout=15) as r:
        ytdlp_pub = json.load(r)["info"]["version"]
    return [("yt-dlp (RESEARCH)", ytdlp, ytdlp_pub),
            ("whisper.cpp (HALO)", WHISPER_VER, safe(lambda: latest_release("ggml-org/whisper.cpp"), "?"))]


def main():
    lines = ["Informe semanal de actualizaciones (Neo). Nada se aplica sin tu decisión."]
    ap = safe(apt_pending, None)
    lines.append("apt: " + ("no se pudo comprobar" if ap is None else
                 f"{ap[0]} pendientes" + (f"; excluidos de los parches automáticos: {', '.join(ap[1][:8])}"
                                          + (" ..." if len(ap[1]) > 8 else "") if ap[1] else "")))
    lines.append(f"Parches automáticos instalados esta semana: {safe(uu_last_week, '?')}")
    if Path("/run/reboot-required").exists():
        lines.append("Neo pide reinicio (/run/reboot-required).")
    du = safe(docker_updates, None)
    lines.append("Docker con versión nueva de su etiqueta: " + ("no se pudo comprobar" if du is None else
                 (", ".join(du[0]) if du[0] else "ninguno")
                 + (f" ({du[1]} imagen(es) sin comprobar)" if du[1] else "")))
    for name, have, latest in safe(hermes_versions, []):
        lines.append(f"{name}: instalada {have or '?'}, publicada {latest}"
                     + (" (WebUI según CHANGELOG)" if name.endswith("WebUI") else ""))
    for name, have, latest in safe(herramientas_versions, []):
        if have != latest:
            lines.append(f"{name}: instalada {have or '?'}, publicada {latest}")
    lines.append("HALO: Ubuntu aplica solo sus parches de seguridad; el resto, en su gestor de actualizaciones.")
    text = "\n".join(lines)
    if "--dry-run" in sys.argv:
        print(text)
        print(f"({len(text)} caracteres)")
        return 0
    stamp = int(time.time())
    tmp = OUTBOX / f".actualizaciones-{stamp}.tmp"
    tmp.write_text(text + "\n")
    tmp.replace(OUTBOX / f"actualizaciones-{stamp}.txt")
    print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
