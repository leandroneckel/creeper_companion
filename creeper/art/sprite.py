"""Desenho do creeper em pixel art, gerado por código.

A imagem tem resolução "fina" de 16x40: cada texel do Minecraft vira 2x2,
o que dá espaço para expressões no rosto sem perder a cara de creeper.
Cabeça 8x8 texels, corpo 8x8, pernas 4x4 (versão um pouco mais fofinha).
"""
import random
from dataclasses import dataclass
from functools import lru_cache

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QImage, QPainter

W, H = 16, 40
HEAD_H = 16

_GREENS = [
    ("#1F6B1C", 7), ("#2F8A28", 17), ("#3FA535", 28), ("#55BC48", 26),
    ("#74D166", 15), ("#A0E28F", 6), ("#D2E5CC", 1),
]
FACE = QColor("#141414")
FACE_SOFT = QColor("#262626")
GLINT = QColor("#FFFFFF")
TONGUE = QColor("#7A2A2A")
BLUSH = QColor(244, 143, 177, 210)
TEAR = QColor("#64B5F6")
SEAM = QColor(0, 0, 0, 70)
SEAM_DARK = QColor(0, 0, 0, 120)


def _texture(rng: random.Random, w: int, h: int) -> list[list[QColor]]:
    colors = [QColor(c) for c, _ in _GREENS]
    weights = [wt for _, wt in _GREENS]
    return [[rng.choices(colors, weights)[0] for _ in range(w)] for _ in range(h)]


_rng = random.Random(1337)
HEAD_TEX = _texture(_rng, 8, 8)
BODY_TEX = _texture(_rng, 8, 8)
LEG_TEX = _texture(_rng, 8, 4)
SINGED = [(_rng.randrange(8), _rng.randrange(16)) for _ in range(14)]


@dataclass(frozen=True)
class Pose:
    eyes: str = "open"      # open, glint, wide, closed, half, happy, angry, sad, x, squint
    mouth: str = "classic"  # classic, open, chew, o, wavy, smile, hiss
    look_x: int = 0         # -1..1 (olhar pros lados)
    look_y: int = 0         # -1..1
    blush: bool = False
    tear: bool = False
    bob: int = 0            # desce cabeça e corpo (respiração/agachar)
    lift_l: int = 0         # levanta o pé esquerdo
    lift_r: int = 0
    sit: int = 0            # 0..6, encolhe as pernas
    singed: bool = False
    tint: str | None = None  # "gold" | "sick"
    flash: float = 0.0       # 0..1, piscar branco antes de explodir


def _px(p: QPainter, pts, color: QColor, ox: int, oy: int) -> None:
    for x, y in pts:
        p.fillRect(ox + x, oy + y, 1, 1, color)


def _eye(p: QPainter, x: int, y: int, kind: str, side: int) -> None:
    """Desenha um olho na caixa 4x4 em (x, y). side: -1 esquerdo, +1 direito."""
    full = [(i, j) for j in range(4) for i in range(4)]
    if kind == "closed":
        p.fillRect(x, y + 2, 4, 1, FACE)
    elif kind == "half":
        p.fillRect(x, y + 2, 4, 2, FACE)
    elif kind == "happy":
        _px(p, [(1, 1), (2, 1), (0, 2), (3, 2), (0, 3), (3, 3)], FACE, x, y)
    elif kind == "angry":
        cut = {(2, 0), (3, 0), (3, 1)} if side < 0 else {(0, 0), (1, 0), (0, 1)}
        _px(p, [c for c in full if c not in cut], FACE, x, y)
    elif kind == "sad":
        cut = {(0, 0), (1, 0), (0, 1)} if side < 0 else {(2, 0), (3, 0), (3, 1)}
        _px(p, [c for c in full if c not in cut], FACE, x, y)
    elif kind == "x":
        _px(p, [(0, 0), (3, 0), (1, 1), (2, 1), (1, 2), (2, 2), (0, 3), (3, 3)], FACE, x, y)
    elif kind == "squint":
        if side < 0:
            pts = [(0, 1), (1, 1), (2, 2), (3, 2), (0, 3), (1, 3)]
        else:
            pts = [(2, 1), (3, 1), (0, 2), (1, 2), (2, 3), (3, 3)]
        _px(p, pts, FACE, x, y)
    else:
        p.fillRect(x, y, 4, 4, FACE)
        if kind == "glint":
            p.fillRect(x + 1, y + 1, 1, 1, GLINT)
        elif kind == "wide":
            p.fillRect(x + 1, y + 1, 2, 2, GLINT)


