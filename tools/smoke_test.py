"""Teste automático sem tela: passa por todos os estados e confere que nada quebra.

Uso:  python tools/smoke_test.py [pasta_para_fotos]
Se passar uma pasta, salva "fotos" da janela em cada estado.
"""
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

TMP = tempfile.mkdtemp(prefix="creeper-test-")
os.environ["APPDATA"] = TMP
os.environ["XDG_CONFIG_HOME"] = TMP
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
if sys.platform == "win32":
    os.environ.setdefault("QT_QPA_FONTDIR", r"C:\Windows\Fonts")

from PySide6.QtWidgets import QApplication  # noqa: E402

qapp = QApplication(sys.argv)
from creeper.app import CompanionApp  # noqa: E402

SHOTS = Path(sys.argv[1]) if len(sys.argv) > 1 else None
app = CompanionApp(qapp)
for timer in app._timers:
    timer.stop()
pet, win = app.pet, app.window
said: list[tuple[str, str]] = []
pet.say = lambda text, kind="chat": (said.append((kind, text)), app.on_say(text, kind))
win.show()


def run(seconds: float, dt: float = 0.033) -> None:
    for _ in range(int(seconds / dt)):
        pet.update(dt)
        win.frame()


def shot(name: str) -> None:
    if SHOTS:
        import time
        SHOTS.mkdir(parents=True, exist_ok=True)
        win.hover_since = time.monotonic() - 5
        win.repaint()
        win.grab().save(str(SHOTS / f"{name}.png"))


def check(cond: bool, msg: str) -> None:
    print(("ok   " if cond else "FAIL ") + msg)
    if not cond:
        check.failed = True


check.failed = False

app.greet()
run(1)
shot("parado")
check(bool(said) and "Creepinho" in said[0][1], "saudação de primeira vez")

pet.needs.values["fome"] = 40
pet.feed("bolo")
run(0.5)
shot("comendo")
run(3)
check(pet.needs["fome"] > 55 and pet.state == "idle", "comer aumenta a saciedade")

pet.needs.values["fome"] = 98
pet.feed("bolo")
run(0.2)
check(pet.state != "eat", "recusa comida quando está cheio")

pet.needs.values["sede"] = 50
pet.feed("cafe")
run(3)
check(pet.needs.has("cafeinado"), "café deixa cafeinado")
pet.needs.values["sede"] = 50
pet.feed("leite")
run(3)
check(not pet.needs.has("cafeinado"), "leite cura")

for act in ("caminhar", "correr", "pular", "flexao", "dancar", "descansar", "gato"):
    pet.needs.values["energia"] = 90
    pet.do_activity(act)
    run(1.0)
    shot(f"atividade_{act}")
    run(75)
    check(pet.state != "exercise" and not pet.hidden, f"atividade '{act}' termina")

pet.needs.values["energia"] = 5
pet.do_activity("correr")
run(0.1)
check(pet.state != "exercise", "recusa exercício quando exausto")
pet.needs.values["energia"] = 80

pet.needs.values["sono"] = 30
pet.request_sleep()
run(2)
shot("dormindo")
check(pet.state == "sleep", "dorme")
pet.wake(forced=True)
run(0.5)
check(pet.state == "idle", "acorda")

pet.needs.annoyance = 0
for _ in range(15):
    if pet.state == "hiss":
        break
    pet.poke()
    run(0.3)
check(pet.state == "hiss", "cutucar demais faz chiar")
shot("chiando")
run(3)
check(pet.state == "exploded" or pet.hidden, "explode")
run(8)
check(pet.state == "idle" and pet.needs.sulking(), "volta emburrado")
shot("emburrado")

for _ in range(30):
    pet.stroke()
    run(0.3)
check(not pet.needs.sulking(), "carinho desemburra")

pet.start_drag()
for i in range(40):
    pet.drag_to(pet.x + (60 if i % 2 else -60), pet.y - (200 if i == 0 else 0))
    run(0.03)
shot("arrastado")
pet.end_drag()
run(3)
check(pet.state not in ("dragged", "fall") and abs(pet.y - pet.world[3]) < 1, "cai de volta no chão")

if app.has_tray:
    app.hide_to_tray()
    check(app.in_tray, "vai pra bandeja")
    app.show_from_tray()
    check(not app.in_tray, "volta da bandeja")
else:
    app.hide_to_tray()
    check(not app.in_tray, "sem bandeja no sistema: continua na tela")

app.save()
check((Path(TMP) / "CreeperCompanion" / "save.json").exists()
      or (Path(TMP) / "creeper-companion" / "save.json").exists(), "salva o estado")

print("\n--- falas ---")
for kind, text in said:
    print(f"[{kind}] {text}")
sys.exit(1 if check.failed else 0)
