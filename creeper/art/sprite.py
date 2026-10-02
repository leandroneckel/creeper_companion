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

from .. import cosmetics

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


def _texture(rng: random.Random, w: int, h: int) -> list[list[int]]:
    """Textura em índices de tom (0 = mais escuro); a cor vem da paleta da roupa na hora de desenhar."""
    weights = [wt for _, wt in _GREENS]
    return [[rng.choices(range(len(_GREENS)), weights)[0] for _ in range(w)] for _ in range(h)]


@lru_cache(maxsize=None)
def _palette(skin: str | None) -> tuple[list[QColor], QColor]:
    """Tons do corpo e cor do rosto para uma cor do guarda-roupa (None = verde clássico)."""
    data = cosmetics.SKINS.get(skin) if skin else None
    if not data:
        return [QColor(c) for c, _ in _GREENS], FACE
    return [QColor(c) for c in data["tons"]], QColor(data.get("rosto", FACE.name()))


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
    skin: str | None = None  # cor do guarda-roupa (cosmetics.SKINS)


def _px(p: QPainter, pts, color: QColor, ox: int, oy: int) -> None:
    for x, y in pts:
        p.fillRect(ox + x, oy + y, 1, 1, color)


def _eye(p: QPainter, x: int, y: int, kind: str, side: int, face: QColor = FACE) -> None:
    """Desenha um olho na caixa 4x4 em (x, y). side: -1 esquerdo, +1 direito."""
    full = [(i, j) for j in range(4) for i in range(4)]
    if kind == "closed":
        p.fillRect(x, y + 2, 4, 1, face)
    elif kind == "half":
        p.fillRect(x, y + 2, 4, 2, face)
    elif kind == "happy":
        _px(p, [(1, 1), (2, 1), (0, 2), (3, 2), (0, 3), (3, 3)], face, x, y)
    elif kind == "angry":
        cut = {(2, 0), (3, 0), (3, 1)} if side < 0 else {(0, 0), (1, 0), (0, 1)}
        _px(p, [c for c in full if c not in cut], face, x, y)
    elif kind == "sad":
        cut = {(0, 0), (1, 0), (0, 1)} if side < 0 else {(2, 0), (3, 0), (3, 1)}
        _px(p, [c for c in full if c not in cut], face, x, y)
    elif kind == "x":
        _px(p, [(0, 0), (3, 0), (1, 1), (2, 1), (1, 2), (2, 2), (0, 3), (3, 3)], face, x, y)
    elif kind == "squint":
        if side < 0:
            pts = [(0, 1), (1, 1), (2, 2), (3, 2), (0, 3), (1, 3)]
        else:
            pts = [(2, 1), (3, 1), (0, 2), (1, 2), (2, 3), (3, 3)]
        _px(p, pts, face, x, y)
    else:
        p.fillRect(x, y, 4, 4, face)
        if kind == "glint":
            p.fillRect(x + 1, y + 1, 1, 1, GLINT)
        elif kind == "wide":
            p.fillRect(x + 1, y + 1, 2, 2, GLINT)


def _mouth(p: QPainter, kind: str, oy: int, face: QColor = FACE) -> None:
    if kind == "o":
        p.fillRect(6, oy + 7, 4, 4, face)
        return
    p.fillRect(6, oy + 6, 4, 2, face)  # "nariz"
    if kind == "classic":
        p.fillRect(4, oy + 8, 8, 4, face)
        p.fillRect(4, oy + 12, 2, 2, face)
        p.fillRect(10, oy + 12, 2, 2, face)
    elif kind in ("open", "hiss"):
        p.fillRect(4, oy + 8, 8, 6, face)
        if kind == "open":
            p.fillRect(6, oy + 11, 4, 2, TONGUE)
        else:
            p.fillRect(5, oy + 10, 6, 2, FACE_SOFT)
    elif kind == "chew":
        p.fillRect(4, oy + 8, 8, 3, face)
        p.fillRect(4, oy + 11, 2, 1, face)
        p.fillRect(10, oy + 11, 2, 1, face)
    elif kind == "wavy":
        _px(p, [(5, 9), (6, 9), (9, 9), (10, 9), (4, 10), (7, 10), (8, 10), (11, 10)], face, 0, oy)
    elif kind == "smile":
        p.fillRect(6, oy + 8, 4, 2, face)
        p.fillRect(4, oy + 9, 2, 2, face)
        p.fillRect(10, oy + 9, 2, 2, face)
        p.fillRect(4, oy + 11, 8, 2, face)


