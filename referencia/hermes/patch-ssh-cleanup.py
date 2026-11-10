"""Parche acotado del cierre SSH; se aplica a una imagen candidata, no al servicio."""

import ast
import sys
from pathlib import Path


def method(source, class_name, method_name):
    tree = ast.parse(source)
    classes = [node for node in tree.body if isinstance(node, ast.ClassDef)
               and node.name == class_name]
    if len(classes) != 1:
        raise ValueError("Clase inesperada: " + class_name)
    matches = [node for node in classes[0].body if isinstance(node, ast.FunctionDef)
               and node.name == method_name]
    if len(matches) != 1 or matches[0].decorator_list:
        raise ValueError("Método inesperado: " + method_name)
    return matches[0]


def patch_sync(source):
    node = method(source, "FileSyncManager", "_sync_back_transaction")
    tail = node.body[-1]
    expected = 'logger.warning("sync_back: all %d attempts failed: %s", _SYNC_BACK_MAX_RETRIES, last_exc)'
    if ast.dump(tail) != ast.dump(ast.parse(expected).body[0]):
        raise ValueError("Final de sync_back distinto del inspeccionado")
    lines = source.splitlines(keepends=True)
    lines.insert(node.end_lineno, '        if getattr(self, "_sip_raise_sync_back_failure", False):\n            raise last_exc\n')
    result = "".join(lines)
    compile(result, "file_sync.py", "exec")
    return result


NATIVE_CLEANUP = '''    def cleanup(self):
        if self._sync_manager:
            logger.info("SSH: syncing files from sandbox...")
            self._sync_manager.sync_back()
        for socket in self._control_sockets():
            if not socket.exists():
                continue
            with contextlib.suppress(OSError, subprocess.SubprocessError):
                cmd = ["ssh", "-o", f"ControlPath={socket}", "-O", "exit", f"{self.user}@{self.host}"]
                subprocess.run(cmd, capture_output=True, timeout=5, stdin=subprocess.DEVNULL)
            with contextlib.suppress(OSError):
                socket.unlink()
'''


CLEANUP = '''    def cleanup(self):
        # El destructor también llama a este método. Serializar y cerrar una vez.
        lock = getattr(self, "_sip_cleanup_lock", None)
        if lock is None:
            return  # Constructor fallido antes de iniciar conexión.
        with lock:
            if self._sip_cleanup_complete:
                return
            try:
                manager = getattr(self, "_sync_manager", None)
                if manager is not None:
                    logger.info("SSH: syncing files from sandbox...")
                    manager.sync_back()
            finally:
                # También cerrar transportes tras fallo; conservar manager para reintentar.
                for socket in self._control_sockets():
                    if not socket.exists():
                        continue
                    with contextlib.suppress(OSError, subprocess.SubprocessError):
                        cmd = ["ssh", "-o", f"ControlPath={socket}", "-O", "exit", f"{self.user}@{self.host}"]
                        subprocess.run(cmd, capture_output=True, timeout=5, stdin=subprocess.DEVNULL)
                    with contextlib.suppress(OSError):
                        socket.unlink()
            self._sip_cleanup_complete = True
            self._sync_manager = None
'''


def patch_ssh(source):
    node = method(source, "SSHEnvironment", "cleanup")
    expected = ast.parse("class SSHEnvironment:\n" + NATIVE_CLEANUP).body[0].body[0]
    if ast.dump(node) != ast.dump(expected) or "_sip_cleanup" in source:
        raise ValueError("cleanup distinto del inspeccionado o ya parcheado")
    # Guardas verificadas antes de modificar archivos; mantener constructor nativo.
    constructor = method(source, "SSHEnvironment", "_" * 2 + "init" + "_" * 2)
    assignment = "        self.host, self.user, self.port, self.key_path = host, user, port, key_path\n"
    constructor_text = ast.get_source_segment(source, constructor)
    if assignment.strip() not in constructor_text or source.count(assignment) != 1:
        raise ValueError("Constructor SSH distinto del inspeccionado")
    if source.count("import tempfile\n") != 1:
        raise ValueError("Imports SSH inesperados")
    sync_call = "        self._sync_manager.sync(force=True)\n"
    if source.count(sync_call) != 1:
        raise ValueError("Inicialización del gestor SSH inesperada")
    lines = source.splitlines(keepends=True)
    lines[node.lineno - 1:node.end_lineno] = [CLEANUP]
    result = "".join(lines).replace("import tempfile\n", "import tempfile\nimport threading\n", 1)
    result = result.replace(assignment, assignment +
                            "        self._sip_cleanup_lock = threading.Lock()\n"
                            "        self._sip_cleanup_complete = False\n", 1)
    # FileSyncManager es compartido: propagar fallos solo para el backend SSH.
    result = result.replace(sync_call, '        self._sync_manager._sip_raise_sync_back_failure = True\n' + sync_call, 1)
    compile(result, "ssh.py", "exec")
    return result


def apply(root):
    paths = [root / "tools/environments/file_sync.py", root / "tools/environments/ssh.py"]
    originals = [path.read_text() for path in paths]
    candidates = [patch_sync(originals[0]), patch_ssh(originals[1])]
    # Validar ambos antes de escribir cualquiera; conservar fuentes originales en la imagen.
    backup = Path("/opt/sip-ssh-cleanup/originals")
    backup.mkdir(parents=True, exist_ok=True)
    for path, original, candidate in zip(paths, originals, candidates):
        (backup / path.name).write_text(original)
        path.write_text(candidate)
        print("Parche aplicado:", path.name)


if __name__ == "__main__":
    apply(Path(sys.argv[1]))
