"""Windows: janela de ferramenta (aparece em todas as áreas de trabalho virtuais),
sempre no topo sem roubar foco, detecção de tela cheia e de inatividade."""
import ctypes
import os
import subprocess
import winreg
from ctypes import wintypes

from .common import launch_command

user32 = ctypes.WinDLL("user32", use_last_error=True)
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
shell32 = ctypes.WinDLL("shell32", use_last_error=True)

GWL_EXSTYLE = -20
GWL_STYLE = -16
WS_EX_TOOLWINDOW = 0x00000080
WS_EX_APPWINDOW = 0x00040000
WS_EX_NOACTIVATE = 0x08000000
WS_EX_TOPMOST = 0x00000008
WS_CAPTION = 0x00C00000
HWND_TOPMOST = wintypes.HWND(-1)
SWP_NOSIZE = 0x0001
SWP_NOMOVE = 0x0002
SWP_NOACTIVATE = 0x0010
SWP_NOOWNERZORDER = 0x0200
MONITOR_DEFAULTTONEAREST = 2

user32.GetWindowLongPtrW.restype = ctypes.c_ssize_t
user32.GetWindowLongPtrW.argtypes = [wintypes.HWND, ctypes.c_int]
user32.SetWindowLongPtrW.restype = ctypes.c_ssize_t
user32.SetWindowLongPtrW.argtypes = [wintypes.HWND, ctypes.c_int, ctypes.c_ssize_t]
user32.SetWindowPos.argtypes = [wintypes.HWND, wintypes.HWND, ctypes.c_int, ctypes.c_int,
                                ctypes.c_int, ctypes.c_int, wintypes.UINT]
user32.GetForegroundWindow.restype = wintypes.HWND
user32.GetClassNameW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
user32.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
user32.MonitorFromWindow.restype = wintypes.HMONITOR
user32.MonitorFromWindow.argtypes = [wintypes.HWND, wintypes.DWORD]


class MONITORINFO(ctypes.Structure):
    _fields_ = [("cbSize", wintypes.DWORD), ("rcMonitor", wintypes.RECT),
                ("rcWork", wintypes.RECT), ("dwFlags", wintypes.DWORD)]


class LASTINPUTINFO(ctypes.Structure):
    _fields_ = [("cbSize", wintypes.UINT), ("dwTime", wintypes.DWORD)]


user32.GetMonitorInfoW.argtypes = [wintypes.HMONITOR, ctypes.POINTER(MONITORINFO)]

SHELL_CLASSES = {"Progman", "WorkerW", "Shell_TrayWnd", "Shell_SecondaryTrayWnd"}
RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
RUN_VALUE = "CreeperCompanion"


def window_flags_extra():
    from PySide6.QtCore import Qt
    return Qt.WindowType(0)


def needs_input_mask() -> bool:
    return False  # janelas "layered" já deixam o clique passar nos pixels transparentes


def _hwnd(widget) -> int:
    return int(widget.winId())


def setup_window(widget) -> None:
    """Garante WS_EX_TOOLWINDOW (sem botão na barra de tarefas e visível em todas as
    áreas de trabalho virtuais) e WS_EX_NOACTIVATE (não rouba o foco)."""
    hwnd = _hwnd(widget)
    ex = user32.GetWindowLongPtrW(hwnd, GWL_EXSTYLE)
    want = (ex | WS_EX_TOOLWINDOW | WS_EX_NOACTIVATE | WS_EX_TOPMOST) & ~WS_EX_APPWINDOW
    if want != ex:
        user32.SetWindowLongPtrW(hwnd, GWL_EXSTYLE, want)
    keep_on_top(widget)
    _pin_fallback(hwnd)


def _pin_fallback(hwnd: int) -> None:
    """Se por algum motivo o Windows associar a janela a uma área de trabalho,
    tenta fixá-la em todas via pyvda (opcional)."""
    try:
        from pyvda import AppView
        view = AppView(hwnd)
    except Exception:
        return  # janela de ferramenta não pertence a nenhuma área de trabalho: ótimo
    try:
        if not view.is_pinned():
            view.pin()
    except Exception:
        pass


def keep_on_top(widget) -> None:
    user32.SetWindowPos(_hwnd(widget), HWND_TOPMOST, 0, 0, 0, 0,
                        SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE | SWP_NOOWNERZORDER)


def user_idle_seconds() -> float | None:
    info = LASTINPUTINFO()
    info.cbSize = ctypes.sizeof(info)
    if not user32.GetLastInputInfo(ctypes.byref(info)):
        return None
    millis = (kernel32.GetTickCount() - info.dwTime) & 0xFFFFFFFF
    return millis / 1000.0


