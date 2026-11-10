#!/usr/bin/env python3
"""sip-actividad.py — qué está haciendo HALO y si se puede apagar (05-11). Root, por unidades oneshot.

  sip-actividad.py muestra            # toma una muestra y escribe /run/sip-energia/estado.json
  sip-actividad.py apagar-auto        # apaga solo si lleva INACTIVO_MIN sin nada que lo impida
  sip-actividad.py apagar-usuario     # apaga si lo que impide el apagado es lo mismo que vio el usuario
                                      # (huella en /run/sip-energia-pet/huella, la deja `orden`)

Decisiones del usuario (05-11): apagado completo, no suspensión. Impiden el apagado automático: teclado o ratón
en uso, audio o vídeo sonando, un agente (Claude Code, Codex, Copilot... en VS Code o en terminal) trabajando,
un modelo/Whisper/ComfyUI cargado, VS Code u otros programas del usuario usando CPU, sesiones SSH o el worker
de CODING. Un navegador abierto sin más no lo impide (sale como información).

Privacidad: solo nombres de programa y tiempos. Nunca títulos de ventana, rutas, nombres de proyecto ni
contenido (de los ficheros de sesión de los agentes solo se mira la fecha de modificación).
"""
import hashlib
import json
import os
import pwd
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

RUN = Path("/run/sip-energia")
PET = Path("/run/sip-energia-pet/huella")
ESTADO = RUN / "estado.json"
MEMORIA = RUN / "memoria.json"       # muestra anterior (CPU acumulada) e «inactivo desde»
RESULTADO = RUN / "apagar.json"
LLAMA = "http://${HALO_TAILNET_IP}:11434/running"
INACTIVO_MIN = int(os.environ.get("SIP_INACTIVO_MIN", "60"))
HUECO_MAX_S = 15 * 60                # sin muestras durante más de esto, el tiempo no visto no cuenta
TECLADO_MIN = 10                     # teclado o ratón en los últimos N min = alguien delante
AGENTE_MIN = 15                      # sesión de agente escrita en los últimos N min = trabajando
CPU_USUARIO = 0.10                   # núcleos medios (10 % de uno) de los programas del usuario
CPU_WHISPER = 0.20
APAGAR_EN_S = 20                     # margen para que la respuesta llegue a Neo antes del apagado

AGENTES = {"claude": "Claude Code", "codex": "Codex", "copilot-runtime": "Copilot", "copilot": "Copilot",
           "gemini": "Gemini CLI", "aider": "Aider", "opencode": "OpenCode", "cursor-agent": "Cursor",
           "goose": "Goose", "cline": "Cline", "qwen": "Qwen Code", "crush": "Crush", "amp": "Amp"}
SESIONES_AGENTE = {"Claude Code": ".claude/projects", "Codex": ".codex/sessions", "Gemini CLI": ".gemini/tmp",
                   "Qwen Code": ".qwen/tmp", "OpenCode": ".local/share/opencode", "Copilot": ".copilot/session-state"}
NAVEGADORES = {"firefox", "firefox-bin", "chrome", "chromium", "chromium-browse", "brave", "brave-browser",
               "vivaldi-bin", "opera", "msedge", "epiphany", "librewolf",
               # procesos internos de Firefox/Chromium
               "Isolated Web Co", "Web Content", "WebExtensions", "Socket Process", "RDD Process", "Utility Process",
               "Privileged Cont", "GPU Process", "Isolated Servic", "Web Content Pro", "Forked Web Cont"}
# Escritorio: dibuja lo que hagan los demás (una pestaña animada); su CPU no indica trabajo del usuario.
ESCRITORIO = ("gnome-", "gsd-", "Xwayland", "pipewire", "wireplumber", "mutter", "ibus", "tracker-", "evolution",
              "dbus-", "xdg-", "gvfs", "at-spi", "systemd", "snapd", "goa-", "dconf", "nautilus", "ding", "gjs")