def head_down(pose: Pose) -> int:
    """Quantos pixels finos a cabeça desce (respiração, sentar). O chapéu acompanha."""
    return max(0, min(7, pose.bob + pose.sit))


@lru_cache(maxsize=512)
def render(pose: Pose) -> QImage:
    img = QImage(W, H, QImage.Format_ARGB32_Premultiplied)
    img.fill(Qt.transparent)
    p = QPainter(img)

    down = head_down(pose)
    tones, face = _palette(pose.skin)

    # cabeça
    for ty, row in enumerate(HEAD_TEX):
        for tx, tone in enumerate(row):
            p.fillRect(tx * 2, down + ty * 2, 2, 2, tones[tone])
    # corpo
    for ty, row in enumerate(BODY_TEX):
        for tx, tone in enumerate(row):
            p.fillRect(tx * 2, HEAD_H + down + ty * 2, 2, 2, tones[tone])
    # pernas (o topo fica preso no corpo, os pés sobem)
    legs_top = 2 * HEAD_H + down
    for side, lift in ((0, pose.lift_l), (1, pose.lift_r)):
        height = max(1, H - legs_top - lift)
        for r in range(height):
            for c in range(8):
                tone = LEG_TEX[min(3, r // 2)][side * 4 + c // 2]
                p.fillRect(side * 8 + c, legs_top + r, 1, 1, tones[tone])
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
    _eye(p, 2 + lx, down + 2 + ly, pose.eyes, -1, face)
    _eye(p, 10 + lx, down + 2 + ly, pose.eyes, 1, face)
    _mouth(p, pose.mouth, down, face)
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
    return render(Pose(eyes=pose.eyes, mouth=pose.mouth, blush=pose.blush, tint=pose.tint,
                       skin=pose.skin)).copy(0, 0, W, HEAD_H)


AURA_PAD = 2   # quanto a aura passa do corpo, em pixels finos


@lru_cache(maxsize=128)
def charged_aura(pose: Pose, phase: int) -> QImage:
    """Aura do creeper carregado: listras azuis andando na diagonal, um pouco maior que o corpo.

    phase (0..5) faz as listras andarem; o desenho fica em cache.
    """
    pad = AURA_PAD
    size = (W + 2 * pad, H + 2 * pad)
    silhouette = QImage(*size, QImage.Format_ARGB32_Premultiplied)
    silhouette.fill(Qt.transparent)
    p = QPainter(silhouette)
    body = render(Pose(bob=pose.bob, sit=pose.sit, lift_l=pose.lift_l, lift_r=pose.lift_r))
    for dx in range(2 * pad + 1):          # o corpo "engordado" em todas as direções
        for dy in range(2 * pad + 1):
            p.drawImage(dx, dy, body)
    p.end()

    aura = QImage(*size, QImage.Format_ARGB32_Premultiplied)
    aura.fill(Qt.transparent)
    p = QPainter(aura)
    light, mid = QColor(170, 235, 255, 235), QColor(79, 195, 247, 170)
    for y in range(size[1]):
        for x in range(size[0]):
            band = (x - y + phase) % 6
            if band < 2:
                p.fillRect(x, y, 1, 1, light if band == 0 else mid)
    p.setCompositionMode(QPainter.CompositionMode_DestinationIn)
    p.drawImage(0, 0, silhouette)
    p.end()
    return aura
