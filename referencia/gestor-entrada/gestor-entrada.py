#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
gestor-entrada.py — Gestor de Entrada SIP (Fase 4, Nivel 1: solo propone).

MODO RENOMBRE (oct-2026, decisión del usuario): NO propone categorías ni
destinos. Lee el contenido parcial de los ficheros legibles de la bandeja de
entrada (00_entrada, recursivo) con el tiny local (llama-swap, 127.0.0.1:11434)
y propone SOLO un nombre que explique el contenido. El humano aprueba por lote
(approve_all) o por ítem; `apply` renombra en el sitio vía filegate (PEP
gestor). Sin aprobación no se toca nada. Las decisiones alimentan el dataset
dorado (S.3).

Alcance honesto: solo ficheros con texto extraíble (pdf/docx/odt/rtf/txt/md/
csv); fotos/vídeos no se tocan (sin visión, renombrar a ciegas es dañino).
Anti ping-pong: los hashes ya renombrados no se reproponen (G.4).

Uso:
  gestor-entrada.py scan                 # propone renombres; lote .md/.json
  gestor-entrada.py apply <lote-id>      # renombra solo aprobados (fail-closed)
  gestor-entrada.py status
  gestor-entrada.py dataset export       # CSV del dataset (a informes/)
  gestor-entrada.py lotes                # lotes con su estado
  gestor-entrada.py decidir <lote-id> todo|ninguno|solo=1,2 [veto=3,7] [nombre=5:Nuevo.pdf]... [via=cli] [simular]
                                         # escribe la decisión humana en el .json (sin editarlo a mano)
  gestor-entrada.py descartar <lote-id> [motivo]
                                         # cierra un lote sin decidir y libera sus ficheros

