# Memoria (v2.4 Fase 8, decisión 9)

Estado a 02-11-2026: **desplegada y verificada**.

## Diseño aplicado

- **Memoria nativa de Hermes** (`MEMORY.md` / `USER.md` en el home de cada zona), sin proveedor externo
  (`memory.provider` vacío en las tres zonas) ni base vectorial. Cosecha Markdown: aplazada (v2.4).
- **`memory.write_approval: true` y `skills.write_approval: true`** en PERSONAL (raíz y todos los perfiles
  de `hermes-webui`), CODING (volumen y `config.api.yaml`) y RESEARCH (`research/config.yaml`). Ninguna
  escritura de memoria o skills se guarda sin revisión: queda en `pending/{memory,skills}/`.
  Revisión: `/memory pending|approve <id>|reject <id>` y `/skills pending|diff|approve|reject` en la WebUI.
- **Separación física:** cada zona tiene su volumen; RESEARCH no tiene herramienta de memoria
  (`browser` + `entrada`) y su única escritura hacia fuera es `00_entrada` por filegate.
- **Sin instalaciones al vuelo:** `security.allow_lazy_installs: false` en PERSONAL y RESEARCH,
  `HERMES_DISABLE_LAZY_INSTALLS=1` en CODING.
- **Curación semanal:** `sip-memory-review.timer` (domingos 10:00) cuenta escrituras pendientes por zona,
  sin leer su contenido, y avisa por Telegram (`sip-notify`) si hay alguna. Instalación: `apply.sh`.

## Verificado el 02-11-2026

- **O12:** petición de guardar un marcador distinto en cada zona. PERSONAL y CODING lo dejaron en
  `pending/memory/` (no en `MEMORY.md`); cada marcador solo aparece en su zona. RESEARCH no puede escribir
  memoria: dejó el marcador como nota en `00_entrada` (filegate `ALLOW`, por diseño), luego en cuarentena
  (`a8efacbb-…`). Escrituras de prueba rechazadas con `/memory reject`.
- **Captura de red de PERSONAL** (`tcpdump`, todo lo que sale de `172.29.0.2` salvo HALO): en la primera,
  192 SYN a PyPI (`151.101.x.223:443`) sin datos, cortados por el firewall (instalación al vuelo de
  `edge-tts`). Tras desactivarlas: **0 paquetes** fuera de HALO.
- **Recordatorio:** ejecutado a mano con 1 pendiente en PERSONAL y 1 en CODING; aviso enviado por Telegram.

## Pendiente

- Auditoría de skills creadas por el agente: `curator` sigue activo (mantenimiento de skills propias);
  sus cambios quedan en el ledger (`hermes curator ledger`). Revisar en la auditoría trimestral (Fase 10).
- RESEARCH no tiene WebUI: su revisión pendiente se hace con `docker exec -it hermes-research hermes`.
