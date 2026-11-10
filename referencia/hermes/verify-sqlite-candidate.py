"""Verificación sin bases reales ni arranque de Hermes; ejecutar en la candidata."""
import sqlite3

assert sqlite3.sqlite_version == "3.53.4", sqlite3.sqlite_version
with open("/proc/self/maps", encoding="utf-8") as maps:
    assert any("/opt/sip-sqlite/lib/libsqlite3.so" in line for line in maps), "Enlace SQLite inesperado"
with sqlite3.connect(":memory:") as db:
    options = {row[0] for row in db.execute("PRAGMA compile_options")}
    required = {
        "ENABLE_FTS3", "ENABLE_FTS4", "ENABLE_FTS5", "ENABLE_RTREE",
        "ENABLE_COLUMN_METADATA", "ENABLE_SESSION", "ENABLE_PREUPDATE_HOOK",
        "ENABLE_DBPAGE_VTAB", "ENABLE_DBSTAT_VTAB", "ENABLE_UNLOCK_NOTIFY",
        "ENABLE_UPDATE_DELETE_LIMIT", "ENABLE_MATH_FUNCTIONS",
        "THREADSAFE=1", "MAX_VARIABLE_NUMBER=250000", "MAX_FUNCTION_ARG=127",
    }
    assert required <= options, sorted(required - options)
    # Comprobar la API real: no todas las compilaciones publican ENABLE_LOAD_EXTENSION.
    db.enable_load_extension(True)
    db.enable_load_extension(False)
    assert db.execute("SELECT json_extract('{\"ok\":1}', '$.ok')").fetchone() == (1,)
    db.execute("CREATE VIRTUAL TABLE search USING fts5(body)")
    db.execute("INSERT INTO search VALUES ('hermes sqlite')")
    assert db.execute("SELECT count(*) FROM search WHERE search MATCH 'hermes'").fetchone() == (1,)
    db.execute("CREATE VIRTUAL TABLE bounds USING rtree(id, lo, hi)")
    db.execute("CREATE TABLE items(id INTEGER)")
    db.executemany("INSERT INTO items VALUES (?)", [(1,), (2,)])
    db.execute("DELETE FROM items ORDER BY id LIMIT 1")
    assert db.execute("SELECT id FROM items").fetchall() == [(2,)]
    assert db.execute("PRAGMA integrity_check").fetchone() == ("ok",)
print("OK: SQLite 3.53.4, enlace aislado, extensiones y consultas verificadas")
