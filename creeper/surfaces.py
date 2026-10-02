"""Onde o creeper pode pisar e se esconder: as janelas abertas, vistas como retângulos.

Os retângulos vêm do sistema em pixels físicos e viram coordenadas do Qt (que escala cada
monitor mantendo o canto de cima-esquerda dele no lugar).
"""
from PySide6.QtGui import QGuiApplication

from . import desktop

Rect = tuple[float, float, float, float]          # esquerda, topo, direita, base
Platform = tuple[float, float, float]             # y, x inicial, x final


def _to_logical(left: float, top: float, right: float, bottom: float) -> Rect:
    for screen in QGuiApplication.screens():
        g, dpr = screen.geometry(), screen.devicePixelRatio()
        if g.left() <= left < g.left() + g.width() * dpr and g.top() <= top < g.top() + g.height() * dpr:
            ox, oy = g.left(), g.top()
            return (ox + (left - ox) / dpr, oy + (top - oy) / dpr, ox + (right - ox) / dpr, oy + (bottom - oy) / dpr)
    return left, top, right, bottom


def windows() -> list[Rect]:
    """Janelas abertas, da de cima pra de baixo, em coordenadas do Qt."""
    try:
        return [_to_logical(*r) for r in desktop.window_rects()]
    except Exception:
        return []


def _subtract(segments: list[tuple[float, float]], cut: tuple[float, float]) -> list[tuple[float, float]]:
    out = []
    for a, b in segments:
        if cut[1] <= a or cut[0] >= b:
            out.append((a, b))
            continue
        if cut[0] > a:
            out.append((a, cut[0]))
        if cut[1] < b:
            out.append((cut[1], b))
    return out


def platforms(rects: list[Rect], min_width: float = 70) -> list[Platform]:
    """Trechos visíveis da borda de cima de cada janela (o que não está coberto por outra janela)."""
    result = []
    for i, (left, top, right, _bottom) in enumerate(rects):
        segments = [(left, right)]
        for l2, t2, r2, b2 in rects[:i]:          # janelas por cima desta
            if t2 <= top <= b2:
                segments = _subtract(segments, (l2, r2))
        result += [(top, a, b) for a, b in segments if b - a >= min_width]
    return result
