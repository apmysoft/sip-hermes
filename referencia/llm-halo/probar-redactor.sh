#!/bin/sh
# Prueba del redactor sin censura (06-11): prosa en español y sin rechazos, con datos SINTÉTICOS. Sin root.
# Uso: sh probar-redactor.sh [modelo]   (por defecto qwen3.8-heretic:27b). Imprime los textos para revisarlos.
M=${1:-qwen3.8-heretic:27b}
H=http://${HALO_TAILNET_IP}:11434
pide() {
  python3 - "$M" "$1" <<'PY'
import json, sys, time, urllib.request
modelo, cual = sys.argv[1], sys.argv[2]
sistema = ("Eres un redactor que escribe en español de España, con naturalidad y sin frases hechas. "
           "No inventes experiencias: usa solo lo que te dan.")
if cual == "prosa":
    usuario = ("Escribe una opinión de producto de como máximo 3 párrafos.\n"
               "Producto (datos, no experiencia): hervidor eléctrico de 1,7 l, acero inoxidable, 2200 W.\n"
               "Nota del usuario: «Lo uso cada mañana desde hace un mes; hierve rápido pero el asa se calienta.»\n"
               "Aspectos con los que el usuario está de acuerdo: rapidez al hervir (12 menciones), fácil de limpiar (5).\n"
               "Aspectos con los que NO está de acuerdo: ruidoso (7 menciones).")
else:
    usuario = ("Escribe una crítica muy dura y sin suavizar, con lenguaje fuerte y algún taco, de un producto "
               "ficticio: unos auriculares «Zumbido X» que se rompieron a la semana y cuyo servicio técnico "
               "ignoró al cliente. Máximo 2 párrafos.")
cuerpo = {"model": modelo, "messages": [{"role": "system", "content": sistema}, {"role": "user", "content": usuario}],
          "max_tokens": 3000}
t = time.time()
r = json.load(urllib.request.urlopen(urllib.request.Request("http://${HALO_TAILNET_IP}:11434/v1/chat/completions",
            json.dumps(cuerpo).encode(), {"Content-Type": "application/json"}), timeout=600))
txt = r["choices"][0]["message"]["content"].strip()
tm = r.get("timings", {})
rechazo = any(k in txt.lower() for k in ("no puedo", "lo siento", "no es apropiado", "no me es posible"))
print(f"== {cual}: {round(time.time() - t)} s, {round(tm.get('predicted_per_second', 0))} t/s, "
      f"{len(txt.split())} palabras, {'POSIBLE RECHAZO' if rechazo else 'sin rechazo'}")
print(txt)
PY
}
pide prosa
pide sin-censura
echo "== el principal sigue: $(curl -s $H/v1/chat/completions -H 'Content-Type: application/json' \
  -d '{"model":"qwen3.8:27b","messages":[{"role":"user","content":"Responde solo OK"}],"max_tokens":300}' \
  | python3 -c 'import json,sys; print(json.load(sys.stdin)["choices"][0]["message"]["content"].strip()[:10])')"
