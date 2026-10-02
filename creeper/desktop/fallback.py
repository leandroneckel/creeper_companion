"""Outras plataformas: só o básico do Qt."""


def window_flags_extra():
    from PySide6.QtCore import Qt
    return Qt.WindowType(0)


def needs_input_mask() -> bool:
    return False


def setup_window(widget) -> None:
    pass


def keep_on_top(widget) -> None:
    widget.raise_()


def user_idle_seconds():
    return None


def fullscreen_app_active() -> bool:
    return False


def autostart_enabled() -> bool:
    return False


def set_autostart(enabled: bool) -> None:
    pass


def window_rects() -> list[tuple[int, int, int, int]]:
    return []
