#!/usr/bin/env python3
"""sip-kopia-estado.py — copia nocturna, consistente y cifrada del estado SIP para Kopia (v2.4 M.7).

Deja <destino>/sip-estado-AAAAMMDD-HHMMSS.tar.gz.age (usuario 0600) en una carpeta que Kopia ya copia.
Los volúmenes de Hermes son de UID 1000/993/995 y modo 700: KopiaUI (usuario) no los lee, y Hermes nunca
ve el repositorio de Kopia. Las bases SQLite se copian en caliente (API de backup, solo lectura) con
integrity_check; el resto, ficheros tal cual. Cifrado age con la passphrase de /root/sip-hermes-backup.pass
(la misma que sip-hermes-backup-encrypted.sh y sip-litellm-backup.sh). Verifica descifrando cada copia.

Restauración (RUNBOOK-M14): age -d -o /tmp/e.tar.gz <fichero>; tar -xzpf /tmp/e.tar.gz -C <dir>;
cada zona queda en <dir>/sip-estado/<nombre>/ con sus propietarios y modos.
"""
import argparse
from contextlib import closing
import datetime
import os
from pathlib import Path
import shutil
import sqlite3
import subprocess
import tarfile
import tempfile

V = '${DOCKER_DATA}/docker_root/volumes'
FUENTES = {
    'personal': f'{V}/hermes_hermes-home/_data',
    'coding': f'{V}/sip-coding_home/_data',
    'research': f'{V}/sip-research_hermes-research-home/_data',
    'filegate-log': '/var/log/filegate',
    'almacen-extra': '${STAGING_ROOT}',
}
LITELLM = Path('/var/backups/sip-litellm')  # ya cifradas: solo la más reciente
FLUJOS = Path('/var/backups/sip-flujos')    # sip-flujos-backup (06-11), ya cifradas: solo la más reciente
PASS_FILE = Path(os.environ.get('SIP_HERMES_BACKUP_PASS', '/root/sip-hermes-backup.pass'))
CABECERA = b'SQLite format 3\x00'
ANEXOS = ('-wal', '-shm', '-journal')


def es_sqlite(p):
    try:
        with open(p, 'rb') as f:
            return f.read(16) == CABECERA
    except OSError:
        return False


def copiar_arbol(origen, destino, cuenta):
    """Copia origen en destino conservando dueño y modo; SQLite en caliente."""
    for raiz, dirs, ficheros in os.walk(origen, followlinks=False):
        rel = Path(raiz).relative_to(origen)
        d = destino / rel
        d.mkdir(exist_ok=True)
        st = os.lstat(raiz)
        os.chown(d, st.st_uid, st.st_gid)
        os.chmod(d, st.st_mode & 0o7777)
        sqlites = {f for f in ficheros if es_sqlite(Path(raiz) / f)}
        for nombre in dirs + ficheros:
            src, dst = Path(raiz) / nombre, d / nombre
            st = os.lstat(src)
            if os.path.islink(src):
                os.symlink(os.readlink(src), dst)
                os.lchown(dst, st.st_uid, st.st_gid)
                continue
            elif nombre in dirs:
                continue
            elif any(nombre.endswith(a) and nombre[:-len(a)] in sqlites for a in ANEXOS):
                continue  # el backup de la base ya incluye el WAL
            elif nombre in sqlites:
                # closing(): el with de sqlite3 no cierra; una copia WAL abierta deja -wal/-shm sueltos.
                with closing(sqlite3.connect(src.as_uri() + '?mode=ro', uri=True, timeout=10)) as o, \
                        closing(sqlite3.connect(dst)) as c:
                    o.backup(c, pages=256, sleep=0.05)
                    c.execute('PRAGMA journal_mode=DELETE')
                    if c.execute('PRAGMA integrity_check').fetchall() != [('ok',)]:
                        raise RuntimeError(f'integridad incorrecta: {src}')
                cuenta['bases'] += 1
            elif src.is_file():
                shutil.copy2(src, dst, follow_symlinks=False)
            else:
                continue  # sockets y fifos
            os.chown(dst, st.st_uid, st.st_gid)
            os.chmod(dst, st.st_mode & 0o7777)
            cuenta['ficheros'] += 1


