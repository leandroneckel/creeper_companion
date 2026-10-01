"""Menus (clique direito, botões da barra e bandeja), com cara de tooltip do Minecraft."""
from PySide6.QtGui import QAction, QActionGroup, QIcon
from PySide6.QtWidgets import QMenu, QProxyStyle, QStyle

from ..art import icons
from ..needs import EFFECT_LABELS, LABELS

STYLE = """
QMenu {
    background-color: #160A1C;
    color: #F2F2F2;
    border: 2px solid #4B2A86;
    padding: 4px;
    font-weight: 600;
}
QMenu::item { padding: 5px 24px 5px 8px; border: 1px solid transparent; }
QMenu::item:selected { background-color: #4B2A86; }
QMenu::item:disabled { color: #8C7E96; }
QMenu::separator { height: 2px; background: #4B2A86; margin: 4px 6px; }
QMenu::indicator { width: 14px; height: 14px; }
QToolTip {
    background-color: #160A1C;
    color: #F2F2F2;
    border: 2px solid #4B2A86;
    padding: 3px;
}
"""

class PixelIconStyle(QProxyStyle):
    """Ícones de menu com 24px (2x o pixel art de 12px), sem borrar."""

    def pixelMetric(self, metric, option=None, widget=None):
        if metric == QStyle.PM_SmallIconSize:
            return 24
        return super().pixelMetric(metric, option, widget)


def install_style(qapp) -> None:
    qapp.setStyle(PixelIconStyle(qapp.style()))
    qapp.setStyleSheet(STYLE)


CATEGORY_TITLES ={"comidas": "Comer", "bebidas": "Beber", "atividades": "Atividades"}
CATEGORY_ICONS = {"comidas": "comer", "bebidas": "beber", "atividades": "atividades"}

SIZES = [(2, "Pequeno"), (3, "Médio"), (4, "Grande")]
CHATTINESS = [("pouco", "Fala pouco"), ("normal", "Normal"), ("muito", "Tagarela")]
SPEEDS = [(0.5, "Lenta (mais tranquilo)"), (1.0, "Normal"), (2.0, "Rápida (mais trabalho)")]


def effects_text(item: dict) -> str:
    parts = [f"{LABELS.get(k, k)} {int(v):+d}" for k, v in item.get("efeitos", {}).items()]
    if item.get("status"):
        parts.append(f"fica {EFFECT_LABELS.get(item['status'], item['status'])}")
    if item.get("cura"):
        parts.append("cura enjoo e café")
    return " · ".join(parts)


def _icon(name: str) -> QIcon:
    return QIcon(icons.pixmap(name, 2))


def fill_category(app, menu: QMenu, category: str) -> None:
    pet = app.pet
    enabled = pet.can_interact() and not pet.busy()
    for item in app.items.by_category[category]:
        label = item["nome"]
        tip = effects_text(item)
        action = QAction(_icon(item["id"]), label, menu)
        action.setToolTip(tip)
        action.setStatusTip(tip)
        action.setEnabled(enabled)
        if category == "atividades":
            action.triggered.connect(lambda _=False, i=item["id"]: app.pet.do_activity(i))
        else:
            action.triggered.connect(lambda _=False, i=item["id"]: app.pet.feed(i))
        menu.addAction(action)
    menu.setToolTipsVisible(True)


def category_menu(app, category: str) -> QMenu:
    menu = QMenu()
    fill_category(app, menu, category)
    return menu


def fill_main(app, menu: QMenu, tray: bool = False) -> None:
    pet = app.pet
    n = pet.needs
    menu.setToolTipsVisible(True)

    header = menu.addAction(f"{app.settings.name} · {n.mood()}")
    header.setEnabled(False)
    menu.addSeparator()

    for category in ("comidas", "bebidas", "atividades"):
        sub = menu.addMenu(_icon(CATEGORY_ICONS[category]), CATEGORY_TITLES[category])
        fill_category(app, sub, category)

    if pet.state == "sleep":
        act = menu.addAction(_icon("acordar"), "Acordar")
        act.triggered.connect(lambda: app.pet.wake(forced=True))
    else:
        act = menu.addAction(_icon("dormir"), "Dormir")
        act.setEnabled(pet.can_interact() and not pet.busy())
        act.triggered.connect(app.pet.request_sleep)
    act = menu.addAction(_icon("carinho"), "Fazer carinho")
    act.setEnabled(pet.can_interact())
    act.triggered.connect(app.pet_hug)

    menu.addSeparator()
    if app.in_tray:
        act = menu.addAction("Mostrar na tela")
        act.triggered.connect(app.show_from_tray)
    else:
        act = menu.addAction(_icon("bandeja"), "Recolher para a bandeja")
        act.triggered.connect(app.hide_to_tray)

    _fill_settings(app, menu.addMenu("Configurações"))
    menu.addSeparator()
    act = menu.addAction("Sair")
    act.triggered.connect(app.quit)


def _radio(menu: QMenu, options, current, on_pick) -> None:
    group = QActionGroup(menu)
    group.setExclusive(True)
    for value, label in options:
        act = menu.addAction(label)
        act.setCheckable(True)
        act.setChecked(value == current)
        act.triggered.connect(lambda _=False, v=value: on_pick(v))
        group.addAction(act)


def _check(menu: QMenu, label: str, checked: bool, on_toggle) -> None:
    act = menu.addAction(label)
    act.setCheckable(True)
    act.setChecked(checked)
    act.toggled.connect(on_toggle)


def _fill_settings(app, menu: QMenu) -> None:
    s = app.settings
    _radio(menu.addMenu("Tamanho"), SIZES, s.scale, app.set_scale)
    _radio(menu.addMenu("Falas"), CHATTINESS, s.chattiness, lambda v: app.set_setting("chattiness", v))
    _radio(menu.addMenu("Velocidade das necessidades"), SPEEDS, s.needs_speed,
           lambda v: app.set_setting("needs_speed", v))

    rem = menu.addMenu("Lembretes pra você")
    _check(rem, f"Beber água (a cada {s.water_minutes} min)", s.remind_water,
           lambda v: app.set_setting("remind_water", v))
    _check(rem, f"Fazer pausas (a cada {s.break_minutes} min de uso)", s.remind_break,
           lambda v: app.set_setting("remind_break", v))
    _check(rem, "Ir dormir (depois da meia-noite)", s.remind_sleep,
           lambda v: app.set_setting("remind_sleep", v))

    _check(menu, "Esconder quando algo estiver em tela cheia", s.hide_fullscreen,
           lambda v: app.set_setting("hide_fullscreen", v))
    _check(menu, "Avisos quando estiver na bandeja", s.notifications,
           lambda v: app.set_setting("notifications", v))
    _check(menu, "Iniciar com o sistema", app.autostart_enabled(), app.set_autostart)
    menu.addSeparator()
    act = menu.addAction("Renomear...")
    act.triggered.connect(app.rename)
