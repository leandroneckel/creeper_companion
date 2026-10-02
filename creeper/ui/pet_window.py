"""Janela transparente do creeper: desenho, balão de fala, barra de botões,
painel de status e interação com o mouse."""
import time

from PySide6.QtCore import QPoint, QPointF, QRect, QRectF, Qt
from PySide6.QtGui import QColor, QCursor, QFont, QFontMetrics, QGuiApplication, QPainter, QPen, QRegion
from PySide6.QtWidgets import QToolTip, QWidget

from .. import cosmetics, desktop
from ..art import icons, sprite
from ..needs import EFFECT_LABELS, LABELS, STATS

SLOT = 28
BUTTONS = [
    ("comer", "Comer"),
    ("beber", "Beber"),
    ("atividades", "Atividades"),
    ("dormir", "Dormir"),
    ("carinho", "Fazer carinho"),
    ("bandeja", "Recolher para a bandeja"),
    ("menu", "Mais opções"),
]
WIDTH = 270
STATUS_W = 214
BUBBLE_MAX_W = 236
STICKY_SECONDS = 90   # quanto tempo o balão com botão ("Fiz!", "Ver") fica voltando
STICKY_BUTTONS = {"atualizar": "Ver", "permitir_atualizacoes": "Pode!"}   # lembretes de água e pausa: "Fiz!"

TOOLTIP_BG = QColor(18, 4, 22, 238)
TOOLTIP_BORDER = QColor("#4B2A86")