PROGRAMAS = {"firefox-bin": "Firefox", "firefox": "Firefox", "chrome": "Chrome", "chromium": "Chromium",
             "brave": "Brave", "code": "VS Code", "thunderbird": "Thunderbird", "soffice.bin": "LibreOffice",
             "gimp": "GIMP", "inkscape": "Inkscape", "blender": "Blender", "obs": "OBS", "steam": "Steam",
             "kdenlive": "Kdenlive", "darktable": "darktable", "vlc": "VLC", "mpv": "mpv", "totem": "Vídeos",
             "spotify": "Spotify", "discord": "Discord", "telegram-deskto": "Telegram", "evince": "Visor de PDF"}
TICKS = os.sysconf("SC_CLK_TCK")


def procesos():
    """pid -> (ppid, uid, comm, cpu_s)."""
    out = {}
    for d in os.listdir("/proc"):
        if not d.isdigit():
            continue
        try:
            stat = Path(f"/proc/{d}/stat").read_text()
            uid = os.stat(f"/proc/{d}").st_uid
        except OSError:
            continue
        comm = stat[stat.index("(") + 1:stat.rindex(")")]
        campos = stat[stat.rindex(")") + 2:].split()
        out[int(d)] = (int(campos[1]), uid, comm, (int(campos[11]) + int(campos[12])) / TICKS)
    return out


def descendientes(ps, raices):
    hijos = {}
    for pid, (ppid, *_r) in ps.items():
        hijos.setdefault(ppid, []).append(pid)
    vistos, pila = set(), list(raices)
    while pila:
        p = pila.pop()
        if p in vistos:
            continue
        vistos.add(p)
        pila.extend(hijos.get(p, []))
    return vistos


def sesiones():
    """[(id, usuario, uid, tipo, remota, servicio)] de logind."""
    r = subprocess.run(["loginctl", "list-sessions", "--no-legend"], capture_output=True, text=True)
    out = []
    for linea in r.stdout.splitlines():
        sid = linea.split()[0]
        p = subprocess.run(["loginctl", "show-session", sid, "-p", "Name", "-p", "User", "-p", "Type",
                            "-p", "Remote", "-p", "Service", "-p", "State"], capture_output=True, text=True)
        v = dict(l.split("=", 1) for l in p.stdout.splitlines() if "=" in l)
        if v.get("State") == "closing":
            continue
        out.append((sid, v.get("Name"), int(v.get("User") or -1), v.get("Type"), v.get("Remote") == "yes",
                    v.get("Service")))
    return out


def como_usuario(uid, args):
    """Ejecuta args con la identidad y el bus de sesión del usuario (gdbus, pw-dump)."""
    u = pwd.getpwuid(uid)
    env = {"PATH": "/usr/bin:/bin", "HOME": u.pw_dir, "XDG_RUNTIME_DIR": f"/run/user/{uid}",
           "DBUS_SESSION_BUS_ADDRESS": f"unix:path=/run/user/{uid}/bus"}
    try:
        return subprocess.run(args, capture_output=True, text=True, timeout=10, env=env, user=uid,
                              group=u.pw_gid, extra_groups=[], cwd="/")
    except (OSError, subprocess.TimeoutExpired):
        return None


def teclado_min(uid):
    r = como_usuario(uid, ["gdbus", "call", "--session", "--dest", "org.gnome.Mutter.IdleMonitor",
                           "--object-path", "/org/gnome/Mutter/IdleMonitor/Core",
                           "--method", "org.gnome.Mutter.IdleMonitor.GetIdletime"])
    try:
        return int(r.stdout.strip().strip("(),").split()[-1]) / 60000
    except (AttributeError, ValueError, IndexError):
        return None


def audio_sonando(uid):
    """Flujos de audio en marcha de programas que NO son navegadores. Firefox deja flujos «running» en silencio
    (pestañas en pausa, webs con audio) y bloqueaba el apagado toda la tarde (06-11). Medir el nivel real del
    monitor de salida no funcionó (pw-record daba ceros también con sonido: 2 intentos, regla 10). Decisión:
    el navegador no cuenta (criterio del usuario); VLC, mpv, Spotify, juegos... sí."""
    r = como_usuario(uid, ["pw-dump"])
    try:
        nodos = json.loads(r.stdout)
    except (AttributeError, ValueError):
        return False
    for n in nodos:
        info = n.get("info") or {}
        props = info.get("props") or {}
        if n.get("type") == "PipeWire:Interface:Node" and props.get("media.class") == "Stream/Output/Audio" \
                and info.get("state") == "running" \
                and str(props.get("application.process.binary") or "") not in NAVEGADORES:
            return True
    return False