`decidir` y `descartar` son decisiones humanas: el puente de Hermes no las expone.
"""
import hashlib
import json
import os
import re
import sqlite3
import subprocess
import sys
import urllib.request
import zipfile
from datetime import datetime, timezone
from pathlib import Path

# --- Config (env sobreescribe) ------------------------------------------------
ENTRADA = Path(os.environ.get("GE_ENTRADA", "${PARA_ROOT}/00_entrada"))
INFORMES = Path(os.environ.get("GE_INFORMES", "${STAGING_ROOT}/_staging/_informes"))
STATE_DIR = Path(os.environ.get("GE_STATE_DIR", "/var/lib/sip-gestor-entrada"))
DB = STATE_DIR / "state.db"
LLM_URL = os.environ.get("GE_LLM_URL", "http://127.0.0.1:11434/v1/chat/completions")
MODEL = os.environ.get("GE_MODEL", "qwen3-4b-instruct")
WRAPPER = os.environ.get("GE_WRAPPER", "/usr/local/bin/sip-gestor-filegate")
MAX_ITEMS = int(os.environ.get("GE_MAX_ITEMS", "50"))   # ficheros por lote
HASH_MAX = 512 * 1024 * 1024
EXCERPT_CHARS = 2000
LLM_TIMEOUT = 180

# tipos con texto extraíble (lo que el tiny puede leer para proponer nombre)
RENAME_EXT = {".pdf", ".txt", ".md", ".markdown", ".csv", ".tsv", ".docx",
              ".odt", ".rtf"}

SCHEMA = {
    "name": "propuesta_renombre",
    "schema": {
        "type": "object",
        "properties": {
            "nuevo_nombre": {"type": "string"},
            "confianza": {"type": "number"},
            "abstencion": {"type": "boolean"},
            "motivo": {"type": "string"},
        },
        "required": ["nuevo_nombre", "confianza", "abstencion", "motivo"],
        "additionalProperties": False,
    },
}

SYSTEM_PROMPT = """Eres un asistente que renombra ficheros con títulos que \
expliquen su contenido, para que el usuario no tenga que abrirlos uno por uno. \
Reglas:
- Lee el extracto y propón un nombre corto, claro y descriptivo en el MISMO \
idioma del documento. Conserva la extensión original.
- Sin fechas salvo que aporten (facturas, contratos); sin datos personales \
innecesarios (DNI, teléfonos completos); sin la cadena "pagina X".
- Si el nombre actual ya describe bien el contenido, devuélvelo IGUAL y \
abstencion=false (será un no-op).
- abstencion=true solo si el extracto no basta para nombrar con seguridad."""


# --- Utilidades ----------------------------------------------------------------
def now_iso():
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def log(msg):
    print(f"[{now_iso()}] {msg}", file=sys.stderr)


def sha256_or_big(p: Path):
    try:
        if p.stat().st_size <= HASH_MAX:
            h = hashlib.sha256()
            with p.open("rb") as f:
                for chunk in iter(lambda: f.read(1 << 20), b""):
                    h.update(chunk)
            return h.hexdigest()
    except OSError:
        pass
    try:
        st = p.stat()
        return f"big:{st.st_size}:{int(st.st_mtime)}"
    except OSError as e:
        return f"error:{e}"


def extract_text(p: Path):
    ext = p.suffix.lower()
    try:
        if ext in (".txt", ".md", ".markdown", ".csv", ".tsv", ".rtf"):
            with p.open("rb") as f:
                raw = f.read(8192)
            return raw.decode("utf-8", errors="replace")[:EXCERPT_CHARS]
        if ext == ".pdf":
            out = subprocess.run(
                ["pdftotext", "-f", "1", "-l", "1", str(p), "-"],
                capture_output=True, text=True, timeout=30)
            if out.returncode == 0 and out.stdout.strip():
                return out.stdout[:EXCERPT_CHARS]
            return None
        if ext == ".docx":
            with zipfile.ZipFile(p) as z:
                xml = z.read("word/document.xml")[:200000].decode(
                    "utf-8", errors="replace")
            txt = re.sub(r"<[^>]+>", " ", xml)
            return re.sub(r"\s+", " ", txt).strip()[:EXCERPT_CHARS] or None
        if ext == ".odt":
            with zipfile.ZipFile(p) as z:
                xml = z.read("content.xml")[:200000].decode(
                    "utf-8", errors="replace")
            txt = re.sub(r"<[^>]+>", " ", xml)
            return re.sub(r"\s+", " ", txt).strip()[:EXCERPT_CHARS] or None
    except Exception:
        return None
    return None


# O9 (v2.4): un documento de entrada puede intentar dar órdenes al tiny o a Hermes, que lee los informes.
# Patrones estrechos para no marcar documentación técnica normal; si coinciden, el ítem no pasa por el
# modelo, queda en abstención y se registra ANOMALÍA en el log (fail-closed).
INYECCION_RE = [(etq, re.compile(p, re.I)) for etq, p in (
    ("ignorar instrucciones", r"ignor[ae]\w*\s+(todas\s+|all\s+)?(tus|las|sus|your|previous|any|the)\s+"
                              r"(\w+\s+)?(instrucciones|instructions)"),
    ("suplanta al sistema", r"instrucci[oó]n(es)?\s+del\s+sistema|system\s+prompt|\[\s*system\s*\]"),
    ("habla al agente", r"(nota|mensaje|instrucci[oó]n(es)?|orden(es)?)\s+para\s+"
                        r"(hermes|el\s+(asistente|agente|modelo)|la\s+ia)"),
    ("aprobar sin el usuario", r"no\s+(le\s+)?preguntes\s+al\s+usuario|without\s+asking|"
                               r"(usuario|user)\s+ya\s+(lo\s+)?aprob[oó]|already\s+approved"),
    ("código de confirmación", r"confirm\w*\s+con\s+el\s+c[oó]digo\s+\d{4,}|"
                               r"\b(proponer|confirmar)\b[^.\n]{0,40}\bmodo\s+todo\b"),
    ("secretos de Neo", r"\b(lee|leer|copia|copiar|read|cat|copy)\s+\S*(/root/|\.env\b|/etc/shadow)"),
)]


def sospecha(texto):
    """Etiqueta del primer patrón de inyección que aparece, o None."""
    return next((etq for etq, rx in INYECCION_RE if texto and rx.search(texto)), None)


GENERIC_RE = re.compile(
    r"(descarga|download|documento|doc|scan|escan|image|img|dsc|unnamed|"
    r"fichero|file|nuevo|sin t[ií]tulo|^\W*$|\(\d+\)\.\w)", re.I)


def generic_score(name: str):
    """Mayor = nombre menos informativo (prioridad de renombrado)."""
    s = 0
    if GENERIC_RE.search(name):
        s += 10
    stem = Path(name).stem
    if len(stem) <= 8:
        s += 5
    if re.fullmatch(r"[A-Za-z0-9_-]{1,12}", stem or ""):
        s += 3
    return s


def sanitize_name(propuesto: str, original: Path):
    """Nombre seguro: conserva extensión original, limpia caracteres."""
    ext = original.suffix                # conserva el caso original (.PDF ≠ .pdf)
    base = Path(propuesto).name          # sin componentes de ruta
    base = re.sub(r"[\x00-\x1f<>:\"|?*]", "", base).strip(" .")
    if base.lower().endswith(ext.lower()):
        base = base[: -len(ext)]
    base = re.sub(r"\s+", "_", base)
    base = base[:120].strip("._-") or original.stem
    return base + ext


def proponer_nombre(p: Path, tamano, excerpt):
    prompt = (f"Fichero actual: `{p.name}` ({tamano} bytes).\nExtracto:\n<<<\n"
              f"{excerpt}\n>>>\nPropón el nuevo nombre (con extensión).")
    body = {
        "model": MODEL,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ],
        "max_tokens": 300,
        "temperature": 0.2,
        "response_format": {"type": "json_schema", "json_schema": SCHEMA},
    }
    req = urllib.request.Request(
        LLM_URL, data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=LLM_TIMEOUT) as r:
            data = json.load(r)
        prop = json.loads(data["choices"][0]["message"]["content"])
        if not all(k in prop for k in SCHEMA["schema"]["required"]):
            raise ValueError("JSON incompleto")
        return prop
    except Exception as e:
        return {"nuevo_nombre": p.name, "confianza": 0.0, "abstencion": True,
                "motivo": f"error_llm: {type(e).__name__}: {e}"}


# --- Estado --------------------------------------------------------------------
def db():
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(DB)
    con.executescript("""
    CREATE TABLE IF NOT EXISTS processed(
        path TEXT PRIMARY KEY, hash TEXT,
        first_seen TEXT, last_seen TEXT);
    CREATE TABLE IF NOT EXISTS proposals(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        batch TEXT, path TEXT, hash TEXT,
        nombre_propuesto TEXT, confianza REAL, abstencion INTEGER,
        motivo TEXT, raw_json TEXT, ts TEXT);
    CREATE TABLE IF NOT EXISTS decisions(
        batch TEXT, path TEXT, hash TEXT,
        decision TEXT,
        nombre_modelo TEXT, nombre_final TEXT,
        ts TEXT, PRIMARY KEY(batch, path));
    CREATE TABLE IF NOT EXISTS moves(
        batch TEXT, path TEXT, src TEXT, dst TEXT,
        resultado TEXT, ts TEXT);
    CREATE TABLE IF NOT EXISTS discarded(
        batch TEXT PRIMARY KEY, motivo TEXT, liberados INTEGER, ts TEXT);
    """)
    cols = [r[1] for r in con.execute("PRAGMA table_info(decisions)")]
    if "categoria_modelo" in cols:          # migrar esquema de la era clasificación
        con.execute("ALTER TABLE decisions RENAME TO decisions_old")
        con.executescript("""
        CREATE TABLE decisions(
            batch TEXT, path TEXT, hash TEXT,
            decision TEXT,
            nombre_modelo TEXT, nombre_final TEXT,
            ts TEXT, PRIMARY KEY(batch, path));
        """)
        for r in con.execute("SELECT batch,path,hash,decision,ts FROM decisions_old"):
            con.execute("INSERT INTO decisions VALUES(?,?,?,?,NULL,NULL,?)", r)
        con.execute("DROP TABLE decisions_old")
        con.commit()
    cols = [r[1] for r in con.execute("PRAGMA table_info(proposals)")]
    if "categoria" in cols:                 # migrar esquema de la era clasificación
        con.execute("ALTER TABLE proposals RENAME TO proposals_old")
        con.executescript("""
        CREATE TABLE proposals(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            batch TEXT, path TEXT, hash TEXT,
            nombre_propuesto TEXT, confianza REAL, abstencion INTEGER,
            motivo TEXT, raw_json TEXT, ts TEXT);
        """)
        con.execute(
            "INSERT INTO proposals(batch,path,hash,nombre_propuesto,confianza,"
            "abstencion,motivo,raw_json,ts)"
            " SELECT batch,path,hash,nuevo_nombre,confianza,abstencion,motivo,"
            "raw_json,ts FROM proposals_old ORDER BY id")
        con.execute("DROP TABLE proposals_old")
        con.commit()
    return con


# --- scan ----------------------------------------------------------------------
def scan():
    con = db()
    candidatos = []
    for e in ENTRADA.rglob("*"):
        try:
            if not e.is_file() or e.name.startswith("."):
                continue
            if e.suffix.lower() not in RENAME_EXT:
                continue
            h = sha256_or_big(e)
            if h.startswith("error:"):
                continue
            row = con.execute(
                "SELECT path FROM processed WHERE hash=? AND path!=?",
                (h, str(e))).fetchone()
            if row:
                # ya renombrado antes (mismo hash, otra ruta): actualizar y saltar
                con.execute(
                    "INSERT INTO processed(path,hash,first_seen,last_seen)"
                    " VALUES(?,?,?,?)"
                    " ON CONFLICT(path) DO UPDATE SET hash=excluded.hash,"
                    " last_seen=excluded.last_seen",
                    (str(e), h, now_iso(), now_iso()))
                continue
            row = con.execute("SELECT hash FROM processed WHERE path=?",
                              (str(e),)).fetchone()
            if row and row[0] == h:
                continue  # sin cambios (idempotencia G.4)
            candidatos.append((generic_score(e.name), e, h))
        except OSError:
            continue
    if not candidatos:
        log("sin candidatos nuevos; nada que proponer")
        return 0
    candidatos.sort(key=lambda t: (-t[0], t[1].as_posix()))
    candidatos = candidatos[:MAX_ITEMS]
    lote_id = datetime.now().strftime("lote-%Y%m%d-%H%M%S")
    d = INFORMES / lote_id[5:13]
    d.mkdir(parents=True, exist_ok=True)
    items = []
    md = [f"# Lote de renombres {lote_id}",
          f"_Generado {now_iso()} · Nivel 1: nada se renombra sin aprobación. "
          f"Aprobación por lote: `\"approve_all\": true` en el .json "
          f"(vetar un ítem: `\"veto\": true`)._", ""]
    md.append("| # | Nombre actual | Propuesto | Conf. | |")
    md.append("|---|---|---|---|---|")
    for i, (_, e, h) in enumerate(candidatos, 1):
        excerpt = extract_text(e)
        alerta = sospecha(e.name) or sospecha(excerpt)
        if alerta:
            log(f"ANOMALÍA {lote_id} ítem {i}: posible inyección en el documento ({alerta}); "
                "no pasa por el modelo")
            prop = {"nuevo_nombre": e.name, "confianza": 0.0, "abstencion": True,
                    "motivo": f"posible inyección ({alerta}): revisar a mano"}
        elif excerpt is None:
            prop = {"nuevo_nombre": e.name, "confianza": 0.0,
                    "abstencion": True, "motivo": "sin extracto legible"}
        else:
            prop = proponer_nombre(e, e.stat().st_size, excerpt)
        nombre_final = sanitize_name(prop["nuevo_nombre"], e)
        if nombre_final == e.name:
            prop["abstencion"] = prop.get("abstencion", False)
            motivo = prop["motivo"] + " (nombre actual adecuado)"
        else:
            motivo = prop["motivo"]
        items.append({"item": i, "ruta": str(e), "hash": h,
                      "nombre_actual": e.name, "nombre_propuesto": nombre_final,
                      "confianza": prop["confianza"],
                      "abstencion": bool(prop["abstencion"]), "motivo": motivo,
                      "veto": False, "approved": False})
        marca = "⚠️ abstención" if prop["abstencion"] else (
            "sin cambio" if nombre_final == e.name else "propone renombrar")
        md.append(f"| {i} | `{e.name}` | `{nombre_final}` | "
                  f"{prop['confianza']} | {marca} |")
        con.execute(
            "INSERT INTO proposals(batch,path,hash,nombre_propuesto,confianza,"
            "abstencion,motivo,raw_json,ts) VALUES(?,?,?,?,?,?,?,?,?)",
            (lote_id, str(e), h, nombre_final, prop["confianza"],
             int(bool(prop["abstencion"])), motivo,
             json.dumps(prop, ensure_ascii=False), now_iso()))
        con.execute(
            "INSERT INTO processed(path,hash,first_seen,last_seen)"
            " VALUES(?,?,?,?)"
            " ON CONFLICT(path) DO UPDATE SET hash=excluded.hash,"
            " last_seen=excluded.last_seen",
            (str(e), h, now_iso(), now_iso()))
    md.append("")
    md.append("_Rutas completas en el .json del lote._")
    (d / f"{lote_id}.md").write_text("\n".join(md), encoding="utf-8")
    (d / f"{lote_id}.json").write_text(json.dumps(
        {"lote": lote_id, "generado": now_iso(), "approve_all": False,
         "items": items}, ensure_ascii=False, indent=2), encoding="utf-8")
    con.commit()
    log(f"lote {lote_id}: {len(items)} propuestas → {d}")
    print(lote_id)
    return 0


# --- apply ---------------------------------------------------------------------
def _wrapper(*args):
    return subprocess.run(["sudo", "-n", WRAPPER, *args],
                          capture_output=True, text=True, timeout=60)


def apply(lote_id):
    con = db()
    if con.execute("SELECT 1 FROM discarded WHERE batch=?", (lote_id,)).fetchone():
        log(f"lote descartado: {lote_id}")
        return 1
    matches = sorted(INFORMES.glob(f"**/{lote_id}.json"))
    if not matches:
        log(f"lote no encontrado: {lote_id}")
        return 1
    data = json.loads(matches[0].read_text(encoding="utf-8"))
    approve_all = bool(data.get("approve_all"))
    hechos = saltados = errores = 0
    for it in data["items"]:
        p, h = it["ruta"], it["hash"]
        aprobado = it.get("approved") or (approve_all and not it.get("veto"))
        if not aprobado:
            con.execute(
                "INSERT OR REPLACE INTO decisions VALUES(?,?,?,?,?,?,?)",
                (lote_id, p, h, "rechazado", it["nombre_propuesto"],
                 None, now_iso()))
            saltados += 1
            continue
        if sha256_or_big(Path(p)) != h:
            log(f"SKIP {p}: hash no coincide")
            saltados += 1
            continue
        nuevo = it.get("nombre_final") or it["nombre_propuesto"]
        nuevo = sanitize_name(nuevo, Path(p))
        if nuevo == Path(p).name:
            con.execute(
                "INSERT OR REPLACE INTO decisions VALUES(?,?,?,?,?,?,?)",
                (lote_id, p, h, "aprobado", it["nombre_propuesto"], nuevo,
                 now_iso()))
            saltados += 1
            continue  # no-op
        dst = Path(p).with_name(nuevo)
        if not str(dst).startswith(str(ENTRADA) + os.sep):
            log(f"SKIP {p}: dst fuera de ENTRADA")
            saltados += 1
            continue
        if dst.exists():
            log(f"SKIP {p}: destino ya existe: {dst.name}")
            saltados += 1
            continue
        r = _wrapper("move", p, str(dst))
        salida = (r.stdout + r.stderr).strip()
        ok = r.returncode == 0 and salida.startswith("OK")
        con.execute("INSERT INTO moves VALUES(?,?,?,?,?,?)",
                    (lote_id, p, p, str(dst), salida[:500], now_iso()))
        if not ok:
            # Sin fila en decisions: el lote queda «aplicado con errores» y un apply posterior lo reintenta.
            con.execute("DELETE FROM decisions WHERE batch=? AND path=?", (lote_id, p))
            errores += 1
            log(f"ERROR renombrando {p}: {salida}")
            continue
        con.execute(
            "INSERT OR REPLACE INTO decisions VALUES(?,?,?,?,?,?,?)",
            (lote_id, p, h, "aprobado", it["nombre_propuesto"], nuevo,
             now_iso()))
        hechos += 1
    con.commit()
    log(f"apply {lote_id}: {hechos} renombrados, {saltados} saltados, {errores} con error")
    return 1 if errores else 0


# --- dataset / status ----------------------------------------------------------
def dataset_export():
    con = db()
    rows = con.execute("SELECT * FROM decisions ORDER BY ts").fetchall()
    out = INFORMES / f"dataset-{datetime.now().strftime('%Y%m%d-%H%M%S')}.csv"
    out.parent.mkdir(parents=True, exist_ok=True)
    import csv
    with out.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["batch", "path", "hash", "decision", "nombre_modelo",
                    "nombre_final", "ts"])
        w.writerows(rows)
    log(f"dataset: {len(rows)} decisiones → {out}")
    return 0


def status():
    con = db()
    for t in ("processed", "proposals", "decisions", "moves"):
        n = con.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
        print(f"{t}: {n}")
    return 0


# --- lotes / decidir / descartar -------------------------------------------------
LOTE_RE = re.compile(r"lote-\d{8}-\d{6}")


def _estado(con, lote_id):
    if con.execute("SELECT 1 FROM discarded WHERE batch=?", (lote_id,)).fetchone():
        return "descartado"
    # renombre intentado y fallido: su decisión no se guarda hasta que un apply lo consiga
    if con.execute("SELECT 1 FROM moves m WHERE m.batch=? AND m.resultado NOT LIKE 'OK%' AND NOT EXISTS"
                   " (SELECT 1 FROM decisions d WHERE d.batch=m.batch AND d.path=m.path)",
                   (lote_id,)).fetchone():
        return "aplicado con errores"
    if con.execute("SELECT 1 FROM decisions WHERE batch=?", (lote_id,)).fetchone():
        return "aplicado"
    return "pendiente"


def _lote_json(lote_id):
    """Solo informes/<fecha>/<lote>.json: lo que está en _descartados/ no cuenta."""
    if not LOTE_RE.fullmatch(lote_id):
        return None
    p = INFORMES / lote_id[5:13] / f"{lote_id}.json"
    return p if p.is_file() else None


def lotes():
    con = db()
    for batch, n, abst in con.execute(
            "SELECT batch, COUNT(*), SUM(abstencion) FROM proposals GROUP BY batch ORDER BY batch"):
        estado = _estado(con, batch)
        p = _lote_json(batch)
        if estado == "pendiente" and p:
            dec = json.loads(p.read_text(encoding="utf-8")).get("decidido")
            if dec:
                estado = f"decidido ({dec['resumen']})"
        print(f"{batch}\t{estado}\t{n} propuestas, {abst or 0} abstenciones"
              f"{'' if p else ', sin .json en informes'}")
    return 0


def _numeros(v, items):
    nums = {int(x) for x in v.split(",") if x.strip()}
    malos = nums - set(items)
    if malos:
        raise ValueError(f"ítems inexistentes: {sorted(malos)}")
    return nums


def decidir(lote_id, args):
    con = db()
    p = _lote_json(lote_id)
    if not p:
        log(f"lote no encontrado: {lote_id}")
        return 1
    estado = _estado(con, lote_id)
    if estado != "pendiente":
        log(f"lote {estado}: {lote_id}")
        return 1
    data = json.loads(p.read_text(encoding="utf-8"))
    items = {it["item"]: it for it in data["items"]}
    modo, veto, nombres, via, simular = None, set(), {}, "cli", False
    try:
        for a in args:
            k, _, v = a.partition("=")
            if a == "simular":
                simular = True
            elif a in ("todo", "ninguno"):
                modo = (a, None)
            elif k == "solo":
                modo = ("solo", _numeros(v, items))
            elif k == "veto":
                veto |= _numeros(v, items)
            elif k == "nombre":
                n, _, nuevo = v.partition(":")
                (n,) = _numeros(n, items)
                if not nuevo.strip():
                    raise ValueError(f"nombre vacío para el ítem {n}")
                nombres[n] = nuevo.strip()
            elif k == "via" and re.fullmatch(r"[a-z]{1,16}", v):
                via = v
            else:
                raise ValueError(f"argumento no válido: {a}")
        if not modo:
            raise ValueError("falta todo, ninguno o solo=…")
    except ValueError as e:
        log(str(e))
        return 2
    aprobados = set()
    for n, it in items.items():
        if modo[0] == "todo":
            ok = n not in veto
        elif modo[0] == "solo":
            ok = n in modo[1] and n not in veto
        else:
            ok = False
        # Una abstención solo se aplica con nombre dado por el humano: su «propuesta» es el nombre
        # actual saneado y renombraría solo por cambiar espacios por «_».
        ok = ok and (not it["abstencion"] or n in nombres)
        it["approved"], it["veto"] = ok, not ok
        if n in nombres:
            it["nombre_final"] = sanitize_name(nombres[n], Path(it["ruta"]))
        else:
            it.pop("nombre_final", None)
        if ok:
            aprobados.add(n)
    abst = sum(1 for n, it in items.items() if it["abstencion"] and n not in aprobados)
    cambian = sum(1 for n in aprobados
                  if (items[n].get("nombre_final") or items[n]["nombre_propuesto"])
                  != items[n]["nombre_actual"])
    data["approve_all"] = False      # la decisión va ítem a ítem: explícita
    por = os.environ.get("GE_DECIDIDO_POR") or os.environ.get("SUDO_USER", "?")
    data["decidido"] = {"ts": now_iso(), "via": via, "por": por,
                        "resumen": f"{len(aprobados)} aprobados, {cambian} con cambio de nombre, "
                                   f"{len(items) - len(aprobados) - abst} vetados, "
                                   f"{abst} abstenciones sin tocar"}
    if simular:
        print(f"{lote_id}: {data['decidido']['resumen']}")
        return 0
    tmp = p.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    os.chmod(tmp, p.stat().st_mode & 0o777)
    os.replace(tmp, p)
    print(f"{lote_id}: {data['decidido']['resumen']}. Falta: apply {lote_id}")
    return 0


def descartar(lote_id, motivo):
    con = db()
    if not LOTE_RE.fullmatch(lote_id):
        log(f"lote no válido: {lote_id}")
        return 2
    estado = _estado(con, lote_id)
    if estado != "pendiente":
        log(f"lote {estado}: {lote_id}")
        return 1
    rutas = [r[0] for r in con.execute("SELECT DISTINCT path FROM proposals WHERE batch=?", (lote_id,))]
    if not rutas:
        log(f"lote sin propuestas: {lote_id}")
        return 1
    liberados = 0
    for ruta in rutas:
        # Solo se libera si ningún otro lote vivo (pendiente o aplicado) cubre ese fichero.
        otro = con.execute(
            "SELECT 1 FROM proposals WHERE path=? AND batch!=? AND batch NOT IN "
            "(SELECT batch FROM discarded)", (ruta, lote_id)).fetchone()
        if not otro:
            liberados += con.execute("DELETE FROM processed WHERE path=?", (ruta,)).rowcount
    con.execute("INSERT INTO discarded VALUES(?,?,?,?)", (lote_id, motivo, liberados, now_iso()))
    con.commit()
    print(f"{lote_id}: descartado; {liberados} de {len(rutas)} ficheros vuelven a ser candidatos")
    return 0


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(2)
    cmd = sys.argv[1]
    if cmd == "scan":
        sys.exit(scan())
    if cmd == "apply" and len(sys.argv) == 3:
        sys.exit(apply(sys.argv[2]))
    if cmd == "dataset" and len(sys.argv) == 3 and sys.argv[2] == "export":
        sys.exit(dataset_export())
    if cmd == "status":
        sys.exit(status())
    if cmd == "lotes":
        sys.exit(lotes())
    if cmd == "decidir" and len(sys.argv) >= 4:
        sys.exit(decidir(sys.argv[2], sys.argv[3:]))
    if cmd == "descartar" and len(sys.argv) in (3, 4):
        sys.exit(descartar(sys.argv[2], sys.argv[3] if len(sys.argv) == 4 else ""))
    print(__doc__)
    sys.exit(2)
