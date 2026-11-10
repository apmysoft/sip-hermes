#!/usr/bin/env python3
"""Auditoría de aprobaciones de Hermes (v2.4 O10; trimestral). En Neo: sudo python3 -I aprobaciones.py

Las aprobaciones «siempre» de Hermes se guardan en `command_allowlist` del config.yaml de cada perfil
(tools/approval.py, save_permanent_allowlist). Aprobado: allowlist vacía o revisada, sin `approvals.mode:
off` y sin clases destructivas permitidas. Por defecto (Hermes 03-11): mode smart; cron, consulta única y
desatendido en deny.
"""
import glob
import sys
import yaml

V = "${DOCKER_DATA}/docker_root/volumes"
fs = [f"{V}/hermes_hermes-home/_data/config.yaml",
      *sorted(glob.glob(f"{V}/hermes_hermes-home/_data/profiles/*/config.yaml")),
      f"{V}/sip-coding_home/_data/config.yaml",
      f"{V}/sip-research_hermes-research-home/_data/config.yaml"]
mal = 0
for f in fs:
    c = yaml.safe_load(open(f)) or {}
    a = c.get("approvals") or {}
    allow = c.get("command_allowlist") or []
    modos = {k: a[k] for k in ("mode", "cron_mode", "single_query_mode", "unattended_mode") if k in a}
    alerta = allow or "off" in modos.values() or a.get("mode") == "yolo"
    mal += bool(alerta)
    print(f"{'REVISAR' if alerta else 'ok':7} {f.split('/volumes/')[1]:55} allowlist={allow} "
          f"modos={modos or '(defecto)'} deny={len(a.get('deny') or [])}")
sys.exit(1 if mal else 0)
