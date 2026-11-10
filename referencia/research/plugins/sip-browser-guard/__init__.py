"""Cierra file:// y similares: dentro del contenedor hay una clave virtual y un token de filegate."""
from urllib.parse import urlsplit


def block_local_schemes(tool_name="", args=None, **kwargs):
    if tool_name != "browser_navigate" or not isinstance(args, dict):
        return None
    url = str(args.get("url", "")).strip()
    # Sin esquema, Hermes y Chromium lo tratan como web; view-source:file: da esquema view-source.
    scheme = urlsplit(url).scheme.lower() if "://" in url or url.lower().startswith(("file:", "view-source:", "data:", "about:", "chrome:", "javascript:")) else "https"
    if scheme in ("http", "https"):
        return None
    return {"action": "block", "message": f"Esquema {scheme or 'vacío'} no permitido; solo http y https."}


def register(ctx):
    ctx.register_hook("pre_tool_call", block_local_schemes)
