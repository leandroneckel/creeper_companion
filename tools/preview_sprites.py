"""Gera uma folha PNG com as poses do creeper e os ícones (para conferir a arte)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from PySide6.QtCore import QRect, Qt
from PySide6.QtGui import QColor, QFont, QImage, QPainter
from PySide6.QtWidgets import QApplication

from creeper.art import sprite
from creeper.art.sprite import Pose

POSES = [
    ("normal", Pose()),
    ("glint", Pose(eyes="glint")),
    ("feliz", Pose(eyes="happy", blush=True)),
    ("sorriso", Pose(eyes="glint", mouth="smile")),
    ("triste", Pose(eyes="sad", tear=True)),
    ("bravo", Pose(eyes="angry")),
    ("susto", Pose(eyes="wide", mouth="o")),
    ("dormindo", Pose(eyes="closed", sit=5)),
    ("sono", Pose(eyes="half")),
    ("comendo", Pose(eyes="happy", mouth="open")),
    ("mastiga", Pose(eyes="happy", mouth="chew")),
    ("enjoado", Pose(eyes="squint", mouth="wavy", tint="sick")),
    ("tonto", Pose(eyes="x", mouth="o")),
    ("andando", Pose(lift_l=2, bob=1, look_x=1)),
    ("dourado", Pose(eyes="glint", tint="gold")),
    ("chamusc.", Pose(eyes="half", singed=True)),
    ("chiando", Pose(eyes="angry", mouth="hiss", flash=0.5)),
]


def main(out: str) -> None:
    app = QApplication.instance() or QApplication(sys.argv)
    scale = 4
    cell_w, cell_h = 90, sprite.H * scale + 30
    cols = 6
    rows = (len(POSES) + cols - 1) // cols
    sheet = QImage(cols * cell_w, rows * cell_h + 140, QImage.Format_ARGB32)
    sheet.fill(QColor("#3a6ea5"))
    p = QPainter(sheet)
    p.setFont(QFont("Segoe UI", 9))
    for i, (name, pose) in enumerate(POSES):
        x = (i % cols) * cell_w
        y = (i // cols) * cell_h
        img = sprite.render(pose)
        p.drawImage(QRect(x + (cell_w - sprite.W * scale) // 2, y + 5, sprite.W * scale, sprite.H * scale), img)
        p.setPen(Qt.white)
        p.drawText(QRect(x, y + sprite.H * scale + 8, cell_w, 20), Qt.AlignCenter, name)
    try:
        from creeper.art import icons
        y0 = rows * cell_h + 10
        for i, name in enumerate(icons.names()):
            img = icons.image(name)
            x = 10 + (i % 16) * 40
            y = y0 + (i // 16) * 40
            p.drawImage(QRect(x, y, 36, 36), img)
    except ImportError:
        pass
    p.end()
    sheet.save(out)
    print("salvo em", out)


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "preview.png")
