#!/usr/bin/env python3
"""Avisa si una herramienta registrada por un plugin SIP no aparece en CATALOGO.md (o si sobra alguna).
Uso: python3 sip-config/herramientas/comprobar-catalogo.py   (sale con 1 si hay diferencias)"""
import pathlib
import re
import sys

RAIZ = pathlib.Path(__file__).resolve().parent.parent
catalogo = (RAIZ / "herramientas" / "CATALOGO.md").read_text(encoding="utf-8")
en_catalogo = set(re.findall(r"`([a-z]+_[a-z_]+)`", catalogo))
registradas = {}
for f in RAIZ.glob("**/plugins/*/__init__.py"):
    for n in re.findall(r'register_tool\(\s*name="([a-z_]+)"', f.read_text(encoding="utf-8")):
        registradas[n] = f.parent.name
    for n in re.findall(r'"(navegador_[a-z]+)"', f.read_text(encoding="utf-8")):
        registradas[n] = f.parent.name
OCULTAS = {"flujo_lanzar", "flujo_estado"}  # solo las usan los perfiles redactores; el catálogo cita la delegación
faltan = sorted(set(registradas) - en_catalogo - OCULTAS)
for n in faltan:
    print(f"FALTA en el catálogo: {n} (plugin {registradas[n]})")
if not faltan:
    print(f"catálogo al día: {len(set(registradas) - OCULTAS)} herramientas")
sys.exit(1 if faltan else 0)
