# Índice de texto de PARA (con OCR en HALO)

Desplegado en Neo el 09-11-2026 por decisión del usuario. Garantías (integridad de PARA) tiene su propia carpeta,
`../garantias/`, y se resume al final. Historial y pruebas en 99-NOTAS (entradas del 09-11).

## Qué hace

PERSONAL puede **buscar dentro del contenido** de los documentos de PARA (`documentos_buscar_texto`) y encontrar
ficheros por nombre al instante (`documentos_buscar`, que consulta primero las rutas del índice). El índice es una
base SQLite FTS5 en Neo, sin tildes en las búsquedas, que PERSONAL monta en **solo lectura** en `/indice`.

| Pieza | Dónde | Cuándo | Qué hace |
|---|---|---|---|
| `sip-indice.py` | Neo, usuario `sip-indice` (grupo `hermes-ro`), sin red | 00:30, hasta 85 min | Recorre las 5 carpetas de PARA y extrae el texto de PDF con capa de texto, ofimática (DOCX/XLSX/PPTX/ODF), HTML, correo (EML), RTF y texto plano. Solo procesa lo nuevo o cambiado. |
| `sip-indice-ocr.py` | Neo → HALO | 02:00; no empieza documentos nuevos desde las 05:50; tope duro a las 06:00 | Toma los PDF escaneados («pendiente-ocr»), despierta HALO por WOL si hace falta y los pasa por el OCR de `sip-medios` (OCRmyPDF con todos los núcleos de HALO). |
| `sip-wol-indice.path/.service` | Neo | bajo demanda | Mismo emisor WOL y mismo cupo (5/h) que el resto; carpeta propia `/var/lib/sip-indice-wol/`. |

## Reglas de contenido

- **Libros fuera:** los PDF de más de 100 páginas (`--max-paginas-pdf`) entran solo por el nombre (`metodo=libro`),
  así que se encuentran por título pero no por contenido. Los ebooks (epub, mobi…) no se indexan. Un índice
  aparte para libros queda pospuesto hasta la purga del disco (decisión del usuario).
- Como mucho 400.000 caracteres por documento; documentos de más de 200 MB solo por nombre.
- **Nombres de fichero que no son UTF-8:** se saltan y se cuentan (`nombre_no_utf8`); SQLite no los admite.
- **Privacidad:** a HALO solo viaja el PDF, siempre con el nombre `documento.pdf`. Los registros solo llevan
  recuentos y tiempos. Con el modo ausencia activo no se despierta a HALO.

## Borrados y espacio

- Lo que se borra de PARA sale del índice **esa misma noche**. El recorrido siempre es completo: al acabarse el
  tiempo solo deja de extraer.
- **Protección:** si una carpeta de primer nivel falta o no se puede leer (PARA medio montado, permisos), o si no
  se puede entrar en una subcarpeta, se **conservan** sus entradas.
- Si más del 20 % del fichero es espacio libre, se compacta (`VACUUM`).
- Tamaño estimado (estadística agregada del 09-11): 0,3–0,5 GB con los libros fuera.

## Seguridad

- `sip-indice` solo lee PARA (grupo `hermes-ro` y `other::r`). La base vive en `/var/lib/sip-indice`
  (`sip-indice:usuario`, 2750/0640), que PERSONAL lee en solo lectura.
- `sip-indice.service`: `PrivateNetwork=yes`, `ProtectSystem=strict`, `MemoryMax=3G`, `Nice=19`, I/O en reposo.
- `sip-indice-ocr.service`: red **solo hacia la IP de HALO** (`IPAddressAllow=${HALO_TAILNET_IP}`), `MemoryMax=1G`,
  `RuntimeMaxSec=4h`. No se ha tocado nftables.
- Hay 4 carpetas que `hermes-ro` no puede leer y que se dejan así a propósito: las copias del estado SIP, los
  backups de SIP, los datos de PostgreSQL de proyecto-personal y las descargas de filegate.

## Instalación y vuelta atrás

```sh
# Root, en Neo, desde este directorio del checkout
sh apply.sh        # usuario, carpeta, servicio y timer de 00:30
sh apply-ocr.sh    # --sin-ocr, servicio OCR de las 02:00 y WOL propio (copia y rollback.sh en /root/sip-agent-backups/<fecha>/indice-ocr/)
```

PERSONAL monta el índice desde `../hermes/compose.para-ro.yml` (WebUI) y `../personal-api/docker-compose.yml`
(API). `documentos_buscar_texto` solo se activa si el índice existe al arrancar.

Para quitarlo del todo: `systemctl disable --now sip-indice.timer sip-indice-ocr.timer sip-wol-indice.path`, borrar
las unidades y `/usr/local/sbin/sip-indice*.py`, quitar el montaje `/indice` de los dos compose y borrar
`/var/lib/sip-indice` y `/var/lib/sip-indice-wol`.

## Comprobar que funciona

```sh
journalctl -u sip-indice -u sip-indice-ocr --since yesterday -o cat | grep -E "total=|pendientes=|WOL|recorrido|ilegibles"
sudo python3 -c "import sqlite3;c=sqlite3.connect('file:/var/lib/sip-indice/indice.db?mode=ro',uri=True);print(c.execute('select metodo,count(*) from docs group by metodo').fetchall())"
```

## Garantías (`../garantias/`)

`sip-garantias.py` (usuario `sip-indice`, sin red) guarda una huella BLAKE2b de cada fichero de PARA y vuelve a
comprobar una parte cada noche. Detecta:

- **corrupción silenciosa** (contenido distinto con el mismo tamaño y la misma fecha);
- PDF, ZIP y Office dañados, y JPEG truncados;
- duplicados exactos de más de 1 MB.

Funcionamiento:

- **Cada noche a las 02:15**, hasta 150 GB o 210 minutos. Los ficheros nuevos se procesan por **prioridad**:
  documentos y ofimática, fotos, libros y cómics, otros, audio, comprimidos y, al final, vídeo; dentro de cada
  grupo, de menor a mayor.
- El informe, con rutas, queda en `/var/lib/sip-garantias/informes/`, que lee el usuario. A Telegram solo van
  recuentos, y solo si hay corrupción o daños.
- Nunca borra nada y conserva las huellas de las carpetas que no puede leer.
- Instalación: `sh ../garantias/apply.sh`, después de `apply.sh` de esta carpeta, que crea el usuario `sip-indice`.
