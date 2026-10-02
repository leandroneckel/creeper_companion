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
        if app.ball.active:
            app.ball.update(dt)
        app.ball_window.sync(win.isVisible())


def shot(name: str, hover: bool = True) -> None:
    if SHOTS:
        import time
        SHOTS.mkdir(parents=True, exist_ok=True)
        win.hover_since = time.monotonic() - 5 if hover else None
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
check(fresh.level == 1 and fresh.inventory == {i["id"]: i["limitado"]["inicial"] for i in app.items.limited()},
      "save antigo começa no nível 1 com o estoque inicial")

# ---- itens e atividades desbloqueáveis ---------------------------------------
import time  # noqa: E402

prog.level = 1
pet.set_state("idle", dur=999)
pet.feed("baga_doce")
pet.do_activity("minerar")
run(0.1)
check(pet.state == "idle", "item trancado não pode ser usado no nível 1")
main_menu = QMenu()
menus.fill_main(app, main_menu)
food_menu = next(a.menu() for a in main_menu.actions() if a.text() == "Comer")
check(any(a.text() == "??? (nível 2)" and not a.isEnabled() for a in food_menu.actions()), "menu mostra item trancado")

prog.level = 30   # libera tudo pra testar
for food in ("baga_doce", "melancia", "peixe", "sopa_beterraba", "cenoura_dourada", "mel"):
    pet.needs.values.update(fome=40, sede=40)
    pet.set_state("idle", dur=999)
    pet.feed(food)
    run(3.2)
    check(pet.state != "eat" and pet.state != "drink" and pet.held is None, f"come/bebe '{food}'")


def drink(potion: str) -> None:
    pet.needs.values["sede"] = 40
    pet.set_state("idle", dur=999)
    pet.feed(potion)
    run(2.6)


stock = prog.inventory["pocao_salto"]
drink("pocao_salto")
check(prog.inventory["pocao_salto"] == stock - 1 and pet.needs.has("salto"), "poção de salto gasta do estoque")
highest = 0.0
for _ in range(400):
    run(0.033)
    highest = max(highest, pet.jump)
    if pet.jump > pet.sprite_h * 0.8:
        shot("salto", hover=False)
check(highest > pet.sprite_h * 0.8, "poção de salto: pulos altíssimos")
pet.needs.effects.pop("salto", None)
run(1)

drink("pocao_encolher")
run(2)
check(abs(pet.size - 0.5) < 0.02, "poção de encolher deixa ele pequeno")
shot("encolhido")
pet.needs.effects["encolhido"] = time.time() - 1
run(2)
check(pet.size == 1.0 and "cresce" in sounds, "volta ao tamanho normal quando o efeito acaba")

drink("pocao_invisibilidade")
check(pet.ghost, "poção de invisibilidade")
shot("invisivel")
pet.needs.effects.pop("invisivel", None)

pet.needs.sulk(600)
drink("pocao_cura")
check(not pet.needs.sulking(), "poção de cura tira o emburrado")

seen_props: dict[str, set] = {}
for act in ("minerar", "pescar", "plantar", "porco", "fogos"):
    pet.needs.values["energia"] = 90
    pet.set_state("idle", dur=999)
    pet.do_activity(act)
    kinds = seen_props.setdefault(act, set())
    for step in range(int(32 / 0.033)):
        pet.update(0.033)
        win.frame()
        kinds.update(f"{p.kind}:{p.name}" for p in pet.props)
        if step == int(7 / 0.033):
            shot(f"atividade_{act}", hover=False)
        if pet.state != "exercise":
            break
    check(pet.state != "exercise" and not pet.props and pet.tool is None and pet.jump == 0,
          f"atividade '{act}' termina e limpa a cena")
check(any(k.startswith("icon:bloco_") for k in seen_props["minerar"]) and prog.counters.get("blocos", 0) >= 1,
      "minerar quebra blocos")
check({"water:", "line:"} <= seen_props["pescar"] and "splash" in sounds, "pescar com poça, linha e boia")
check("icon:flor" in seen_props["plantar"] and "cavar" in sounds, "plantar cava e a flor cresce")
check(any(k.startswith("big:porco") for k in seen_props["porco"]) and "cavaleiro_suino" in prog.done,
      "porco aparece e dá conquista")
check("estouro" in sounds and "foguete" in sounds, "fogos sobem e estouram")

# ---- guarda-roupa ---------------------------------------------------------------
from creeper import cosmetics  # noqa: E402

pet.set_state("idle", dur=999)
prog.level, prog.xp, said0 = 4, 0.0, len(said)
prog.add_xp(prog.needed + 1)
run(0.3)
check(app.settings.hat == "abobora" and any(k == "reaction" and "5" in t for k, t in said[said0:]),
      "nível 5 desbloqueia e já veste a abóbora")
