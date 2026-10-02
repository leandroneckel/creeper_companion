"""Gera a imagem do README (docs/creeper-companion.png) renderizando a janela sem tela.

Uso:  python tools/readme_image.py
"""
import os
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

TMP = tempfile.mkdtemp(prefix="creeper-img-")
os.environ["APPDATA"] = TMP
os.environ["XDG_CONFIG_HOME"] = TMP
os.environ["QT_QPA_PLATFORM"] = "offscreen"
os.environ["CREEPER_SEM_SOM"] = "1"
os.environ.setdefault("QT_SCALE_FACTOR", "2")
if sys.platform == "win32":
    os.environ.setdefault("QT_QPA_FONTDIR", r"C:\Windows\Fonts")

from PySide6.QtCore import QRectF, Qt  # noqa: E402
from PySide6.QtGui import QColor, QImage, QLinearGradient, QPainter  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

qapp = QApplication(sys.argv)
if sys.platform == "win32":
    from PySide6.QtGui import QFont
    qapp.setFont(QFont("Segoe UI", 9))  # a fonte que o app usa de verdade no Windows
from creeper.app import CompanionApp  # noqa: E402

OUT = ROOT / "docs" / "creeper-companion.png"
SPACING = 250
TASKBAR = 34

app = CompanionApp(qapp)
for timer in app._timers:
    timer.stop()
pet, win = app.pet, app.window
pet.say = lambda text, kind="chat": None
win.update_hover = lambda: None
win.show()


def run(seconds: float, dt: float = 0.033) -> None:
    for _ in range(int(seconds / dt)):
        pet.update(dt)
        win.frame()


def reset(**needs) -> None:
    pet.set_state("idle", dur=999)
    pet.particles.clear()
    pet.jump = pet.squash = pet.swell = pet.flash = pet.tilt = 0
    pet.held = None
    pet.hidden = False
    pet.happy_until = pet.flinch_until = pet.dizzy_until = 0
    pet.needs.effects.clear()
    pet.needs.annoyance = 0
    pet.needs.sulk_until = 0
    pet.needs.values.update({"fome": 80, "sede": 80, "energia": 85, "sono": 80, "diversao": 85, **needs})
    pet.cursor = None
    win.hover_since = None
    win.bubble_text = None


def grab(bubble: str | None = None, hover: bool = False) -> QImage:
    pet.next_blink = pet.clock + 999
    pet.blink_until = 0
    win.hover_since = time.monotonic() - 5 if hover else None
    if bubble:
        win.show_bubble(bubble, 999)
    win._last_sig = None
    win.repaint()
    return win.grab().toImage()


scenes = []

# 1. passando o mouse: barra de botões, status (com nível) e um presente esperando
reset(fome=55, sede=70, energia=85, sono=62, diversao=92)
app.progress.level = 7
app.progress.xp = app.progress.needed * 0.6
app.progress.presents = 1
pet.cursor = (pet.x + 300, pet.y - 600)
run(0.3)
scenes.append(grab("Oi! Eu sou o Creepinho. Passa o mouse em mim pra ver do que eu preciso.", hover=True))
app.progress.presents = 0

# 2. comendo bolo
reset(fome=55)
pet.feed("bolo")
run(0.55)
scenes.append(grab("BOLO! É meu aniversário?!"))

# 3. dançando
reset()
pet.do_activity("dancar")
run(2.0)
while pet.jump < 5 * pet.s / 3:
    run(0.033)
scenes.append(grab("Danço melhor que o Steve. Não é difícil."))

# 4. chiando antes de explodir
reset()
pet.needs.annoyance = 100
pet.start_hiss()
run(1.6)
while pet.flash < 0.55:
    run(0.033)
scenes.append(grab("Tssssssss..."))

# 5. dormindo
reset(sono=40)
pet.start_sleep()
run(4.5)
scenes.append(grab("...mais cinco minutinhos..."))

def first_opaque_row(image: QImage) -> int:
    image = image.convertToFormat(QImage.Format_ARGB32)
    data = bytes(image.constBits())
    bpl, w = image.bytesPerLine(), image.width()
    for y in range(image.height()):
        if any(data[y * bpl + 3: y * bpl + w * 4: 4]):
            return y
    return image.height()


dpr = scenes[0].devicePixelRatio()
w0 = scenes[0].width() / dpr
h0 = scenes[0].height() / dpr
crop_top = max(0, min(first_opaque_row(s) for s in scenes) / dpr - 18)
width = int(SPACING * (len(scenes) - 1) + w0)
height = int(h0 - crop_top + TASKBAR)

img = QImage(int(width * dpr), int(height * dpr), QImage.Format_ARGB32)
img.setDevicePixelRatio(dpr)
p = QPainter(img)
sky = QLinearGradient(0, 0, 0, height)
sky.setColorAt(0, QColor("#5FA8E8"))
sky.setColorAt(1, QColor("#BFE3FF"))
p.fillRect(QRectF(0, 0, width, height), sky)
p.fillRect(QRectF(0, height - TASKBAR, width, TASKBAR), QColor("#1E1F29"))
p.fillRect(QRectF(0, height - TASKBAR, width, 1), QColor("#3A3C4E"))
for i, scene in enumerate(scenes):
    x = i * SPACING
    y = -crop_top
    p.drawImage(QRectF(x, y, w0, h0), scene)
p.end()

OUT.parent.mkdir(parents=True, exist_ok=True)
img.save(str(OUT))
print("salvo em", OUT, f"({img.width()}x{img.height()})")
