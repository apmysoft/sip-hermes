# Resumen matutino (v2.4 Fase 9)

Estado a 02-11-2026: **desplegado y verificado** en Neo (`sip-morning.timer`, diario a las 8:00).

## Diseño

- **Solo datos del sistema**, sin contenido personal (decisión del usuario del 02-11: Telegram es cloud).
- Los datos se recogen de forma **determinista**; el tiny de Neo (`qwen3-4b-instruct`, llama-swap en
  `127.0.0.1:11434`) solo escribe un titular de una frase. Si el tiny falla, el resumen sale sin titular.
- Fuentes: unidades systemd fallidas (sin `casper-md5check`; las instancias `filegate@` se cuentan
  aparte, porque cada una es una conexión rechazada), contenedores en bucle de reinicios (por contador,
  porque entre reinicios aparecen como running), no sanos o caídos en las últimas 24 h; HALO encendido o
  apagado (sin despertarlo); escrituras de memoria y skills pendientes por zona; lotes del gestor sin
  decisión; gasto de LiteLLM en 24 h por clave; paquetes apt pendientes; último backup de LiteLLM.
- Entrega por la bandeja de `sip-notify` (tope de 1000 caracteres).
- Servicio root con `ProtectSystem=strict`, solo lectura de volúmenes y estado del gestor, escritura solo
  en la bandeja, red solo a localhost y a HALO (`IPAddressAllow`).

Instalación: `apply.sh`. Prueba sin enviar: `/usr/local/sbin/sip-morning.py --dry-run`.

## Verificado el 02-11-2026

- Ejecución real del servicio: `success`, 585-734 caracteres, ~30 s (carga del tiny), aviso `enviado`.
- Corregidos en la prueba: `torproxy` en bucle no aparecía (lo detecta el contador de reinicios);
  contenedores parados hace semanas y su último estado de salud salían como problema.