def fullscreen_app_active() -> bool:
    # Estado oficial de "não perturbe" do Windows (jogos D3D, apresentações, apps em tela cheia)
    state = ctypes.c_int(0)
    try:
        if shell32.SHQueryUserNotificationState(ctypes.byref(state)) == 0 and state.value in (2, 3, 4):
            return True
    except (AttributeError, OSError):
        pass

    hwnd = user32.GetForegroundWindow()
    if not hwnd:
        return False
    buf = ctypes.create_unicode_buffer(256)
    user32.GetClassNameW(hwnd, buf, 256)
    if buf.value in SHELL_CLASSES:
        return False
    pid = wintypes.DWORD()
    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    if pid.value == os.getpid():
        return False
    rect = wintypes.RECT()
    user32.GetWindowRect(hwnd, ctypes.byref(rect))
    info = MONITORINFO()
    info.cbSize = ctypes.sizeof(info)
    if not user32.GetMonitorInfoW(user32.MonitorFromWindow(hwnd, MONITOR_DEFAULTTONEAREST), ctypes.byref(info)):
        return False
    mon = info.rcMonitor
    covers = rect.left <= mon.left and rect.top <= mon.top and rect.right >= mon.right and rect.bottom >= mon.bottom
    if not covers:
        return False
    style = user32.GetWindowLongPtrW(hwnd, GWL_STYLE)
    return (style & WS_CAPTION) != WS_CAPTION


def autostart_enabled() -> bool:
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as key:
            winreg.QueryValueEx(key, RUN_VALUE)
            return True
    except OSError:
        return False


def set_autostart(enabled: bool) -> None:
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE) as key:
        if enabled:
            winreg.SetValueEx(key, RUN_VALUE, 0, winreg.REG_SZ, subprocess.list2cmdline(launch_command()))
        else:
            try:
                winreg.DeleteValue(key, RUN_VALUE)
            except FileNotFoundError:
                pass


# ---- janelas abertas (pra ele subir nelas e se esconder atrás) ----------------
dwmapi = ctypes.WinDLL("dwmapi")
DWMWA_EXTENDED_FRAME_BOUNDS = 9
DWMWA_CLOAKED = 14
WNDENUMPROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
user32.EnumWindows.argtypes = [WNDENUMPROC, wintypes.LPARAM]
user32.IsWindowVisible.argtypes = [wintypes.HWND]
user32.IsIconic.argtypes = [wintypes.HWND]
user32.GetWindowTextLengthW.argtypes = [wintypes.HWND]
dwmapi.DwmGetWindowAttribute.argtypes = [wintypes.HWND, wintypes.DWORD, ctypes.c_void_p, wintypes.DWORD]


def window_rects() -> list[tuple[int, int, int, int]]:
    """Janelas normais visíveis nesta área de trabalho (sem as nossas), da de cima pra de baixo.

    Só posição e tamanho, em pixels físicos: (esquerda, topo, direita, base).
    """
    own = os.getpid()
    found: list[tuple[int, int, int, int]] = []
    name = ctypes.create_unicode_buffer(256)

    def visit(hwnd, _lparam):
        if not user32.IsWindowVisible(hwnd) or user32.IsIconic(hwnd) or not user32.GetWindowTextLengthW(hwnd):
            return True
        if user32.GetWindowLongPtrW(hwnd, GWL_EXSTYLE) & WS_EX_TOOLWINDOW:
            return True
        pid = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        if pid.value == own:
            return True
        user32.GetClassNameW(hwnd, name, 256)
        if name.value in SHELL_CLASSES:
            return True
        cloaked = ctypes.c_int(0)   # "escondida" pelo Windows (outra área de trabalho, app suspenso)
        dwmapi.DwmGetWindowAttribute(hwnd, DWMWA_CLOAKED, ctypes.byref(cloaked), ctypes.sizeof(cloaked))
        if cloaked.value:
            return True
        rect = wintypes.RECT()   # sem a borda invisível de redimensionar
        if dwmapi.DwmGetWindowAttribute(hwnd, DWMWA_EXTENDED_FRAME_BOUNDS, ctypes.byref(rect), ctypes.sizeof(rect)):
            user32.GetWindowRect(hwnd, ctypes.byref(rect))
        if rect.right - rect.left >= 80 and rect.bottom - rect.top >= 40:
            found.append((rect.left, rect.top, rect.right, rect.bottom))
        return True

    user32.EnumWindows(WNDENUMPROC(visit), 0)
    return found
