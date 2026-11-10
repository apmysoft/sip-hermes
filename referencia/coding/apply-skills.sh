#!/bin/sh
# Despliega skills de SIP (root, en Neo, desde una copia del repo con sip-config/):
#   - sip-lecciones-codigo en hermes-coding, propiedad de root y 0644: el agente (993) la lee y no la edita.
#   - kanban-router (fuente: modelos/kanban-router-SKILL.md) en hermes-coding y, si su copia era igual a la
#     anterior del repo, en hermes-webui (PERSONAL).
# Rollback: copiar los SKILL.md de "$B" a su sitio (o borrar el directorio de sip-lecciones-codigo).
set -eu
R=$(cd "$(dirname "$0")/.." && pwd)
B=/root/sip-agent-backups/$(date +%F)/skills-$(date +%H%M%S)
S=/home/hermeswebui/.hermes/skills
install -d -m 700 "$B"

put() {  # contenedor  fichero-origen  destino  propietario
  docker exec "$1" sh -c "test -f '$3' && cat '$3'" > "$B/$1-$(basename "$(dirname "$3")").md" || true
  docker exec -i "$1" sh -c "mkdir -p '$(dirname "$3")' && cat > '$3.tmp' && chown $4 '$3.tmp' && chmod 644 '$3.tmp' && mv '$3.tmp' '$3'" < "$2"
  docker exec -i "$1" cmp -s "$3" - < "$2"
  echo "$1: $3 ($(docker exec "$1" stat -c '%U:%G %a' "$3"))"
}

# Primera versión (03-11, 00:38) en la raíz de skills: se movió a software-development.
if docker exec hermes-coding test -d "$S/sip-lecciones-codigo"; then
  docker exec hermes-coding cat "$S/sip-lecciones-codigo/SKILL.md" > "$B/hermes-coding-sip-lecciones-codigo-raiz.md"
  docker exec hermes-coding sh -c "rm '$S/sip-lecciones-codigo/SKILL.md' && rmdir '$S/sip-lecciones-codigo'"
fi
put hermes-coding "$R/coding/skills/sip-lecciones-codigo/SKILL.md" "$S/software-development/sip-lecciones-codigo/SKILL.md" 0:0
put hermes-coding "$R/modelos/kanban-router-SKILL.md" "$S/kanban-router/SKILL.md" \
  "$(docker exec hermes-coding stat -c '%u:%g' "$S/kanban-router/SKILL.md")"

P=/home/hermeswebui/.hermes/profiles/personal/skills/kanban-router/SKILL.md
if docker exec hermes-webui test -f "$P"; then
  if docker exec hermes-webui grep -q 'model="qwen3-coder:30b"' "$P"; then
    put hermes-webui "$R/modelos/kanban-router-SKILL.md" "$P" "$(docker exec hermes-webui stat -c '%u:%g' "$P")"
  else
    echo "hermes-webui: $P difiere de lo esperado; no se toca"
  fi
fi

docker exec -u 993 -e HOME=/home/hermeswebui -w /opt/hermes-agent hermes-coding /app/venv/bin/python -c '
from pathlib import Path
s = Path("/home/hermeswebui/.hermes/skills")
for n in ("software-development/sip-lecciones-codigo", "kanban-router"):
    t = (s / n / "SKILL.md").read_text()
    assert t.startswith("---\nname: " + n.split("/")[-1] + "\n"), n
print("CODING: skills legibles por el agente")
try:
    open(s / "software-development" / "sip-lecciones-codigo" / "SKILL.md", "a")
    raise SystemExit("FAIL: el agente puede escribir la skill de lecciones")
except PermissionError:
    print("CODING: el agente no puede editar sip-lecciones-codigo")'
# Hermes cachea en el proceso la lista de skills del prompt: sin reinicio, la skill nueva no aparece.
(cd /home/usuario/sip-fase7-coding && docker compose restart hermes-coding hermes-coding-api)
echo "RESULTADO: OK. Copia previa en $B"
