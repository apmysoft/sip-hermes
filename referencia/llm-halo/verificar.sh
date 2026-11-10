#!/bin/sh
# Comprobación de los modelos de HALO tras un arranque (05-11). Sin root. Solo lectura, salvo un turno corto.
# Uso: sh verificar.sh   (en HALO o desde cualquier nodo de la tailnet con acceso a :11434)
H=http://${HALO_TAILNET_IP}:11434
f=0
echo "llama-swap: $(systemctl is-active llama-swap 2>/dev/null) / $(systemctl is-enabled llama-swap 2>/dev/null)"
echo "ollama:     $(systemctl is-active ollama 2>/dev/null) / $(systemctl is-enabled ollama 2>/dev/null)"
echo "fallidas:   $(systemctl --failed --no-legend 2>/dev/null | wc -l)"
n=$(curl -sf $H/v1/models | python3 -c 'import json,sys; print(len(json.load(sys.stdin)["data"]))' 2>/dev/null) || n=0
echo "modelos:    $n (esperados 13)"; [ "$n" = 13 ] || f=1
r=$(curl -sf $H/v1/chat/completions -H 'Content-Type: application/json' \
  -d '{"model":"qwen3.8:27b","messages":[{"role":"user","content":"Responde solo OK"}],"max_tokens":400}' \
  | python3 -c 'import json,sys; d=json.load(sys.stdin); print(d["choices"][0]["message"]["content"].strip()[:10], round(d["timings"]["predicted_per_second"]), "t/s")' 2>/dev/null) || r=""
echo "turno:      ${r:-FALLO}"; [ -n "$r" ] || f=1
[ $f = 0 ] && echo "RESULTADO: OK" || { echo "RESULTADO: FALLO (journalctl -u llama-swap -n 30)"; exit 1; }
