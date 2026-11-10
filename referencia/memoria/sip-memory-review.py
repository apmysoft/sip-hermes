#!/usr/bin/env python3
"""Recordatorio de curación de memoria (v2.4 Fase 8, decisión 9). Sin LLM.

Cuenta las escrituras de memoria y skills pendientes de revisión (write_approval) en cada zona y,
si hay alguna, deja un aviso en la bandeja de sip-notify. No lee el contenido de las escrituras.
"""
import os
import time
from pathlib import Path

VOL = Path("${DOCKER_DATA}/docker_root/volumes")
ZONES = {
    "PERSONAL (WebUI :8787)": [VOL / "hermes_hermes-home/_data"] + sorted(
        (VOL / "hermes_hermes-home/_data/profiles").glob("*")),
    "CODING (WebUI :8788)": [VOL / "sip-coding_home/_data"],
    "RESEARCH": [VOL / "sip-research_hermes-research-home/_data"],
}
OUTBOX = Path(os.environ.get("SIP_NOTIFY_OUTBOX", "/var/lib/sip-notify/outbox"))


def count(home, kind):
    d = home / "pending" / kind
    return sum(1 for _ in d.glob("*.json")) if d.is_dir() else 0


def main():
    lines = []
    for zone, homes in ZONES.items():
        mem = sum(count(h, "memory") for h in homes)
        sk = sum(count(h, "skills") for h in homes)
        if mem or sk:
            lines.append(f"- {zone}: {mem} de memoria, {sk} de skills")
    if not lines:
        print("sin escrituras pendientes")
        return 0
    text = ("Curación semanal: escrituras pendientes de revisar\n" + "\n".join(lines) +
            "\nRevísalas con /memory pending y /skills pending en la WebUI de cada zona"
            " (RESEARCH: docker exec hermes-research hermes).")
    tmp = OUTBOX / f".memoria-{int(time.time())}.tmp"
    tmp.write_text(text + "\n")
    tmp.replace(OUTBOX / f"memoria-{int(time.time())}.txt")
    print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
