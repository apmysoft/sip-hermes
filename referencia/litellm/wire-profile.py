#!/usr/bin/env python3
"""Cablea un perfil Hermes a LiteLLM (Fase 6 Bloque B). Uso: wire-profile.py <config.yaml>

Edición de texto mínima, sin reserializar el YAML. La clave no va aquí: se
añade aparte como LITELLM_API_KEY en el .env del perfil (ver README).
PERSONAL no se cablea nunca: v2.4 lo limita a modelos locales.
"""
import re
import sys

p = sys.argv[1]
s = open(p).read()
if 'litellm:' in s:
    sys.exit('ya cableado: ' + p)
head, rest = s.split('providers:\n', 1)
m = re.search(r'^(  default: (\S+)\n  provider: )custom:ollama$', head, re.M)
if not m:
    sys.exit('bloque model inesperado: ' + p)
head = head.replace(m.group(0), m.group(1) + 'custom:litellm')
block = ('  litellm:\n    base_url: http://sip-litellm:4000/v1\n'
         '    key_env: LITELLM_API_KEY\n    default_model: ' + m.group(2) + '\n')
open(p, 'w').write(head + 'providers:\n' + block + rest)
