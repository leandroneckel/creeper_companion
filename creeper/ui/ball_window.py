"""A bolinha na tela: uma janelinha redonda que dá pra agarrar e arremessar."""
import time
from collections import deque

from PySide6.QtCore import QPoint, QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QPainter, QRegion
from PySide6.QtWidgets import QWidget

from .. import desktop
from ..ball import RADIUS

SIZE = int(RADIUS * 2) + 4
# bolinha de borracha em pixel art (9x9)
PIXELS = [
    "..rrrrr..",
    ".rrwwrrr.",
    "rrwwrrrrR",
    "rrwrrrrrR",
    "rrrrrrrrR",
    "rrrrrrrRR",
    "RrrrrrRRR",
    ".RRrrRRR.",
    "..RRRRR..",
]
COLORS = {"r": QColor("#E53935"), "R": QColor("#A61C1C"), "w": QColor("#FFCDD2")}


class BallWindow(QWidget):
    def __init__(self, ball, on_throw):
        flags = (Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool
                 | Qt.WindowDoesNotAcceptFocus | desktop.window_flags_extra())
        super().__init__(None, flags)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self.setWindowTitle("Bolinha")
        self.setFixedSize(SIZE, SIZE)
        self.setCursor(Qt.OpenHandCursor)
        self.ball = ball
        self.on_throw = on_throw
        self.samples: deque = deque(maxlen=6)
        self.grab_offset = QPointF()
        if desktop.needs_input_mask():
            self.setMask(QRegion(0, 0, SIZE, SIZE, QRegion.Ellipse))

    def sync(self, allowed: bool = True) -> None:
        """Acompanha a física: mostra/esconde e move a janelinha. allowed=False: o creeper está
        escondido (bandeja, tela cheia), então a bolinha some junto."""
        b = self.ball
        show = allowed and b.active and b.held != "pet"
        if show != self.isVisible():
            self.setVisible(show)
        if show and b.held != "user":
            pos = QPoint(round(b.x - SIZE / 2), round(b.y - SIZE / 2))
            if pos != self.pos():
                self.move(pos)

    def showEvent(self, event) -> None:
        super().showEvent(event)
        desktop.setup_window(self)

    def paintEvent(self, event) -> None:
        p = QPainter(self)
        cell = (SIZE - 4) / 9
        for y, row in enumerate(PIXELS):
            for x, ch in enumerate(row):
                if ch in COLORS:
                    p.fillRect(QRectF(2 + x * cell, 2 + y * cell, cell + 0.5, cell + 0.5), COLORS[ch])
        p.end()

    # ---- agarrar e arremessar ---------------------------------------------
    def mousePressEvent(self, e) -> None:
        if e.button() != Qt.LeftButton:
            return
        g = e.globalPosition()
        self.ball.held = "user"
        self.grab_offset = QPointF(self.ball.x - g.x(), self.ball.y - g.y())
        self.samples.clear()
        self.samples.append((g.x(), g.y(), time.monotonic()))
        self.setCursor(Qt.ClosedHandCursor)

    def mouseMoveEvent(self, e) -> None:
        if self.ball.held != "user":
            return
        g = e.globalPosition()
        self.ball.x, self.ball.y = g.x() + self.grab_offset.x(), g.y() + self.grab_offset.y()
        self.samples.append((g.x(), g.y(), time.monotonic()))
        self.move(round(self.ball.x - SIZE / 2), round(self.ball.y - SIZE / 2))

    def mouseReleaseEvent(self, e) -> None:
        if self.ball.held != "user":
            return
        self.setCursor(Qt.OpenHandCursor)
        vx = vy = 0.0
        if len(self.samples) >= 2:
            (x0, y0, t0), (x1, y1, t1) = self.samples[0], self.samples[-1]
            if time.monotonic() - t1 < 0.1:   # só conta como arremesso se ainda estava mexendo
                dt = max(1e-3, t1 - t0)
                vx, vy = (x1 - x0) / dt, (y1 - y0) / dt
        self.ball.throw(vx, vy)
        self.on_throw()
