"""Linux (X11 e GNOME/Wayland via XWayland).

O main.py força QT_QPA_PLATFORM=xcb: no GNOME com Wayland o app roda via XWayland,
onde dá pra pedir "todas as áreas de trabalho" e "sempre no topo".
A janela usa X11BypassWindowManagerHint: o gerenciador de janelas não a controla,
então ela fica visível em todas as áreas de trabalho e acima das outras janelas.
"""
import shutil
import subprocess
from pathlib import Path

from .common import launch_command

AUTOSTART = Path.home() / ".config" / "autostart" / "creeper-companion.desktop"


def _is_x11() -> bool:
    from PySide6.QtGui import QGuiApplication
    return QGuiApplication.platformName() == "xcb"


def window_flags_extra():
    from PySide6.QtCore import Qt
    return Qt.X11BypassWindowManagerHint if _is_x11() else Qt.WindowType(0)


def needs_input_mask() -> bool:
    return True  # no X11 o clique só atravessa a janela com máscara de entrada


def _run(*args: str, timeout: float = 1.0) -> str | None:
    if not shutil.which(args[0]):
        return None
    try:
        out = subprocess.run(args, capture_output=True, text=True, timeout=timeout)
        return out.stdout if out.returncode == 0 else None
    except (OSError, subprocess.SubprocessError):
        return None


def setup_window(widget) -> None:
    if not _is_x11():
        return
    wid = hex(int(widget.winId()))
    # Reforço para gerenciadores que ainda tratem a janela: fixa em todas as áreas.
    _run("wmctrl", "-i", "-r", wid, "-b", "add,sticky,above")
    _run("xprop", "-id", wid, "-f", "_NET_WM_DESKTOP", "32c", "-set", "_NET_WM_DESKTOP", "0xFFFFFFFF")


def keep_on_top(widget) -> None:
    widget.raise_()


def user_idle_seconds() -> float | None:
    # GNOME (X11 e Wayland)
    out = _run("gdbus", "call", "--session", "--dest", "org.gnome.Mutter.IdleMonitor",
               "--object-path", "/org/gnome/Mutter/IdleMonitor/Core",
               "--method", "org.gnome.Mutter.IdleMonitor.GetIdletime")
    if out:
        digits = "".join(ch for ch in out.split(",")[0] if ch.isdigit())
        if digits:
            return int(digits) / 1000.0
    out = _run("xprintidle")
    if out and out.strip().isdigit():
        return int(out.strip()) / 1000.0
    return None


def fullscreen_app_active() -> bool:
    if not _is_x11():
        return False
    out = _run("xprop", "-root", "_NET_ACTIVE_WINDOW")
    if not out or "0x" not in out:
        return False
    win = out.strip().split()[-1]
    if win in ("0x0", "0"):
        return False
    state = _run("xprop", "-id", win, "_NET_WM_STATE")
    return bool(state and "_NET_WM_STATE_FULLSCREEN" in state)


def autostart_enabled() -> bool:
    return AUTOSTART.exists()


def set_autostart(enabled: bool) -> None:
    if not enabled:
        AUTOSTART.unlink(missing_ok=True)
        return
    AUTOSTART.parent.mkdir(parents=True, exist_ok=True)
    cmd = " ".join(f'"{part}"' for part in launch_command())
    AUTOSTART.write_text(
        "[Desktop Entry]\n"
        "Type=Application\n"
        "Name=Creeper Companion\n"
        f"Exec={cmd}\n"
        "X-GNOME-Autostart-enabled=true\n",
        encoding="utf-8",
    )


_hidden_cache: dict[str, tuple[float, bool]] = {}


def _minimized(win: str) -> bool:
    """_NET_WM_STATE_HIDDEN, guardado por 10 s pra não chamar o xprop toda hora."""
    import time
    now = time.monotonic()
    cached = _hidden_cache.get(win)
    if cached and now - cached[0] < 10:
        return cached[1]
    state = _run("xprop", "-id", win, "_NET_WM_STATE") or ""
    hidden = "_NET_WM_STATE_HIDDEN" in state
    _hidden_cache[win] = (now, hidden)
    return hidden


def window_rects() -> list[tuple[int, int, int, int]]:
    """Janelas visíveis na área de trabalho atual, da de cima pra de baixo (só X11, via wmctrl).

    No Wayland as janelas nativas não aparecem pro XWayland: aí devolve só as que der (ou nada).
    """
    if not _is_x11() or not shutil.which("wmctrl"):
        return []
    listing = _run("wmctrl", "-lG")
    stacking = _run("xprop", "-root", "_NET_CLIENT_LIST_STACKING")
    current = _run("xprop", "-root", "_NET_CURRENT_DESKTOP")
    if not listing:
        return []
    try:
        desk = current.split("=")[-1].strip() if current else None
        rects = {}
        for line in listing.splitlines():
            parts = line.split(None, 7)
            if len(parts) < 7:
                continue
            win, d, x, y, w, h = parts[0], parts[1], *map(int, parts[2:6])
            if desk is not None and d not in (desk, "-1"):
                continue
            if w >= 80 and h >= 40:
                rects[int(win, 16)] = (win, (x, y, x + w, y + h))
        order = []
        if stacking and "#" in stacking:   # lista de baixo pra cima
            order = [int(v.strip(), 16) for v in stacking.split("#", 1)[1].split(",") if v.strip()]
        ids = [i for i in reversed(order) if i in rects] or list(rects)
        return [rects[i][1] for i in ids[:30] if not _minimized(rects[i][0])]
    except (ValueError, IndexError):
        return []