main_menu = QMenu()
menus.fill_main(app, main_menu)
wardrobe = next(a.menu() for a in main_menu.actions() if a.text() == "Guarda-roupa")
hats_menu = next(a.menu() for a in wardrobe.actions() if a.text() == "Chapéu")
hat_texts = {a.text(): a.isEnabled() for a in hats_menu.actions()}
check(hat_texts.get("Abóbora esculpida") is True and hat_texts.get("??? (nível 12)") is False,
      "guarda-roupa mostra o que tem e o que falta")

prog.level = 30
looks = [("abobora", "neve", "folhas"), ("cartola", "outono", "faiscas"), ("coroa", "noturno", "coracoes"),
         ("capacete", "", "")]
for hat, skin, trail in looks:
    app.set_outfit("chapeu", hat)
    app.set_outfit("cor", skin)
    app.set_outfit("rastro", trail)
    pet.set_state("walk", target=pet.x + (150 if pet.x < pet.world[2] / 2 else -150))
    run(1.0)
    check(pet.pose().skin == (skin or None) and app.settings.hat == hat, f"veste {hat}/{skin or 'verde'}")
    if trail:
        check(any(p.kind in ("crumb", "spark", "heart") for p in pet.particles), f"rastro de {trail} ao andar")
    shot(f"visual_{hat}", hover=False)
pet.set_state("idle", dur=999)
app.set_outfit("carregado", True)
run(0.1)
check(app.settings.charged and any(p.kind == "bolt" for p in pet.particles) and "trovao" in sounds,
      "creeper carregado chega com raio e trovão")
shot("carregado_raio", hover=False)
run(1)
shot("carregado", hover=False)

# ---- comportamentos e brincadeiras ----------------------------------------------
prog.level = 1
main_menu = QMenu()
menus.fill_main(app, main_menu)
play_menu = next(a.menu() for a in main_menu.actions() if a.text() == "Brincadeiras")
check(all(not a.isEnabled() for a in play_menu.actions()), "brincadeiras trancadas no nível 1")
app.call_pet()
check(pet.state != "come", "não vem quando chamado antes de aprender")

prog.level = 30
for kind, value in (("carregado", False), ("chapeu", ""), ("rastro", ""), ("cor", "")):
    app.set_outfit(kind, value)
pet.needs.effects.clear()
pet.needs.values.update(fome=90, sede=90, energia=90, sono=90, diversao=90)
pet.needs.sulk_until = 0
pet.set_state("idle", dur=999)
run(0.5)
left, top, right, ground = pet.world
middle = (left + right) / 2

said0 = len(said)
pet.call(pet.x + 250 if pet.x < middle else pet.x - 250)
target = pet._clamp_x(pet.data["target"])
run(4)
check(pet.state == "idle" and abs(pet.x - target) < 2 and len(said) >= said0 + 2, "vem correndo quando chamado")

plat = (ground - 220.0, pet.x - 200, pet.x + 200)
pet.platforms = [plat]
spot = pet._climb_spot()
check(spot is not None, "acha uma janela pra subir")
pet.leap_to(*spot)
run(1.5)
check(pet.perch == plat and abs(pet.y - plat[0]) < 1, "pula e fica em cima da janela")
shot("em_cima_da_janela", hover=False)
pet.platforms = []          # a janela fechou
run(1.5)
check(pet.perch is None and abs(pet.y - ground) < 1, "cai quando a janela some")
pet.platforms = [plat]
pet.start_drag()
pet.drag_to(pet.x, plat[0] - 150)
pet.end_drag()
run(1.5)
check(pet.perch == plat, "solto em cima de uma janela, pousa nela")
pet.platforms = []
run(1.5)

app.ball.world = pet.world
app.toggle_ball()
run(0.5)
check(app.ball.active and pet.state == "fetch", "bolinha em jogo")
fetched = prog.counters.get("bolinha", 0)
app.ball.held = "user"
app.ball.x, app.ball.y = pet.x, pet.y - 80
app.ball.throw(900 if pet.x < middle else -900, -700)
app.on_ball_thrown()
carried = False
for _ in range(int(20 / 0.033)):
    run(0.033)
    if pet.held == "bola" and not carried:
        carried = True
        shot("bolinha_na_boca", hover=False)
    if prog.counters.get("bolinha", 0) > fetched:
        break
check(carried and prog.counters.get("bolinha", 0) == fetched + 1, "busca a bolinha e traz de volta")
check("quique" in sounds, "bolinha quica")
app.toggle_ball()
run(0.3)
check(not app.ball.active and pet.state != "fetch" and not app.ball_window.isVisible(), "guarda a bolinha")

from PySide6.QtCore import QPoint, Qt  # noqa: E402
from PySide6.QtTest import QTest  # noqa: E402