class PetWindow(QWidget):
    def __init__(self, app):
        flags = (Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool
                 | Qt.WindowDoesNotAcceptFocus | desktop.window_flags_extra())
        super().__init__(None, flags)
        self.app = app
        self.pet = app.pet
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self.setMouseTracking(True)
        self.setWindowTitle("Creeper Companion")

        self.font_bubble = QFont()
        self.font_bubble.setPixelSize(13)
        self.font_bubble.setWeight(QFont.DemiBold)
        self.font_small = QFont()
        self.font_small.setPixelSize(11)
        self.font_small.setWeight(QFont.DemiBold)
        self.font_title = QFont()
        self.font_title.setPixelSize(12)
        self.font_title.setBold(True)

        self.bubble_text: str | None = None
        self.bubble_until = 0.0
        self.sticky: tuple[str, str, float] | None = None   # balão com botão: (texto, tipo, até quando)
        self.bubble_btn: QRect | None = None
        self.hover_since: float | None = None
        self.hover_lost: float | None = None
        self.hover_btn: str | None = None
        self.press: tuple[QPoint, float] | None = None
        self.dragging = False
        self.drag_offset = QPointF()
        self.stroke_dir = 0
        self.stroke_x: int | None = None
        self.stroke_times: list[float] = []
        self._mask_key = None
        self._last_sig = None
        self.resize_for_scale()

    # ---- geometria -------------------------------------------------------
    def resize_for_scale(self) -> None:
        s = self.pet.s
        self.sw, self.sh = 16 * s, 40 * s
        self.H = self.sh + 305
        self.setFixedSize(WIDTH, self.H)
        self.sync_position()

    def sync_position(self) -> None:
        x = round(self.pet.x - WIDTH / 2)
        y = round(self.pet.y - self.H)
        if x != self.x() or y != self.y():
            self.move(x, y)

    def sprite_rect(self) -> QRectF:
        pet = self.pet   # pet.sprite_w/h já incluem a poção de encolher
        w = pet.sprite_w * (1 + pet.swell + 0.22 * pet.squash)
        h = pet.sprite_h * (1 + pet.swell - 0.22 * pet.squash)
        return QRectF(WIDTH / 2 - w / 2, self.H - h - pet.jump, w, h)

    def toolbar_rect(self) -> QRect:
        w = len(BUTTONS) * SLOT + 8
        h = SLOT + 8
        return QRect((WIDTH - w) // 2, int(self.H - self.pet.sprite_h) - 12 - h, w, h)

    def button_rects(self) -> list[tuple[str, QRect]]:
        bar = self.toolbar_rect()
        return [(bid, QRect(bar.x() + 4 + i * SLOT, bar.y() + 4, SLOT, SLOT)) for i, (bid, _) in enumerate(BUTTONS)]

    def status_height(self) -> int:
        return 8 + 18 + 15 + 15 + len(STATS) * 15 + 6

    def gift_rect(self) -> QRect | None:
        """Presente esperando pra ser aberto, no chão ao lado dele."""
        pet = self.pet
        if not self.app.progress.presents or pet.hidden or pet.state in ("dragged", "fall", "exploded", "hide"):
            return None
        g = 8 * pet.s
        return QRect(int(WIDTH / 2 - pet.sprite_w / 2 - g - 6), self.H - g, g, g)

    def status_rect(self) -> QRect:
        h = self.status_height()
        return QRect((WIDTH - STATUS_W) // 2, self.toolbar_rect().top() - 6 - h, STATUS_W, h)

    def _visible_x_range(self) -> tuple[int, int]:
        """Parte da janela que está dentro da tela (para o balão não ser cortado)."""
        screen = self.screen() or QGuiApplication.primaryScreen()
        geo = screen.geometry()
        return max(0, geo.left() - self.x()), min(WIDTH, geo.right() + 1 - self.x())

    # ---- estado de hover -------------------------------------------------
    def toolbar_allowed(self) -> bool:
        pet = self.pet
        return (not self.dragging and pet.can_interact() and pet.jump == 0 and not pet.roaming()
                and pet.state not in ("hiss", "fall", "exploded"))

    def ui_rect(self) -> QRect:
        """O que está aparecendo dele (creeper + barra + painel), em coordenadas da tela.
        Os menus abrem do lado disso, pra não cobrir nada."""
        rect = self.sprite_rect().toAlignedRect()
        if self.toolbar_visible():
            rect = rect.united(self.toolbar_rect())
            if self.status_visible():
                rect = rect.united(self.status_rect())
        return rect.translated(self.pos())

    def toolbar_visible(self) -> bool:
        return (self.toolbar_allowed() and self.hover_since is not None
                and time.monotonic() - self.hover_since > 0.2)

    def status_visible(self) -> bool:
        return self.toolbar_visible() and time.monotonic() - self.hover_since > 0.7

    def update_hover(self) -> None:
        local = self.mapFromGlobal(QCursor.pos())
        now = time.monotonic()
        zone = self.sprite_rect().toRect().adjusted(-4, -4, 4, 4)
        if self.hover_since is not None and self.toolbar_allowed():
            zone = zone.united(self.toolbar_rect().adjusted(-8, -8, 8, 8))
            if self.status_visible():
                zone = zone.united(self.status_rect().adjusted(-8, -8, 8, 8))
        inside = zone.contains(local) and not self.pet.hidden
        popup = self.app._popup
        if popup is not None and popup.isVisible() and self.hover_since is not None:
            inside = True   # com o menu aberto do lado, o painel continua aparecendo
        if inside:
            self.hover_lost = None
            if self.hover_since is None:
                self.hover_since = now
        elif self.hover_since is not None:
            if self.hover_lost is None:
                self.hover_lost = now
            elif now - self.hover_lost > 0.6:
                self.hover_since = None
                self.hover_lost = None
                self.hover_btn = None
                QToolTip.hideText()

    # ---- quadro ----------------------------------------------------------
    def frame(self) -> None:
        """Chamado a cada quadro pelo app."""
        if not self.isVisible():
            return
        if not self.dragging:
            self.sync_position()
        self.update_hover()
        self.pet.attention = self.hover_since is not None
        now = time.monotonic()
        if self.sticky and now > self.sticky[2]:
            self.sticky = None
        if self.bubble_text and now > self.bubble_until:
            self.bubble_text = None
        if self.pet.state == "exploded":
            self.bubble_text = None
        elif not self.bubble_text and self.sticky:
            # outra fala cobriu o lembrete; quando ela some, o lembrete com "Fiz!" volta
            self.bubble_text, self.bubble_until = self.sticky[0], self.sticky[2]
        if desktop.needs_input_mask():
            self._update_mask()
        sig = self._signature()
        if sig is None or sig != self._last_sig:
            self._last_sig = sig
            self.update()

    def _signature(self):
        """Resumo de tudo que aparece na tela; se não mudou, não precisa redesenhar."""
        pet = self.pet
        if pet.particles or pet.props or pet.size != pet.size_target:
            return None
        r = self.sprite_rect()
        prog = self.app.progress
        status = None
        if self.status_visible():
            n = pet.needs
            status = (n.mood(), tuple(int(v // 5) for v in n.values.values()),
                      tuple(n.active_effects()), self.app.settings.name,
                      prog.level, int(prog.fraction() * 129), prog.losing)
        return (pet.pose(), pet.hidden, pet.held, round(pet.tilt), round(r.x()), round(r.y()),
                round(r.width()), round(r.height()), self.bubble_text, self.toolbar_visible(),
                self.hover_btn, pet.state == "sleep", status, prog.presents, self.sticky is None,
                pet.ghost, pet.tool, round(pet.tool_angle), self.app.settings.hat,
                int(pet.clock * 8) % 6 if self.app.settings.charged else 0,
                self._occluder_rect().getRect() if pet.occluder else None)

    def show_bubble(self, text: str, seconds: float | None = None, action: str | None = None) -> None:
        """Mostra uma fala. Com `action` (veja STICKY_BUTTONS), o balão ganha um botão e volta se
        outra fala o cobrir."""
        self.bubble_text = text
        if action:
            self.sticky = (text, action, time.monotonic() + STICKY_SECONDS)
            self.bubble_until = self.sticky[2]
        else:
            self.bubble_until = time.monotonic() + (seconds or max(3.5, min(9.0, 2.5 + len(text) / 13)))

    def sticky_active(self) -> bool:
        return self.sticky is not None and time.monotonic() < self.sticky[2]

    def clear_sticky(self) -> None:
        if self.sticky and self.bubble_text == self.sticky[0]:
            self.bubble_text = None
        self.sticky = None

    def showEvent(self, event) -> None:
        super().showEvent(event)
        desktop.setup_window(self)

    # ---- máscara de entrada (Linux/X11) ----------------------------------
    def _update_mask(self) -> None:
        body = self.sprite_rect()
        grow = 10 if self.app.settings.charged else 2   # a aura passa um pouco do corpo
        rects = [body.toRect().adjusted(-grow, -grow, grow, grow)]
        hat = self._hat_rect(body, self.pet.pose())
        if hat:
            rects.append(hat.toRect().adjusted(-2, -2, 2, 2))
        if self.toolbar_visible():
            rects.append(self.toolbar_rect())
            if self.status_visible():
                rects.append(self.status_rect())
        if self.bubble_text:
            rects.append(QRect(0, 0, WIDTH, self.toolbar_rect().top()))
        gift = self.gift_rect()
        if gift:
            rects.append(gift.adjusted(-2, -12, 2, 0))
        for prop in self.pet.props:
            rects.append(self._prop_rect(prop).toRect().adjusted(-4, -4, 4, 4))
        if self.pet.tool:
            rects.append(self._tool_rect().toRect().adjusted(-8, -8, 8, 8))
        for part in self.pet.particles:
            # a máscara também recorta o desenho no X11, então inclui cada partícula
            if part.kind in ("boom", "bolt"):
                rects.append(QRect(0, 0, WIDTH, self.H))
                continue
            size = 48 if part.kind in ("smoke", "z", "note", "icon") else 12
            rects.append(QRect(int(WIDTH / 2 + part.x - size / 2), int(self.H + part.y - size), size, size + 4))
        key = tuple((r.x(), r.y(), r.width(), r.height()) for r in rects)
        if key == self._mask_key:
            return
        self._mask_key = key
        region = QRegion()
        for r in rects:
            region = region.united(QRegion(r))
        occluder = self._occluder_rect()
        if occluder is not None:   # o clique na parte escondida tem que ir pra janela de verdade
            region = region.subtracted(QRegion(occluder))
        self.setMask(region)

    # ---- desenho ---------------------------------------------------------
    def paintEvent(self, event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.SmoothPixmapTransform, False)
        pet = self.pet
        cx = WIDTH / 2
        ground = self.H

        if not pet.hidden:
            p.save()
            occluder = self._occluder_rect()
            if occluder is not None:   # esconde-esconde: não desenha a parte "atrás" da janela/borda/chão
                p.setClipRegion(QRegion(self.rect()).subtracted(QRegion(occluder)))
            if pet.state not in ("dragged", "fall", "hide"):
                lift = max(0.35, 1 - pet.jump / (pet.sprite_h * 0.5))
                sw = pet.sprite_w * 1.05 * lift
                p.setPen(Qt.NoPen)
                p.setBrush(QColor(0, 0, 0, int(60 * lift * (0.3 if pet.ghost else 1))))
                p.drawEllipse(QRectF(cx - sw / 2, ground - 6, sw, 6))
            self._draw_gift(p)
            self._draw_props(p, behind=True)
            self._draw_creeper(p)
            self._draw_props(p, behind=False)
            p.restore()

        self._draw_particles(p)

        top = self.H - pet.sprite_h - 10
        if self.toolbar_visible():
            self._draw_toolbar(p)
            top = self.toolbar_rect().top() - 4
            if self.status_visible():
                rect = self.status_rect()
                self._draw_status(p, rect)
                top = rect.top() - 4
        if self.bubble_text and not pet.hidden and pet.state != "hide":
            self._draw_bubble(p, top)
        p.end()

    def _draw_creeper(self, p: QPainter) -> None:
        pet = self.pet
        pose = pet.pose()
        img = sprite.render(pose)
        rect = self.sprite_rect()
        outfit = self.app.settings
        p.save()
        if pet.ghost:
            p.setOpacity(0.28)
        if pet.tilt:
            pivot = QPointF(rect.center().x(), rect.top() + rect.height() * 0.3)
            p.translate(pivot)
            p.rotate(pet.tilt)
            p.translate(-pivot)
        p.drawImage(rect, img)
        px_w, px_h = rect.width() / sprite.W, rect.height() / sprite.H   # tamanho de um pixel fino
        if outfit.charged:
            pad = sprite.AURA_PAD
            p.save()
            p.setOpacity(p.opacity() * 0.7)
            p.drawImage(rect.adjusted(-pad * px_w, -pad * px_h, pad * px_w, pad * px_h),
                        sprite.charged_aura(pose, int(pet.clock * 8) % 6))
            p.restore()
        hat_rect = self._hat_rect(rect, pose)
        if hat_rect:
            p.drawImage(hat_rect, icons.hat_image(outfit.hat))
        if pet.held:
            size = 8 * pet.s
            ix = rect.center().x() - size * 0.15
            iy = rect.top() + rect.height() * 0.28
            p.save()
            p.translate(ix, iy)
            if pet.state == "drink":
                p.rotate(-35)
            p.drawImage(QRectF(-size / 2, -size / 2, size, size), icons.image(pet.held))
            p.restore()
        if pet.tool:
            tool = self._tool_rect()
            p.save()
            p.translate(tool.center())
            if pet.facing < 0:
                p.scale(-1, 1)   # espelha pra quando ele olha pra esquerda
            p.rotate(pet.tool_angle)
            p.drawImage(QRectF(-tool.width() / 2, -tool.height() / 2, tool.width(), tool.height()),
                        icons.image(pet.tool))
            p.restore()
        p.restore()

    def _occluder_rect(self) -> QRect | None:
        """O que cobre ele no esconde-esconde, em coordenadas da janela (ou None)."""
        occ = self.pet.occluder
        if not occ:
            return None
        left, top, right, bottom = occ
        x0, y0 = self.pos().x(), self.pos().y()   # canto da janela na tela
        return QRectF(left - x0, top - y0, right - left, bottom - top).toAlignedRect().intersected(self.rect())

    def _hat_rect(self, rect: QRectF, pose) -> QRectF | None:
        """Onde o chapéu fica: em cima da cabeça, descendo junto quando ele respira ou senta."""
        hat = cosmetics.HATS.get(self.app.settings.hat)
        if not hat:
            return None
        img = icons.hat_image(self.app.settings.hat)
        px_w, px_h = rect.width() / sprite.W, rect.height() / sprite.H
        top = rect.top() + (sprite.head_down(pose) - (img.height() - hat["sobre"])) * px_h
        return QRectF(rect.left() + hat["x"] * px_w, top, img.width() * px_w, img.height() * px_h)

    def _tool_rect(self) -> QRectF:
        pet = self.pet
        x, y = pet.tool_anchor()
        size = pet.tool_size()
        return QRectF(WIDTH / 2 + x - size / 2, self.H + y - size / 2, size, size)

    def _prop_rect(self, prop) -> QRectF:
        cx, gy = WIDTH / 2 + prop.x, self.H + prop.y
        if prop.kind == "big":
            img = icons.big_image(prop.name)
            w, h = img.width() * prop.size, img.height() * prop.size
            return QRectF(cx - w / 2, gy - h, w, h)
        if prop.kind == "water":
            return QRectF(cx - prop.size / 2, gy - 7, prop.size, 9)
        if prop.kind == "line":
            x1, y1 = WIDTH / 2 + prop.x, self.H + prop.y
            x2, y2 = WIDTH / 2 + prop.x2, self.H + prop.y2
            return QRectF(min(x1, x2) - 3, min(y1, y2) - 3, abs(x2 - x1) + 6, abs(y2 - y1) + 6)
        return QRectF(cx - prop.size / 2, gy - prop.size, prop.size, prop.size)

    def _draw_props(self, p: QPainter, behind: bool) -> None:
        """Objetos das atividades. Atrás dele: poça, porco, bloco, planta; na frente: linha de pesca."""
        for prop in self.pet.props:
            if (prop.kind == "line") == behind:
                continue
            r = self._prop_rect(prop)
            if prop.kind == "water":
                p.setPen(Qt.NoPen)
                p.setBrush(QColor("#2F6FD0"))
                p.drawRoundedRect(r, 4, 4)
                p.setBrush(QColor("#5B9BF0"))
                p.drawRoundedRect(r.adjusted(3, 1, -3, -4), 3, 3)
                wave = int(self.pet.clock * 2) % 2
                p.fillRect(QRectF(r.x() + 10 + wave * 6, r.y() + 2, 10, 1.5), QColor(255, 255, 255, 150))
                p.fillRect(QRectF(r.right() - 26 - wave * 6, r.y() + 4, 8, 1.5), QColor(255, 255, 255, 120))
            elif prop.kind == "line":
                p.setPen(QColor(235, 235, 235, 220))
                p.drawLine(QPointF(WIDTH / 2 + prop.x, self.H + prop.y), QPointF(WIDTH / 2 + prop.x2, self.H + prop.y2))
                p.setPen(Qt.NoPen)
                bx, by = WIDTH / 2 + prop.x2, self.H + prop.y2
                p.fillRect(QRectF(bx - 3, by - 6, 6, 3), QColor("#E53935"))   # boia
                p.fillRect(QRectF(bx - 3, by - 3, 6, 3), QColor("#FAFAFA"))
            elif prop.kind == "big":
                img = icons.big_image(prop.name)
                if prop.flip:
                    img = img.mirrored(True, False)
                p.drawImage(r, img)
            else:
                p.drawImage(r, icons.image(prop.name))
                if prop.crack > 0:
                    self._draw_cracks(p, r, prop.crack)

    def _draw_cracks(self, p: QPainter, r: QRectF, amount: float) -> None:
        """Rachaduras do bloco sendo minerado, aumentando a cada golpe."""
        px = r.width() / 12
        cracks = [(5, 5), (6, 6), (4, 6), (6, 4), (3, 7), (7, 3), (8, 7), (2, 4), (7, 9), (4, 9), (9, 5),
                  (2, 8), (9, 2), (1, 2), (10, 9), (5, 1), (6, 10), (1, 10)]
        color = QColor(20, 20, 20, 190)
        for x, y in cracks[:max(1, int(len(cracks) * amount))]:
            p.fillRect(QRectF(r.x() + x * px, r.y() + y * px, px, px), color)

    def _draw_gift(self, p: QPainter) -> None:
        rect = self.gift_rect()
        if not rect:
            return
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(0, 0, 0, 50))
        p.drawEllipse(QRectF(rect.x(), rect.bottom() - 3, rect.width(), 5))
        p.drawImage(rect, icons.image("presente"))
        count = self.app.progress.presents
        if count > 1:
            p.setFont(self.font_small)
            text_rect = QRect(rect.right() - 18, rect.bottom() - 11, 22, 13)   # como a contagem de itens do jogo
            p.setPen(QColor(0, 0, 0, 200))
            p.drawText(text_rect.translated(1, 1), Qt.AlignRight | Qt.AlignVCenter, f"x{count}")
            p.setPen(QColor("#FFFFFF"))
            p.drawText(text_rect, Qt.AlignRight | Qt.AlignVCenter, f"x{count}")

    def _draw_particles(self, p: QPainter) -> None:
        pet = self.pet
        cx, gy = WIDTH / 2, self.H
        p.setPen(Qt.NoPen)
        for part in pet.particles:
            x, y = cx + part.x, gy + part.y - (pet.jump if part.kind in ("sweat",) else 0)
            fade = 1.0 - part.age / part.life
            if part.kind in ("z", "note"):
                font = QFont(self.font_title)
                font.setPixelSize(int(part.size + part.age * 4))
                p.setFont(font)
                color = QColor(part.color)
                color.setAlphaF(max(0.0, min(1.0, fade * 1.4)))
                p.setPen(QColor(0, 0, 0, int(160 * fade)))
                p.drawText(QPointF(x + 1, y + 1), part.text)
                p.setPen(color)
                p.drawText(QPointF(x, y), part.text)
                p.setPen(Qt.NoPen)
            elif part.kind == "bolt":
                pts = [QPointF(cx + px_, gy + py_) for px_, py_ in part.points]
                glow = QColor(79, 195, 247, int(200 * fade))
                for width, color in ((7, glow), (3, QColor(255, 255, 255, int(255 * fade)))):
                    p.setPen(QPen(color, width))
                    p.drawPolyline(pts)
                p.setPen(Qt.NoPen)
            elif part.kind == "heart":
                size = part.size * 2
                p.setOpacity(max(0.0, min(1.0, fade * 1.5)))
                p.drawImage(QRectF(x - size / 2, y - size / 2, size, size), icons.image("carinho"))
                p.setOpacity(1.0)
            elif part.kind == "icon":
                size = part.size
                p.setOpacity(max(0.0, min(1.0, fade * 3)))
                p.drawImage(QRectF(x - size / 2, y - size, size, size), icons.image(part.text))
                p.setOpacity(1.0)
            elif part.kind == "rocket":
                s = part.size
                p.fillRect(QRectF(x - s * 0.7, y - s * 2.5, s * 1.4, s * 3), QColor(part.color))
                p.fillRect(QRectF(x - s * 0.7, y - s * 3.2, s * 1.4, s * 0.7), QColor("#FAFAFA"))
                p.fillRect(QRectF(x - s * 0.25, y + s * 0.5, s * 0.5, s * 1.5), QColor("#8D6E63"))
            elif part.kind == "smoke":
                size = part.size * (1 + 1.5 * part.age / part.life)
                color = QColor(part.color)
                color.setAlpha(int(200 * fade))
                p.fillRect(QRectF(x - size / 2, y - size / 2, size, size), color)
            elif part.kind == "boom":
                r = part.size * (0.35 + part.age / part.life)
                p.setBrush(QColor(255, 255, 255, int(230 * fade)))
                p.drawEllipse(QPointF(x, y), r, r)
                p.setBrush(Qt.NoBrush)
            else:  # crumb, debris, sweat, spark, orb
                color = QColor(part.color)
                if part.kind in ("spark", "sweat", "orb"):
                    color.setAlpha(int(255 * fade))
                if part.kind == "sweat":
                    color = QColor(100, 181, 246, int(255 * fade))
                s = part.size
                p.fillRect(QRectF(x - s / 2, y - s / 2, s, s), color)

    def _bevel(self, p: QPainter, r: QRect, fill: QColor, light: QColor, dark: QColor) -> None:
        p.fillRect(r, fill)
        p.fillRect(QRect(r.left(), r.top(), r.width(), 2), light)
        p.fillRect(QRect(r.left(), r.top(), 2, r.height()), light)
        p.fillRect(QRect(r.left(), r.bottom() - 1, r.width(), 2), dark)
        p.fillRect(QRect(r.right() - 1, r.top(), 2, r.height()), dark)

    def _draw_toolbar(self, p: QPainter) -> None:
        bar = self.toolbar_rect()
        p.fillRect(bar.adjusted(-2, -2, 2, 2), QColor("#000000"))
        self._bevel(p, bar, QColor("#C6C6C6"), QColor("#FFFFFF"), QColor("#555555"))
        for bid, rect in self.button_rects():
            self._bevel(p, rect.adjusted(1, 1, -1, -1), QColor("#8B8B8B"), QColor("#373737"), QColor("#FFFFFF"))
            name = bid
            if bid == "dormir" and self.pet.state == "sleep":
                name = "acordar"
            icon_rect = QRect(rect.x() + 2, rect.y() + 2, 24, 24)
            p.drawImage(icon_rect, icons.image(name))
            if bid == self.hover_btn:
                p.fillRect(rect.adjusted(3, 3, -3, -3), QColor(255, 255, 255, 80))

    def _draw_tooltip_box(self, p: QPainter, r: QRect) -> None:
        p.fillRect(r.adjusted(2, 0, -2, 0), TOOLTIP_BG)
        p.fillRect(r.adjusted(0, 2, 0, -2), TOOLTIP_BG)
        pen_r = r.adjusted(2, 2, -2, -2)
        p.fillRect(QRect(pen_r.left(), pen_r.top(), pen_r.width(), 2), TOOLTIP_BORDER)
        p.fillRect(QRect(pen_r.left(), pen_r.bottom() - 1, pen_r.width(), 2), TOOLTIP_BORDER)
        p.fillRect(QRect(pen_r.left(), pen_r.top(), 2, pen_r.height()), TOOLTIP_BORDER)
        p.fillRect(QRect(pen_r.right() - 1, pen_r.top(), 2, pen_r.height()), TOOLTIP_BORDER)

    def _draw_status(self, p: QPainter, r: QRect) -> None:
        n = self.pet.needs
        self._draw_tooltip_box(p, r)
        x0, y = r.left() + 10, r.top() + 8
        p.setFont(self.font_title)
        p.setPen(QColor("#FFFFFF"))
        p.drawText(QRect(x0, y, r.width() - 20, 16), Qt.AlignLeft | Qt.AlignVCenter,
                   f"{self.app.settings.name} · {n.mood()}")
        y += 18
        issues = [n.level_word(stat) for stat in STATS if n[stat] < 40]
        issues += [EFFECT_LABELS[e] for e in n.active_effects() if e in EFFECT_LABELS]
        if self.pet.state == "sleep":
            issues.insert(0, "dormindo")
        if self.app.progress.presents:
            issues.insert(0, "tem presente pra você")
        if self.app.progress.losing:
            issues.append("perdendo XP")
        p.setFont(self.font_small)
        p.setPen(QColor("#B9A6D6"))
        p.drawText(QRect(x0, y, r.width() - 20, 14), Qt.AlignLeft | Qt.AlignVCenter,
                   ", ".join(issues) if issues else "tudo certo")
        y += 16
        # barra de XP verde, como a do Minecraft
        prog = self.app.progress
        p.setPen(QColor("#80FF20"))
        p.drawText(QRect(x0, y, 64, 13), Qt.AlignLeft | Qt.AlignVCenter, f"Nível {prog.level}")
        bar = QRect(x0 + 66, y + 3, 129, 7)
        p.fillRect(bar.adjusted(-1, -1, 1, 1), QColor("#000000"))
        p.fillRect(bar, QColor("#2A2A2A"))
        fill = int(bar.width() * prog.fraction())
        if fill:
            p.fillRect(QRect(bar.x(), bar.y(), fill, bar.height()), QColor("#7FD321"))
            p.fillRect(QRect(bar.x(), bar.y(), fill, 2), QColor("#B5F23A"))
        y += 15
        for stat in STATS:
            p.setPen(QColor("#E0E0E0"))
            p.drawText(QRect(x0, y, 64, 13), Qt.AlignLeft | Qt.AlignVCenter, LABELS[stat])
            value = n[stat]
            full = int(value // 10)
            half = (value % 10) >= 5
            for i in range(10):
                cell = QRect(x0 + 66 + i * 13, y, 12, 12)
                if i < full:
                    p.drawImage(cell, icons.status_image(stat))
                elif i == full and half:
                    p.drawImage(cell, icons.status_image(stat, dim=True))
                    p.save()
                    p.setClipRect(QRect(cell.x(), cell.y(), 6, 12))
                    p.drawImage(cell, icons.status_image(stat))
                    p.restore()
                else:
                    p.drawImage(cell, icons.status_image(stat, dim=True))
            y += 15

    def _draw_bubble(self, p: QPainter, bottom: float) -> None:
        text = self.bubble_text
        fm = QFontMetrics(self.font_bubble)
        lo, hi = self._visible_x_range()
        max_w = max(120, min(BUBBLE_MAX_W, hi - lo - 4))   # perto da borda da tela, o balão fica mais estreito
        br = fm.boundingRect(QRect(0, 0, max_w - 22, 1000), Qt.TextWordWrap, text)
        bw, bh = br.width() + 22, br.height() + 14
        with_button = self.sticky is not None and text == self.sticky[0]
        if with_button:
            bw = max(bw, 92)
            bh += 24
        x = int(max(lo + 2, min(hi - bw - 2, (WIDTH - bw) / 2)))
        y = int(bottom - bh - 8)
        black, white = QColor("#111111"), QColor("#FFFFFF")
        p.fillRect(QRect(x + 2, y, bw - 4, bh), black)
        p.fillRect(QRect(x, y + 2, bw, bh - 4), black)
        p.fillRect(QRect(x + 4, y + 2, bw - 8, bh - 4), white)
        p.fillRect(QRect(x + 2, y + 4, bw - 4, bh - 8), white)
        # rabinho em escadinha apontando pro creeper
        tx = int(WIDTH / 2)
        for i, w in enumerate((14, 10, 6)):
            p.fillRect(QRect(tx - w // 2, y + bh - 2 + i * 3, w, 3), black)
            if w > 6:
                p.fillRect(QRect(tx - w // 2 + 2, y + bh - 2 + i * 3, w - 4, 3 if i == 0 else 2), white)
        p.setFont(self.font_bubble)
        p.setPen(black)
        p.drawText(QRect(x + 11, y + 7, br.width(), br.height()), Qt.TextWordWrap, text)
        self.bubble_btn = None
        if with_button:
            btn = QRect(x + bw - 11 - 60, y + bh - 28, 60, 20)
            self.bubble_btn = btn
            p.fillRect(btn.adjusted(-1, -1, 1, 1), black)
            self._bevel(p, btn, QColor("#7FB04A"), QColor("#B5E07A"), QColor("#3E6B1E"))
            p.setFont(self.font_title)
            p.setPen(QColor("#1E3A0C"))
            label = STICKY_BUTTONS.get(self.sticky[1], "Fiz!")
            p.drawText(btn.translated(1, 1), Qt.AlignCenter, label)
            p.setPen(white)
            p.drawText(btn, Qt.AlignCenter, label)

    # ---- mouse -----------------------------------------------------------
    def _button_at(self, pos: QPoint) -> str | None:
        if not self.toolbar_visible():
            return None
        for bid, rect in self.button_rects():
            if rect.contains(pos):
                return bid
        return None

    def _on_sprite(self, pos: QPoint) -> bool:
        return not self.pet.hidden and self.sprite_rect().contains(QPointF(pos))

    def mousePressEvent(self, e) -> None:
        pos = e.position().toPoint()
        gpos = e.globalPosition().toPoint()
        if e.button() == Qt.LeftButton:
            if self.bubble_text and self.bubble_btn and self.bubble_btn.contains(pos):
                self.app.bubble_action(self.sticky[1] if self.sticky else None)
                return
            gift = self.gift_rect()
            if gift and gift.adjusted(-3, -3, 3, 3).contains(pos):
                self.app.open_present()
                return
            bid = self._button_at(pos)
            if bid:
                self.app.on_toolbar(bid)
                return
            if self._on_sprite(pos):
                self.press = (gpos, time.monotonic())
                self.drag_offset = QPointF(self.pet.x - gpos.x(), self.pet.y - gpos.y())
            elif self.bubble_text:
                self.bubble_text = None
                self.sticky = None   # dispensou o lembrete (o "Fiz!" continua no menu por um tempo)
        elif e.button() == Qt.RightButton:
            self.app.show_context_menu()

    def mouseMoveEvent(self, e) -> None:
        gpos = e.globalPosition().toPoint()
        if self.press and e.buttons() & Qt.LeftButton:
            if not self.dragging and (gpos - self.press[0]).manhattanLength() > 6:
                self.dragging = self.pet.start_drag()
                if not self.dragging:
                    self.press = None
                    return
                self.hover_since = None
            if self.dragging:
                self.pet.drag_to(gpos.x() + self.drag_offset.x(), gpos.y() + self.drag_offset.y())
                self.sync_position()
            return
        pos = e.position().toPoint()
        bid = self._button_at(pos)
        if bid != self.hover_btn:
            self.hover_btn = bid
            if bid:
                label = dict(BUTTONS)[bid]
                if bid == "dormir" and self.pet.state == "sleep":
                    label = "Acordar"
                QToolTip.showText(gpos, label, self)
            else:
                QToolTip.hideText()
        if self._on_sprite(pos):
            self._track_stroke(gpos.x())

    def _track_stroke(self, x: int) -> None:
        if self.stroke_x is None:
            self.stroke_x = x
            return
        dx = x - self.stroke_x
        if abs(dx) < 4:
            return
        d = 1 if dx > 0 else -1
        now = time.monotonic()
        if self.stroke_dir and d != self.stroke_dir:
            self.stroke_times.append(now)
        self.stroke_dir = d
        self.stroke_x = x
        self.stroke_times = [t for t in self.stroke_times if now - t < 1.5]
        if len(self.stroke_times) >= 2:
            self.pet.stroke()
            self.stroke_times = self.stroke_times[-1:]

    def mouseReleaseEvent(self, e) -> None:
        if e.button() != Qt.LeftButton:
            return
        if self.dragging:
            self.dragging = False
            self.pet.end_drag()
        elif self.press and time.monotonic() - self.press[1] < 0.5:
            self.pet.poke()
        self.press = None

    def leaveEvent(self, e) -> None:
        self.stroke_x = None
        self.stroke_dir = 0
        super().leaveEvent(e)
