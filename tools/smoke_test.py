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
os.environ["CREEPER_SEM_SOM"] = "1"  # registra os sons pedidos, mas não toca nada
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
sounds: list[str] = []
app.play_sound = lambda name, volume=1.0: sounds.append(name)
pet.sfx = app.play_sound
achieved: list[str] = []
pet.on_achievement = lambda ach: (achieved.append(ach["id"]), app.on_achievement(ach))
prog = app.progress
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
pet.needs.values["sede"] = 50
pet.feed("pocao_velocidade")
run(3)
check(pet.needs.has("velocidade"), "poção deixa veloz")

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
check(not pet.hidden and pet.state not in ("exploded", "fall") and pet.needs.sulking(),
      "volta emburrado")  # já pode ter decidido andar ou sentar
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

import creeper.app  # noqa: E402
creeper.app.desktop.user_idle_seconds = lambda: 0.0
app.last_water -= app.settings.water_minutes * 60
app.care_tick()
check(said[-1][0] == "reminder" and sounds[-1] == "lembrete", "lembrete de água com som")

# ---- progresso: XP, níveis, presentes, estoque, conquistas ------------------
from PySide6.QtWidgets import QMenu  # noqa: E402
from creeper.ui import menus  # noqa: E402

check(app.pending_care() == "agua" and win.sticky_active(), "lembrete de água vem com o botão Fiz!")
win.show_bubble("Ai!", 5)
win.bubble_until = 0
win.frame()
check(win.bubble_text == win.sticky[0], "lembrete volta depois de outra fala")
shot("lembrete_fiz")
win.grab()
check(win.bubble_btn is not None, "botão Fiz! desenhado no balão")
xp0 = prog.total_xp
app.confirm_care()
run(0.3)
check(prog.total_xp >= xp0 + 15 and prog.counters.get("agua_feita") == 1 and not win.sticky_active()
      and app.pending_care() is None, "apertar Fiz! dá XP e fecha o lembrete")

check("primeira_mordida" in achieved and "primeira_mordida" in prog.done, "conquista ao dar a primeira comida")
check("inimigo_natural" in achieved and "tsss_bum" in achieved, "conquistas de gato e explosão")
check(app.toast.current is not None, "aviso de conquista aparece")
if SHOTS:
    app.toast.grab().save(str(SHOTS / "conquista.png"))

budget = prog.care_budget
prog.care_budget = 0
check(prog.care("comer") == 0, "cuidar tem limite de XP por hora")
prog.care_budget = budget

level0, presents0, said0 = prog.level, prog.presents, len(said)
prog.add_xp(prog.needed - prog.xp + 1)
run(0.5)
check(prog.level == level0 + 1 and prog.presents == presents0 + 1, "subir de nível traz presente")
check(any(kind == "reaction" and str(prog.level) in text for kind, text in said[said0:]) and "nivel" in sounds,
      "comemora o nível novo")
shot("presente")
check(win.gift_rect() is not None, "presente aparece do lado dele")
inventory0, xp0, n0 = dict(prog.inventory), prog.total_xp, prog.presents
app.open_present()
run(0.3)
check(prog.presents == n0 - 1 and (prog.inventory != inventory0 or prog.total_xp > xp0), "abrir presente dá item ou XP")

pet.needs.values["fome"] = 30
prog.inventory["maca_dourada"] = 0
pet.feed("maca_dourada")
run(0.2)
check(pet.state != "eat", "sem estoque, não come")
main_menu = QMenu()
menus.fill_main(app, main_menu)
food_menu = next(a.menu() for a in main_menu.actions() if a.text() == "Comer")
apple_action = next(a for a in food_menu.actions() if a.text().startswith("Maçã dourada"))
check(apple_action.text().endswith("×0") and not apple_action.isEnabled(), "menu mostra estoque zerado")
check(any(a.text().startswith(f"Conquistas ({len(prog.done)}/") for a in main_menu.actions()),
      "menu de conquistas")
prog.inventory["maca_dourada"] = 1
pet.feed("maca_dourada")
run(0.2)
check(pet.state == "eat" and prog.inventory["maca_dourada"] == 0, "come e gasta do estoque")
run(3)

pet.needs.values["fome"] = 5
prog.xp = 50.0
prog.tick(60, True, pet.needs)
run(0.1)
check(prog.losing and prog.xp < 50, "descuido tira XP")
level0 = prog.level
prog.xp = 1.0
prog.tick(3600, False, pet.needs)
check(prog.level == level0 and prog.xp == 0, "descuido nunca rebaixa de nível")
pet.needs.values["fome"] = 80

import json  # noqa: E402
from creeper.progress import Progress  # noqa: E402
again = Progress.from_dict(json.loads(json.dumps(prog.to_dict())), app.items, app.achievements)
check((again.level, again.inventory, set(again.done), again.counters) ==
      (prog.level, prog.inventory, set(prog.done), prog.counters), "progresso salva e carrega igual")
fresh = Progress.from_dict(None, app.items, app.achievements)
check(fresh.level == 1 and fresh.inventory == {"maca_dourada": 1, "pocao_velocidade": 2},
      "save antigo começa no nível 1 com o estoque inicial")

for name in ("pop", "mastigar", "gole", "brilho", "pulo", "miau", "cutucao", "chiado", "explosao", "pouso",
             "carinho", "tonto", "xp", "nivel", "conquista"):
    check(name in sounds, f"som '{name}' tocou")
check(any(n.startswith("nota_") for n in sounds), "dançar toca notas")

from creeper.sound import synth  # noqa: E402

main_menu = QMenu()
menus.fill_main(app, main_menu)
settings_menu = next(a.menu() for a in main_menu.actions() if a.text() == "Configurações")
check(any(a.text() == "Sons" for a in settings_menu.actions()), "menu de sons nas configurações")
app.set_setting("sound_volume", 30)
check(app.settings.sound_volume == 30 and sounds[-1] == "pop", "mudar volume toca amostra")

bad = []
for name in synth.SOUNDS:
    x = synth.samples(name)
    peak = max(abs(v) for v in x)
    if not (0.05 < peak <= 0.96 and abs(x[0]) < 0.01 and abs(x[-1]) < 0.01 and len(x) < 3 * synth.SR):
        bad.append(name)
check(not bad, f"{len(synth.SOUNDS)} sons gerados sem estourar nem estalar" + (f": {bad}" if bad else ""))

app.save()
check((Path(TMP) / "CreeperCompanion" / "save.json").exists()
      or (Path(TMP) / "creeper-companion" / "save.json").exists(), "salva o estado")

print("\n--- falas ---")
for kind, text in said:
    print(f"[{kind}] {text}")
sys.exit(1 if check.failed else 0)
