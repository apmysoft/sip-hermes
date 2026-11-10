#!/bin/sh
# Arreglo de O4 (03-11): la contraseña de la WebUI pasa de la variable HERMES_WEBUI_PASSWORD (que hereda
# el terminal del agente) a password_hash en settings.json (PBKDF2, con el código de la propia WebUI).
# Lo ejecuta el USUARIO en Neo, en una terminal interactiva: la contraseña se teclea y nadie más la ve.
#   sh fijar-password-webui.sh personal    → hermes-webui (PERSONAL)
#   sh fijar-password-webui.sh coding      → hermes-coding (WebUI de CODING)
# No cambia el login actual: mientras la variable siga en el contenedor, manda la variable. El cambio
# efectivo llega al recrear el contenedor sin ella (aplicar.sh, lo hace el agente).
set -eu
case "${1:-}" in
    personal) C=hermes-webui; U=1000 ;;
    coding) C=hermes-coding; U=993 ;;
    *) echo "uso: sh fijar-password-webui.sh personal|coding" >&2; exit 2 ;;
esac
docker exec -it -u "$U" -w /app "$C" /app/venv/bin/python -c '
import getpass, os, sys
sys.path.insert(0, "/app")
os.environ.pop("HERMES_WEBUI_PASSWORD", None)
p1 = getpass.getpass("Nueva contraseña de la WebUI: ")
p2 = getpass.getpass("Repítela: ")
if not p1.strip() or p1 != p2:
    sys.exit("No coinciden o está vacía: no se ha cambiado nada.")
if len(p1.strip()) < 12:
    sys.exit("Mínimo 12 caracteres: no se ha cambiado nada.")
from api.config import save_settings, load_settings
from api.auth import _hash_password
save_settings({"_set_password": p1})
ok = load_settings().get("password_hash") == _hash_password(p1.strip())
print("password_hash guardado y comprobado" if ok else "ERROR: el hash guardado no coincide")
sys.exit(0 if ok else 1)
'
