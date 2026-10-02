"""Aviso "Conquista feita!" que desliza no canto da tela, no estilo do Minecraft.

Não rouba o foco e deixa o clique passar: é só pra ver.
"""
import time

from PySide6.QtCore import QRect, Qt, QTimer
from PySide6.QtGui import QColor, QFont, QFontMetrics, QGuiApplication, QPainter
from PySide6.QtWidgets import QWidget

from .. import desktop
from ..art import icons

W, H = 260, 52
MARGIN = 14
SHOW_SECONDS = 5.0
SLIDE_SECONDS = 0.3


class Toast(QWidget):
    def __init__(self):
        flags = (Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool | Qt.WindowDoesNotAcceptFocus
                 | Qt.WindowTransparentForInput | desktop.window_flags_extra())
        super().__init__(None, flags)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self.setWindowTitle("Conquista")
        self.setFixedSize(W, H)
        self.font_title = QFont()
        self.font_title.setPixelSize(12)
        self.font_title.setBold(True)
        self.font_name = QFont()
        self.font_name.setPixelSize(12)
        self.font_name.setWeight(QFont.DemiBold)
        self.queue: list[tuple[dict, object]] = []
        self.current: dict | None = None
        self.started = 0.0
        self.area = QRect()
        self.timer = QTimer(self)
        self.timer.setTimerType(Qt.PreciseTimer)
        self.timer.timeout.connect(self._step)

    def show_achievement(self, achievement: dict, screen=None) -> None:
        self.queue.append((achievement, screen))
        if self.current is None:
            self._next()

    def _next(self) -> None:
        if not self.queue:
            self.current = None
            self.timer.stop()
            self.hide()
            return
        self.current, screen = self.queue.pop(0)
        self.area = (screen or QGuiApplication.primaryScreen()).availableGeometry()
        self.started = time.monotonic()
        self._step()
        self.show()
        self.update()
        self.timer.start(16)

    def _step(self) -> None:
        t = time.monotonic() - self.started
        total = SHOW_SECONDS + 2 * SLIDE_SECONDS
        if t >= total:
            self._next()
            return
        k = min(1.0, t / SLIDE_SECONDS, (total - t) / SLIDE_SECONDS)
        k = 1 - (1 - k) ** 2   # desacelera no fim do deslize
        self.timer.setInterval(16 if k < 1 else 100)
        self.move(self.area.right() + 1 - round((W + MARGIN) * k), self.area.top() + MARGIN)

    def showEvent(self, event) -> None:
        super().showEvent(event)
        desktop.setup_window(self)

    def paintEvent(self, event) -> None:
        if not self.current:
            return
        p = QPainter(self)
        black, border, bg = QColor("#000000"), QColor("#5A5A5A"), QColor("#212121")
        # caixa com cantos "em escadinha", como o resto da interface
        p.fillRect(QRect(2, 0, W - 4, H), black)
        p.fillRect(QRect(0, 2, W, H - 4), black)
        p.fillRect(QRect(2, 2, W - 4, H - 4), border)
        p.fillRect(QRect(4, 4, W - 8, H - 8), bg)
        p.drawImage(QRect(14, 14, 24, 24), icons.image(self.current.get("icone", "xp")))
        p.setFont(self.font_title)
        p.setPen(QColor("#FFFF55"))
        p.drawText(QRect(48, 8, W - 58, 18), Qt.AlignLeft | Qt.AlignVCenter, "Conquista feita!")
        p.setFont(self.font_name)
        p.setPen(QColor("#FFFFFF"))
        name = QFontMetrics(self.font_name).elidedText(self.current.get("nome", ""), Qt.ElideRight, W - 58)
        p.drawText(QRect(48, 26, W - 58, 18), Qt.AlignLeft | Qt.AlignVCenter, name)
        p.end()