def _mouth(p: QPainter, kind: str, oy: int) -> None:
    if kind == "o":
        p.fillRect(6, oy + 7, 4, 4, FACE)
        return
    p.fillRect(6, oy + 6, 4, 2, FACE)  # "nariz"
    if kind == "classic":
        p.fillRect(4, oy + 8, 8, 4, FACE)
        p.fillRect(4, oy + 12, 2, 2, FACE)
        p.fillRect(10, oy + 12, 2, 2, FACE)
    elif kind in ("open", "hiss"):
        p.fillRect(4, oy + 8, 8, 6, FACE)
        if kind == "open":
            p.fillRect(6, oy + 11, 4, 2, TONGUE)
        else:
            p.fillRect(5, oy + 10, 6, 2, FACE_SOFT)
    elif kind == "chew":
        p.fillRect(4, oy + 8, 8, 3, FACE)
        p.fillRect(4, oy + 11, 2, 1, FACE)
        p.fillRect(10, oy + 11, 2, 1, FACE)
    elif kind == "wavy":
        _px(p, [(5, 9), (6, 9), (9, 9), (10, 9), (4, 10), (7, 10), (8, 10), (11, 10)], FACE, 0, oy)
    elif kind == "smile":
        p.fillRect(6, oy + 8, 4, 2, FACE)
        p.fillRect(4, oy + 9, 2, 2, FACE)
        p.fillRect(10, oy + 9, 2, 2, FACE)
        p.fillRect(4, oy + 11, 8, 2, FACE)


@lru_cache(maxsize=512)
def render(pose: Pose) -> QImage:
    img = QImage(W, H, QImage.Format_ARGB32_Premultiplied)
    img.fill(Qt.transparent)
    p = QPainter(img)

    down = max(0, min(7, pose.bob + pose.sit))

    # cabeça
    for ty, row in enumerate(HEAD_TEX):
        for tx, color in enumerate(row):
            p.fillRect(tx * 2, down + ty * 2, 2, 2, color)
    # corpo
    for ty, row in enumerate(BODY_TEX):
        for tx, color in enumerate(row):
            p.fillRect(tx * 2, HEAD_H + down + ty * 2, 2, 2, color)
    # pernas (o topo fica preso no corpo, os pés sobem)
    legs_top = 2 * HEAD_H + down
    for side, lift in ((0, pose.lift_l), (1, pose.lift_r)):
        height = max(1, H - legs_top - lift)
        for r in range(height):
            for c in range(8):
                color = LEG_TEX[min(3, r // 2)][side * 4 + c // 2]
                p.fillRect(side * 8 + c, legs_top + r, 1, 1, color)
    p.fillRect(7, legs_top, 2, H - legs_top, SEAM_DARK)
    # sombrinhas: cabeça sobre o corpo, corpo sobre as pernas
    p.fillRect(0, HEAD_H + down, 16, 1, SEAM)
    p.fillRect(0, legs_top, 16, 1, SEAM)

    if pose.singed:
        for tx, ty in SINGED:
            p.fillRect(tx * 2, down + ty * 2, 2, 2, QColor(40, 40, 40, 170))

    if pose.tint:
        p.setCompositionMode(QPainter.CompositionMode_SourceAtop)
        if pose.tint == "gold":
            p.fillRect(0, 0, W, H, QColor(255, 213, 79, 110))
        elif pose.tint == "sick":
            p.fillRect(0, 0, W, H, QColor(205, 220, 90, 100))
        p.setCompositionMode(QPainter.CompositionMode_SourceOver)

    # rosto
    lx = max(-1, min(1, pose.look_x))
    ly = max(-1, min(1, pose.look_y))
    _eye(p, 2 + lx, down + 2 + ly, pose.eyes, -1)
    _eye(p, 10 + lx, down + 2 + ly, pose.eyes, 1)
    _mouth(p, pose.mouth, down)
    if pose.blush:
        p.fillRect(0, down + 8, 2, 1, BLUSH)
        p.fillRect(14, down + 8, 2, 1, BLUSH)
    if pose.tear:
        p.fillRect(3 + lx, down + 6 + ly, 1, 2, TEAR)

    if pose.flash > 0:
        p.setCompositionMode(QPainter.CompositionMode_SourceAtop)
        p.fillRect(0, 0, W, H, QColor(255, 255, 255, int(235 * min(1.0, pose.flash))))
    p.end()
    return img


def render_head(pose: Pose) -> QImage:
    """Só a cabeça (16x16), usada no ícone da bandeja."""
    return render(Pose(eyes=pose.eyes, mouth=pose.mouth, blush=pose.blush, tint=pose.tint)).copy(0, 0, W, HEAD_H)