app.toggle_ball()
run(0.5)
bw = app.ball_window
center = QPoint(bw.width() // 2, bw.height() // 2)
QTest.mousePress(bw, Qt.LeftButton, Qt.NoModifier, center)
for step in range(1, 6):
    QTest.mouseMove(bw, center + QPoint(step * 12, -step * 6))
QTest.mouseRelease(bw, Qt.LeftButton, Qt.NoModifier, center + QPoint(72, -36))
check(app.ball.held == "none" and abs(app.ball.vx) > 100 and pet.data.get("phase") == "go",
      "agarrar e arremessar a bolinha com o mouse")
app.toggle_ball()
run(0.3)

app.start_hide()
run(3)
check(pet.state == "hide" and pet.data["phase"] == "escondido" and pet.occluder is not None, "se esconde")
pet.data["giggle"] = pet.t   # a risadinha (dica de onde ele está) viria em 10-18 s
run(0.1)
found0 = prog.counters.get("esconde", 0)
pet.poke()
run(0.5)
check(pet.state != "hide" and pet.occluder is None and prog.counters.get("esconde", 0) == found0 + 1
      and abs(pet.y - pet.world[3]) < 1, "clicar nele = achou")
said0 = len(said)
app.start_hide()
run(3)
pet.data["until"] = pet.t
run(0.2)
check(pet.state != "hide" and len(said) > said0 + 1, "se não achar a tempo, ele ganha")
window_rect = (left + 300.0, ground - 400.0, left + 700.0, ground)
spots = [pet._hide_spot([window_rect]) for _ in range(40)]
check(any(s["occluder"] == window_rect for s in spots), "se esconde atrás de uma janela")
for name, spot in (("tela", spots[0] if spots[0]["peek"] else None), ("chao", None), ("janela", None)):
    pick = {"tela": lambda s: s["peek"] and s["occluder"] != window_rect, "chao": lambda s: not s["peek"],
            "janela": lambda s: s["occluder"] == window_rect}[name]
    spot = next((s for s in spots if pick(s)), None)
    if spot:
        pet.set_state("hide", phase="escondido", base_x=spot["x"], base_y=spot["y"], peek=spot["peek"],
                      until=pet.t + 99, giggle=pet.t + 99, world=pet.world, windows=[])
        pet.x, pet.y, pet.facing, pet.occluder = spot["x"], spot["y"], spot["facing"], spot["occluder"]
        win.frame()
        shot(f"escondido_{name}", hover=False)
pet._end_hide(found=True)
run(0.5)

prog.presents = 0   # com presente esperando ele fica parado esperando você abrir
budget = prog.care_budget
for _ in range(300):
    pet.set_state("idle", dur=0)
    pet.last_solo = -1e9
    pet.decide()
    if pet.state == "exercise" and pet.data.get("solo"):
        break
check(pet.state == "exercise" and pet.data.get("solo"), "brinca sozinho quando está feliz")
run(30)
check(pet.state != "exercise" and prog.care_budget == budget, "brincar sozinho não dá XP de cuidado")

# ---- mouse em cima: ele para, e o menu abre do lado ------------------------------
pet.set_state("walk", target=pet.x + (200 if pet.x < middle else -200))
win.hover_since = time.monotonic()
run(0.1)
check(pet.state == "idle", "para de andar quando o mouse chega nele")
pet.set_state("come", target=pet.x + 300)
win.hover_since = time.monotonic() - 5
check(not win.toolbar_visible(), "sem painel enquanto ele corre pela tela")
pet.set_state("idle", dur=999)
win.hover_since = time.monotonic() - 5
win.frame()
app.show_context_menu()
popup = app._popup
check(popup.isVisible() and win.status_visible() and not popup.geometry().intersects(win.ui_rect()),
      "menu abre do lado, sem cobrir o painel")
if SHOTS:
    from PySide6.QtGui import QColor, QImage, QPainter  # noqa: E402
    area = win.ui_rect().united(popup.geometry()).adjusted(-10, -10, 10, 10)
    sheet = QImage(area.size(), QImage.Format_ARGB32)
    sheet.fill(QColor("#5B8FC7"))
    painter = QPainter(sheet)
    painter.drawImage(win.pos() - area.topLeft(), win.grab().toImage())
    painter.drawImage(popup.pos() - area.topLeft(), popup.grab().toImage())
    painter.end()
    sheet.save(str(SHOTS / "menu_do_lado.png"))
popup.hide()

for name in ("pop", "mastigar", "gole", "brilho", "pulo", "miau", "cutucao", "chiado", "explosao", "pouso",
             "carinho", "tonto", "xp", "nivel", "conquista", "picareta", "quebra", "oinc", "encolhe", "trovao",
             "quique", "risadinha", "poof"):
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
