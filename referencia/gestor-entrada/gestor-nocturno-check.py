#!/usr/bin/env python3
"""ExecCondition del barrido nocturno: solo deja pasar si hay menos de GE_MAX_PENDIENTES lotes sin decidir.

Un lote está pendiente si tiene propuestas, ninguna decisión y no está descartado. Así el barrido de cada noche no apila
lotes que nadie ha revisado. Salida 0: barrer; 1: saltar (systemd lo registra como condición no
cumplida, no como fallo).
"""
import os
import sqlite3
import sys

DB = os.environ.get("GE_STATE_DB", "/var/lib/sip-gestor-entrada/state.db")
MAX = int(os.environ.get("GE_MAX_PENDIENTES", "2"))

con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
n = con.execute("select count(distinct p.batch) from proposals p where not exists "
                "(select 1 from decisions d where d.batch = p.batch) "
                "and p.batch not in (select batch from discarded)").fetchone()[0]
if n >= MAX:
    print(f"{n} lote(s) sin decidir (máximo {MAX}): se salta el barrido nocturno")
    sys.exit(1)
print(f"{n} lote(s) sin decidir: se barre")