def age(args, entrada, lineas):
    # age exige TTY: script(1) aporta el pty y la passphrase viaja por pipe (como los otros backups).
    r = subprocess.run(['script', '-qec', ' '.join(f"'{a}'" for a in ['age', *args, entrada]), '/dev/null'],
                       input=lineas, text=True, capture_output=True)
    if r.returncode != 0:
        raise RuntimeError('age falló')


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument('--destino', required=True, type=Path)
    ap.add_argument('--conservar', type=int, default=3)
    a = ap.parse_args()
    pw = PASS_FILE.read_text().strip()
    if not pw:
        raise SystemExit('passphrase vacía')
    dest = a.destino.resolve(strict=True)
    st = os.stat(dest)  # la copia final es del dueño del destino (usuario), legible por KopiaUI
    uid, gid = st.st_uid, st.st_gid
    os.umask(0o077)
    sello = datetime.datetime.now().strftime('%Y%m%d-%H%M%S')
    with tempfile.TemporaryDirectory(prefix='sip-kopia-', dir='/var/tmp') as tmp:
        tmp = Path(tmp)
        raiz = tmp / 'sip-estado'
        raiz.mkdir()
        cuenta = {'bases': 0, 'ficheros': 0}
        for nombre, ruta in FUENTES.items():
            (raiz / nombre).mkdir()
            copiar_arbol(Path(ruta), raiz / nombre, cuenta)
        ultimas = sorted(LITELLM.glob('litellm-db-*.sql.gz.age'))
        if not ultimas:
            raise RuntimeError('sin copia de LiteLLM')
        (raiz / 'litellm').mkdir()
        shutil.copy2(ultimas[-1], raiz / 'litellm' / ultimas[-1].name)
        extra = 1  # ficheros añadidos fuera de `cuenta` (LiteLLM y, desde el 06-11, sip-flujos)
        if FLUJOS.is_dir():  # desde el 06-11; si existe el directorio, la copia es obligatoria
            ultimas = sorted(FLUJOS.glob('flujos-db-*.tar.gz.age'))
            if not ultimas:
                raise RuntimeError('sin copia de sip-flujos')
            (raiz / 'flujos').mkdir()
            shutil.copy2(ultimas[-1], raiz / 'flujos' / ultimas[-1].name)
            extra += 1
        claro = tmp / 'e.tar.gz'
        with tarfile.open(claro, 'w:gz', compresslevel=6) as t:
            t.add(raiz, arcname='sip-estado')
        shutil.rmtree(raiz)
        final = dest / f'sip-estado-{sello}.tar.gz.age'
        parcial = dest / f'.{final.name}.parcial'
        try:
            age(['-p', '-o', str(parcial)], str(claro), f'{pw}\n{pw}\n')
            # Verificación: descifrar y recorrer el tar entero; contar las bases.
            age(['-d', '-o', str(tmp / 'v.tar.gz')], str(parcial), f'{pw}\n')
            with tarfile.open(tmp / 'v.tar.gz', 'r:gz') as t:
                n = sum(1 for m in t if m.isfile())
            if n != cuenta['ficheros'] + extra:
                raise RuntimeError(f'verificación: {n} ficheros en el tar, {cuenta["ficheros"] + extra} esperados')
            os.chown(parcial, uid, gid)
            os.chmod(parcial, 0o600)
            os.rename(parcial, final)
        finally:
            parcial.unlink(missing_ok=True)
    for viejo in sorted(dest.glob('sip-estado-*.tar.gz.age'))[:-a.conservar]:
        viejo.unlink()
    print(f'OK: {final.name} {final.stat().st_size} bytes; {cuenta["ficheros"]} ficheros, '
          f'{cuenta["bases"]} bases SQLite con integrity_check=ok; verificado descifrando')


if __name__ == '__main__':
    main()
