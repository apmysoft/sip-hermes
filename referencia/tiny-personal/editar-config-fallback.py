"""Parte D del respaldo de PERSONAL (v2.4 §H.3, 06-11): el tiny de Neo como PRIMER fallback.
Proveedor propio `tiny_neo` (para que Hermes sepa que tiene 32K) y primera entrada de `fallback_providers`:
Hermes 0.22.7 solo cambia una vez de proveedor por turno («Rebuilt-message restart limit (1)»), así que
detrás de los modelos de HALO no se llegaba nunca (prueba del 06-11). Los de HALO quedan detrás. Edición de texto mínima en el mismo fichero (conserva dueño, modo e inodo,
necesario para config.api.yaml, montado como fichero suelto). Idempotente. Valida el YAML.
Uso: python3 editar-config-fallback.py <config.yaml>"""
import sys
import yaml

URL = "http://172.29.0.1:11435/v1"
f = sys.argv[1]
s = open(f, encoding="utf-8").read()
c = yaml.safe_load(s)
FB = ("- provider: custom:tiny_neo\n"
      "  model: qwen3-4b-instruct\n"
      f"  base_url: {URL}\n")
PROV = ("  tiny_neo:\n"
        f"    base_url: {URL}\n"
        "    default_model: qwen3-4b-instruct\n"
        "    context_length: 65536\n")
fb = c.get("fallback_providers") or []
if fb and fb[0].get("model") == "qwen3-4b-instruct" and "tiny_neo" in (c.get("providers") or {}):
    print(f"{f}: el tiny ya es el primer fallback"); sys.exit(0)
assert "\nfallback_providers:\n" in s and "\ndatabase:\n" in s, "fallback_providers/database no están donde se esperaba"
s = s.replace(FB, "")                       # si ya estaba (al final), se quita para ponerlo primero
if "tiny_neo" not in (c.get("providers") or {}):
    assert "\nproviders:\n  ollama:\n" in "\n" + s, "providers.ollama no está donde se esperaba"
    s = s.replace("providers:\n  ollama:\n", "providers:\n" + PROV + "  ollama:\n", 1)
s = s.replace("\nfallback_providers:\n", "\nfallback_providers:\n" + FB, 1)
n = yaml.safe_load(s)
halo = [x["model"] for x in fb if x.get("model") != "qwen3-4b-instruct"]
assert n["providers"]["tiny_neo"]["context_length"] == 65536
assert [x["model"] for x in n["fallback_providers"]] == ["qwen3-4b-instruct"] + halo
assert n["model"] == c["model"]
with open(f, "r+", encoding="utf-8") as fh:
    fh.seek(0); fh.write(s); fh.truncate()
print(f"{f}: fallback -> {[x['model'] for x in n['fallback_providers']]}")