def sesion_agente_reciente(home, rel, minutos):
    raiz = Path(home) / rel
    if not raiz.is_dir():
        return False
    limite = time.time() - minutos * 60
    for dirpath, dirs, files in os.walk(raiz):
        for f in files:
            try:
                if os.stat(os.path.join(dirpath, f), follow_symlinks=False).st_mtime > limite:
                    return True
            except OSError:
                pass
    return False


def modelos_cargados():
    try:
        with urllib.request.urlopen(LLAMA, timeout=5) as r:
            return [m["model"] for m in json.load(r).get("running", [])]
    except Exception:
        return []


def muestra():
    ahora = time.time()
    try:
        mem = json.loads(MEMORIA.read_text())
    except (OSError, ValueError):
        mem = {}
    ps = procesos()
    cpu_prev = {int(k): v for k, v in mem.get("cpu", {}).items()}
    hueco = ahora - mem.get("ts", 0)
    bloqueos, info = {}, set()

    ses = sesiones()
    graficas = [s for s in ses if s[3] in ("wayland", "x11") and s[2] >= 1000]
    for _sid, nombre, uid, *_r in graficas:
        m = teclado_min(uid)
        if m is not None:
            info.add(f"último uso de teclado o ratón hace {int(m)} min")
            if m < TECLADO_MIN:
                bloqueos["teclado"] = f"teclado o ratón en uso (hace {int(m)} min)"
        if audio_sonando(uid):
            bloqueos["audio"] = "se está reproduciendo audio o vídeo"
    remotas = sorted({s[1] for s in ses if s[4] and s[1] != "sip-energia"})
    if remotas:
        bloqueos["ssh"] = "sesión remota abierta (" + ", ".join(remotas) + ")"
    if any(uid == _uid("hermes-worker") for (_p, uid, _c, _cpu) in ps.values()):
        bloqueos["worker"] = "CODING está trabajando en HALO (worker)"

    cargados = modelos_cargados()
    if cargados:
        bloqueos["gpu"] = "en la GPU/memoria: " + ", ".join(cargados)

    # Agentes: proceso vivo + (sesión escrita hace poco o comandos hijos en marcha o CPU).
    usuarios = {uid for (_p, uid, _c, _cpu) in ps.values() if uid >= 1000 and uid != 65534}
    agentes_vivos = {}
    for pid, (_pp, uid, comm, _cpu) in ps.items():
        if comm in AGENTES and uid in usuarios:
            agentes_vivos.setdefault(AGENTES[comm], []).append(pid)
    for nombre, pids in agentes_vivos.items():
        home = pwd.getpwuid(ps[pids[0]][1]).pw_dir
        rel = SESIONES_AGENTE.get(nombre)
        arbol = descendientes(ps, pids) - set(pids)
        hijos_cmd = [p for p in arbol if ps[p][2] in ("bash", "sh", "zsh", "python3", "python", "make", "cargo",
                                                      "npm", "node", "go", "pytest", "ssh", "git", "docker",
                                                      "cmake", "gcc", "cc1", "rustc", "uv", "pip")
                     and ps[p][3] - cpu_prev.get(p, ps[p][3]) > 0]
        cpu = sum(ps[p][3] - cpu_prev.get(p, ps[p][3]) for p in descendientes(ps, pids))
        if (rel and sesion_agente_reciente(home, rel, AGENTE_MIN)) or hijos_cmd \
                or (hueco < HUECO_MAX_S and cpu / max(hueco, 1) > CPU_USUARIO):
            bloqueos["agente-" + nombre] = f"{nombre} trabajando"
        else:
            info.add(f"{nombre} abierto, sin actividad")

    # Programas del usuario con CPU (VS Code, compilaciones, renders...). Los navegadores no cuentan.
    if hueco < HUECO_MAX_S:
        por_prog = {}
        for pid, (_pp, uid, comm, cpu) in ps.items():
            if uid in usuarios and comm not in NAVEGADORES and not comm.startswith(ESCRITORIO) and pid in cpu_prev:
                d = cpu - cpu_prev[pid]
                if d > 0:
                    por_prog[comm] = por_prog.get(comm, 0) + d
        total = sum(por_prog.values()) / max(hueco, 1)
        if total > CPU_USUARIO:
            top = sorted(por_prog, key=por_prog.get, reverse=True)[:3]
            bloqueos["cpu"] = "programas del usuario usando CPU (" + ", ".join(PROGRAMAS.get(c, c) for c in top) + ")"
        w = [p for p, (_pp, uid, _c, _cpu) in ps.items() if uid == _uid("sip-whisper")]
        dw = sum(ps[p][3] - cpu_prev.get(p, ps[p][3]) for p in w)
        if dw / max(hueco, 1) > CPU_WHISPER:
            bloqueos["whisper"] = "Whisper (CPU) transcribiendo"

    for (_pp, uid, comm, _cpu) in ps.values():
        if uid in usuarios and comm in PROGRAMAS:
            info.add(PROGRAMAS[comm] + " abierto")

    # Inactividad continua y observada.
    desde = mem.get("inactivo_desde")
    if bloqueos or hueco > HUECO_MAX_S or desde is None:
        desde = ahora
    estado = {
        "ts": int(ahora), "bloqueos": [bloqueos[k] for k in sorted(bloqueos)],
        "claves": sorted(bloqueos), "info": sorted(info),
        "inactivo_min": int((ahora - desde) / 60), "umbral_min": INACTIVO_MIN,
        "huella": hashlib.sha256("|".join(sorted(bloqueos)).encode()).hexdigest()[:16],
    }
    RUN.mkdir(mode=0o755, exist_ok=True)
    _escribir(MEMORIA, {"ts": ahora, "inactivo_desde": desde, "cpu": {str(p): v[3] for p, v in ps.items()}}, 0o600)
    _escribir(ESTADO, estado, 0o644)
    return estado


