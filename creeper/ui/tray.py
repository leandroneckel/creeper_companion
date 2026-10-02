"""Ícone na bandeja do sistema (Windows) / área de indicadores (Linux)."""
from PySide6.QtCore import Qt
from PySide6.QtGui import QIcon, QPixmap
from PySide6.QtWidgets import QMenu, QSystemTrayIcon

from ..art import sprite
from ..art.sprite import Pose
from . import menus


class Tray(QSystemTrayIcon):
    def __init__(self, app):
        super().__init__()
        self.app = app
        self.menu = QMenu()
        self.menu.aboutToShow.connect(self.rebuild)
        self.setContextMenu(self.menu)
        self.activated.connect(self._on_activated)
        self._icon_key = None
        self.rebuild()
        self.refresh()

    def rebuild(self) -> None:
        self.menu.clear()
        menus.fill_main(self.app, self.menu, tray=True)

    def _on_activated(self, reason) -> None:
        if reason in (QSystemTrayIcon.Trigger, QSystemTrayIcon.DoubleClick):
            self.app.toggle_visible()

    def refresh(self) -> None:
        pet = self.app.pet
        n = pet.needs
        if pet.state == "sleep":
            pose = Pose(eyes="closed")
        elif n.mood() in ("irritado", "emburrado"):
            pose = Pose(eyes="angry")
        elif n.mood() in ("chateado", "péssimo"):
            pose = Pose(eyes="sad")
        else:
            pose = Pose(eyes="glint")
        if pose != self._icon_key:
            self._icon_key = pose
            img = sprite.render_head(pose).scaled(64, 64, Qt.IgnoreAspectRatio, Qt.FastTransformation)
            self.setIcon(QIcon(QPixmap.fromImage(img)))
        worst, value = n.worst()
        tip = f"{self.app.settings.name} · nível {self.app.progress.level} · {n.mood()}"
        if value < 40:
            tip += f" ({n.level_word(worst)})"
        self.setToolTip(tip)
