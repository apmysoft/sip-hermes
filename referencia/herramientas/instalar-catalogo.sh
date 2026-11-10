#!/bin/sh
# Instala CATALOGO.md como la skill `herramientas` de PERSONAL (WebUI: perfil personal; API/Telegram: raíz).
# Una sola fuente: el SKILL.md se genera aquí. Volver a lanzarlo cada vez que cambie el catálogo.
# Root, en Neo, desde este directorio. Rollback: borrar los dos directorios `herramientas` de skills.
set -eu
cd "$(dirname "$0")"
python3 comprobar-catalogo.py
V=${DOCKER_DATA}/docker_root/volumes/hermes_hermes-home/_data
T=$(mktemp)
{
  printf '%s\n' '---' 'name: herramientas' \
    'description: Catálogo de herramientas SIP (qué se puede pedir, en qué zona y dónde queda el resultado). Úsala cuando el usuario pregunte qué herramientas hay, qué puede hacer o pida el catálogo.' \
    '---' '' \
    'Muestra al usuario el catálogo siguiente tal cual, o solo la parte por la que pregunte. No inventes herramientas que no estén aquí.' ''
  cat CATALOGO.md
} > "$T"
for d in "$V/skills/herramientas" "$V/profiles/personal/skills/herramientas"; do
  install -d -o 1000 -g 1000 -m 750 "$d"
  install -o 1000 -g 1000 -m 640 "$T" "$d/SKILL.md"
done
rm -f "$T"
echo "RESULTADO: OK (skill herramientas instalada en raíz y perfil personal)"