def _uid(nombre):
    try:
        return pwd.getpwnam(nombre).pw_uid
    except KeyError:
        return -2


def _escribir(ruta, datos, modo):
    tmp = ruta.with_suffix(".tmp")
    tmp.write_text(json.dumps(datos, ensure_ascii=False))
    tmp.chmod(modo)
    tmp.replace(ruta)


def apagar(motivo, estado):
    subprocess.run(["systemd-run", "--quiet", f"--on-active={APAGAR_EN_S}", "--unit=sip-apagado-programado",
                    "--description=SIP apagado de HALO (" + motivo + ")", "/bin/systemctl", "poweroff"], check=True)
    print(f"apagado programado en {APAGAR_EN_S} s ({motivo})", flush=True)
    return {"ok": True, "apagado_en_s": APAGAR_EN_S, "motivo": motivo, "info": estado["info"]}


def main():
    modo = sys.argv[1] if len(sys.argv) > 1 else "muestra"
    estado = muestra()
    if modo == "muestra":
        return 0
    if modo == "apagar-auto":
        if estado["bloqueos"] or estado["inactivo_min"] < INACTIVO_MIN:
            res = {"ok": False, "error": "no procede", "estado": estado}
        else:
            res = apagar("inactividad", estado)
    elif modo == "apagar-usuario":
        try:
            huella = PET.read_text().strip()
            PET.unlink()
        except OSError:
            huella = ""
        if huella != estado["huella"]:
            res = {"ok": False, "error": "lo que está haciendo HALO ha cambiado desde que se pidió; vuelve a proponer",
                   "estado": estado}
        else:
            res = apagar("petición del usuario", estado)
    else:
        return 2
    _escribir(RESULTADO, res, 0o644)
    return 0


if __name__ == "__main__":
    sys.exit(main())
