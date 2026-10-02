"""Comportamento do creeper: estados, reações, falas e partículas.

Não sabe nada de janela: trabalha em coordenadas globais da tela.
(x, y) é o ponto entre os pés do creeper.
"""
import math
import random
import time
from collections import deque
from dataclasses import dataclass
from datetime import datetime

from . import cosmetics
from .art.sprite import Pose
from .needs import Needs
from .progress import Progress

CHAT_COOLDOWN = {"pouco": 360, "normal": 160, "muito": 75}
CHAT_CHANCE = {"pouco": 0.25, "normal": 0.4, "muito": 0.6}

NEED_LINES = {
    "fome": ("fome", "fome_critica"),
    "sede": ("sede", "sede_critica"),
    "energia": ("cansado", "cansado_critico"),
    "sono": ("sono", "sono_critico"),
    "diversao": ("tedio", "tedio_critico"),
}

# Estados em que ele não aceita comida/atividades
BUSY = {"eat", "drink", "exercise", "hiss", "exploded", "dragged", "fall", "leap", "come", "fetch", "hide"}
NO_INTERACTION = {"hiss", "exploded", "dragged", "fall", "leap", "hide"}
# Estados em que ele não fica preso ao chão (ou à janela onde está)
AIRBORNE = {"dragged", "fall", "exploded", "leap", "hide"}
# O que ele faz quando brinca sozinho (se já estiver desbloqueado)
SOLO_ACTIVITIES = ("dancar", "pular", "correr", "minerar", "pescar", "plantar")
SOLO_COOLDOWN = 10 * 60
HIDE_SECONDS = 90

GRAVITY = 2200.0

MAGIC_EFFECTS = {"dourado", "velocidade", "salto", "invisivel"}   # brilham ao beber
POTION_SWIRL = {"salto": "#7CFC5A", "encolhido": "#B388FF", "invisivel": "#C9CCD6"}
SHRUNK = 0.5          # tamanho com a poção de encolher
HOP_TIME = 0.75       # duração de um pulo da poção de salto
ACTIVITY_COUNTERS = {"dancar": "dancou", "gato": "gato", "plantar": "plantou", "porco": "porco", "fogos": "fogos"}

# Minerar: bloco, o que cai, golpes pra quebrar, chance relativa
ORES = (
    ("bloco_pedra", None, 3, 50),
    ("bloco_carvao", "carvao", 3, 25),
    ("bloco_ferro", "ferro", 4, 18),
    ("bloco_diamante", "diamante", 5, 7),
)
# Pescar: o que vem no anzol e a chance relativa ("tesouro" = um item especial pro estoque)
CATCHES = (("peixe", 70), ("bota", 20), ("tesouro", 10))
FIREWORK_COLORS = ("#FF5252", "#FFD740", "#69F0AE", "#40C4FF", "#E040FB", "#FFAB40")


@dataclass
class Prop:
    """Coisa que aparece junto dele durante uma atividade (bloco, poça, linha de pesca, porco).

    Some sozinha quando o estado muda. Coordenadas relativas aos pés, como as partículas.
    """
    kind: str              # icon | big | water | line
    name: str = ""
    x: float = 0.0         # centro; y = base do desenho
    y: float = 0.0
    size: float = 12.0     # icon: lado em px; big: px por pixel do desenho; water: largura
    flip: bool = False
    crack: float = 0.0     # 0..1, rachaduras do bloco minerado
    x2: float = 0.0        # line: ponta (a boia)
    y2: float = 0.0


@dataclass
class Particle:
    kind: str
    x: float              # relativo aos pés do creeper; y negativo = pra cima
    y: float
    vx: float = 0.0
    vy: float = 0.0
    life: float = 1.0
    age: float = 0.0
    gravity: float = 0.0
    color: str = "#FFFFFF"
    size: float = 3.0
    text: str = ""
    points: tuple = ()     # raio: a linha em zigue-zague


class Pet:
    def __init__(self, settings, items, lines, needs: Needs, progress: Progress):
        self.settings = settings
        self.items = items
        self.lines = lines
        self.needs = needs
        self.progress = progress

        self.state = "idle"
        self.t = 0.0
        self.data: dict = {"dur": 2.0}

        self.x = 400.0
        self.y = 800.0
        self.vx = 0.0
        self.vy = 0.0
        self.jump = 0.0      # altura do pulo (px)
        self.squash = 0.0    # 0..1 achatado (pouso/cutucão)
        self.swell = 0.0     # inchaço antes de explodir
        self.flash = 0.0
        self.tilt = 0.0      # inclinação quando arrastado (graus)
        self.facing = 1
        self.world = (0, 0, 1920, 1040)  # left, top, right, ground
        self.cursor: tuple[float, float] | None = None

        self.clock = 0.0
        self.next_blink = 3.0
        self.blink_until = 0.0
        self.happy_until = 0.0
        self.flinch_until = 0.0
        self.dizzy_until = 0.0
        self.particles: list[Particle] = []
        self.props: list[Prop] = []
        self.held: str | None = None   # ícone do item que está comendo/bebendo
        self.tool: str | None = None   # ferramenta na mão (picareta, vara)
        self.tool_angle = 0.0          # graus; positivo = golpe pra frente
        self.hidden = False            # invisível (explodiu / fugiu do gato)
        self.size = 1.0                # encolhe com a poção
        self.size_target = 1.0
        self.hop: float | None = None  # tempo desde o início do pulo da poção de salto
        self._last_x = self.x
        self._trail_timer = 0.0
        self.platforms: list[tuple[float, float, float]] = []   # bordas de janelas: (y, x1, x2)
        self.perch: tuple[float, float, float] | None = None    # em cima de qual janela ele está
        self.occluder: tuple[float, float, float, float] | None = None   # esconde-esconde: o que o cobre
        self.ball = None                                        # a bolinha (ball.Ball), quando em jogo
        self.last_solo = -1e9

        now = time.monotonic()
        self.last_chat = now
        self.last_need: dict[str, float] = {}
        self.last_pet_line = -1e9
        self.last_pet_fun = -1e9
        self.last_poke = -1e9
        self.last_shake_line = -1e9
        self._need_check = 0.0
        self._fx_timer = 0.0
        self._drag_samples: deque = deque(maxlen=12)
        self._reversals: deque = deque(maxlen=12)

        # ligações com a interface
        self.say = lambda text, kind="chat": None
        self.sfx = lambda name, volume=1.0: None
        self.sfx_stop = lambda name: None
        self.on_achievement = lambda achievement: None

    # ---- utilidades ------------------------------------------------------
    @property
    def s(self) -> int:
        return self.settings.scale

    @property
    def sprite_w(self) -> float:
        return 16 * self.s * self.size

    @property
    def sprite_h(self) -> float:
        return 40 * self.s * self.size

    @property
    def ghost(self) -> bool:
        """Poção de invisibilidade: a janela desenha ele quase transparente."""
        return self.needs.has("invisivel")

    def tool_anchor(self) -> tuple[float, float]:
        """Centro da ferramenta (relativo aos pés): do lado pra onde ele olha, na altura do corpo."""
        return self.facing * self.sprite_w * 0.6, -self.sprite_h * 0.42 - self.jump

    def tool_size(self) -> float:
        return 8 * self.s * self.size

    def rod_tip(self) -> tuple[float, float]:
        x, y = self.tool_anchor()
        return x + self.facing * self.tool_size() * 0.42, y - self.tool_size() * 0.5

    def line(self, key: str, kind: str = "chat", **fmt) -> bool:
        text = self.lines.pick(key, nome=self.settings.name, **fmt)
        if not text:
            return False
        self.last_chat = time.monotonic()
        self.say(text, kind)
        return True

    def set_state(self, state: str, **data) -> None:
        self.state = state
        self.t = 0.0
        self.data = data
        self.props = []
        self.tool = None
        self.tool_angle = 0.0
        if self.hop is not None and state not in ("idle", "walk"):
            self.hop = None
            self.jump = 0.0

    def busy(self) -> bool:
        return self.state in BUSY

    def can_interact(self) -> bool:
        return self.state not in NO_INTERACTION and not self.hidden

    def walk_speed(self) -> float:
        speed = 16.0 * self.s
        if self.needs.has("velocidade"):
            speed *= 2.2
        if self.needs.has("cafeinado"):
            speed *= 1.3
        if self.needs["energia"] < 25:
            speed *= 0.7
        return speed

    def _margin(self) -> float:
        return self.sprite_w / 2 + 60

    def _clamp_x(self, x: float) -> float:
        left, _, right, _ = self.world
        m = self._margin()
        return max(left + m, min(right - m, x))

    def _roam_bounds(self) -> tuple[float, float]:
        """Até onde ele pode andar: a borda da janela onde está, ou a tela."""
        if self.perch:
            m = self.sprite_w / 2 + 6
            lo, hi = self.perch[1] + m, self.perch[2] - m
            return (lo, hi) if lo < hi else ((lo + hi) / 2, (lo + hi) / 2)
        left, _, right, _ = self.world
        return left + self._margin(), right - self._margin()

    def _roam_x(self, x: float) -> float:
        lo, hi = self._roam_bounds()
        return max(lo, min(hi, x))

    def _needs_activity(self) -> str:
        if self.state == "sleep":
            return "sleep"
        if self.state == "sit" or (self.state == "exercise" and self.data.get("kind") == "descansar"):
            return "sit"
        if self.state == "walk":
            return "walk"
        if self.state == "exercise":
            return "exercise"
        return "idle"

    # ---- ciclo principal -------------------------------------------------
    def update(self, dt: float) -> None:
        dt = min(dt, 0.25)
        self.clock += dt
        self.t += dt

        for effect in self.needs.tick(dt, self._needs_activity(), self.settings.needs_speed):
            self.line(f"fim_{effect}")
            if effect == "encolhido":
                self.sfx("cresce")

        self.size_target = SHRUNK if self.needs.has("encolhido") else 1.0
        if self.size != self.size_target:
            self.size += (self.size_target - self.size) * min(1.0, dt * 5)
            if abs(self.size - self.size_target) < 0.01:
                self.size = self.size_target

        getattr(self, f"_u_{self.state}")(dt)
        self._hop_tick(dt)
        self._trail_tick(dt)
        if self.ball and self.ball.held == "pet" and self.state != "fetch":
            self._drop_ball()   # foi interrompido com a bolinha na boca

        for event in self.progress.drain():
            self._on_progress(event)

        self._ground_check()
        self._blink()
        self._effects_fx(dt)
        self._update_particles(dt)
        self.squash = max(0.0, self.squash - dt * 4)

        self._need_check += dt
        if self._need_check >= 5:
            self._need_check = 0
            self._check_needs()

    def _ground_check(self) -> None:
        left, top, right, ground = self.world
        if self.state in AIRBORNE:
            return
        if self.state == "exercise" and self.data.get("kind") == "gato":
            return
        if self.perch:
            # continua em cima da janela? (ela pode ter mexido, sumido ou ele andou até a ponta)
            y0 = self.perch[0]
            near = [p for p in self.platforms if p[1] <= self.x <= p[2] and abs(p[0] - y0) < 40]
            if near:
                self.perch = min(near, key=lambda p: abs(p[0] - y0))
                self.y = self.perch[0]
                self.x = self._clamp_x(self.x)
                return
            self.perch = None
            self.set_state("fall", from_y=self.y)
            return
        if self.y < ground - 1:
            self.set_state("fall", from_y=self.y)
        elif self.y > ground:
            self.y = ground
        self.x = self._clamp_x(self.x)

    def _blink(self) -> None:
        if self.clock >= self.next_blink:
            self.blink_until = self.clock + 0.14
            self.next_blink = self.clock + random.uniform(2.5, 6.0)

    # ---- estados ---------------------------------------------------------
    def _u_idle(self, dt: float) -> None:
        if self.t >= self.data.get("dur", 3.0):
            self.decide()

    def decide(self) -> None:
        n = self.needs
        if n["sono"] < 8:
            self.line("sono_critico", "need")
            self.start_sleep()
            return
        self.maybe_chat()
        if self.progress.presents:
            self.set_state("idle", dur=random.uniform(4, 8))  # espera você abrir o presente
            return
        if (self.settings.solo_play and self.progress.knows("sozinho") and n.mood() == "feliz"
                and n["energia"] > 50 and self.clock - self.last_solo > SOLO_COOLDOWN and random.random() < 0.2):
            self.last_solo = self.clock
            self.do_activity(random.choice([a for a in SOLO_ACTIVITIES if self.progress.unlocked(self.items.get(a))]),
                             solo=True)
            if self.state == "exercise":
                return
        if self.platforms and random.random() < 0.15:
            spot = self._climb_spot()
            if spot:
                self.leap_to(*spot)
                return
        r = random.random()
        if n["energia"] < 25 and r < 0.5:
            self.set_state("sit", dur=random.uniform(20, 45))
            return
        if r < 0.5:
            if self.perch and random.random() < 0.3:   # anda até a ponta da janela e cai
                y, x1, x2 = self.perch
                target = x2 + self.sprite_w if self.x > (x1 + x2) / 2 else x1 - self.sprite_w
            else:
                target = self._roam_x(self.x + random.uniform(-450, 450))
            if abs(target - self.x) > 20:
                self.set_state("walk", target=target)
                return
        if r < 0.6 and n["energia"] < 70:
            self.set_state("sit", dur=random.uniform(10, 25))
            return
        self.set_state("idle", dur=random.uniform(2.5, 7.0), look=random.choice((-1, 0, 0, 1)))

    def _walk_towards(self, target: float, speed: float, dt: float) -> bool:
        dx = target - self.x
        if abs(dx) < 1:
            return True
        self.facing = 1 if dx > 0 else -1
        self.x += self.facing * min(abs(dx), speed * dt)
        return abs(target - self.x) < 1

    def _u_walk(self, dt: float) -> None:
        if self._walk_towards(self.data["target"], self.walk_speed(), dt):
            self.set_state("idle", dur=random.uniform(2, 6))

    def _u_sit(self, dt: float) -> None:
        if self.t >= self.data.get("dur", 20):
            self.set_state("idle", dur=2)

    def _u_sleep(self, dt: float) -> None:
        if self.clock - self.data.get("last_z", -10) > 1.4:
            self.data["last_z"] = self.clock
            self.particles.append(Particle(
                "z", x=self.sprite_w * 0.3, y=-self.sprite_h * 0.75,
                vx=random.uniform(6, 14), vy=-22, life=2.6,
                text=random.choice("zZ"), size=10 + self.s * 2))
        if self.t >= self.data.get("next_dream", 90):
            self.data["next_dream"] = self.t + random.uniform(150, 300)
            self.line("sonho")
        if self.needs["sono"] >= 100 and (not self.data.get("nap") or self.t > 600):
            self.data["nap"] = False  # acordou sozinho, não porque você voltou
            self.wake()

    def _u_eat(self, dt: float) -> None:
        if self.clock - self.data.get("last_crumb", -1) > 0.3:
            self.data["last_crumb"] = self.clock
            self.sfx("mastigar")
            for _ in range(2):
                self.particles.append(Particle(
                    "crumb", x=random.uniform(-6, 6) * self.s / 3, y=-self.sprite_h * 0.62,
                    vx=random.uniform(-40, 40), vy=random.uniform(-60, -20), gravity=500, life=1.0,
                    color=random.choice(("#C8783C", "#E0A84F", "#8D4E2A")), size=self.s))
        if self.t >= 2.8:
            self._finish_consume()

    def _u_drink(self, dt: float) -> None:
        if self.t >= 0.15 and self.clock - self.data.get("last_gulp", -1) > 0.55:
            self.data["last_gulp"] = self.clock
            self.sfx("gole")
        if self.t >= 2.4:
            self._finish_consume()

    def _finish_consume(self) -> None:
        item = self.items.get(self.data["item"])
        n = self.needs
        n.apply(item.get("efeitos"))
        cured = n.cure() if item.get("cura") else False
        status = item.get("status")
        if status:
            n.add_effect(status)
        if item.get("desemburra"):
            n.sulk_until = 0.0
            n.annoyance = 0.0
            n.effects.pop("chamuscado", None)
        verb = "comer" if item["categoria"] == "comidas" else "beber"
        prog = self.progress
        prog.bump("comeu" if verb == "comer" else "bebeu")
        prog.collect(item["categoria"], item["id"])
        if item["id"].startswith("pocao_"):
            prog.collect("pocoes", item["id"])
        if item["id"] == "maca_dourada":
            prog.bump("maca_dourada")
        self._xp_fx(prog.care(verb))
        if status == "encolhido":
            self.sfx("encolhe")
        elif status in MAGIC_EFFECTS or item.get("desemburra"):
            self.sfx("brilho")
        elif verb == "comer" and random.random() < 0.35:
            self.sfx("arroto")
        self.held = None
        self.set_state("idle", dur=random.uniform(3, 5))
        if n.sulking():
            treat = item.get("efeitos", {}).get("diversao", 0) >= 10
            if n.reduce_sulk(240 if treat else 60):
                self.line("desemburrou")
            else:
                self.line("emburrado_comer")
            return
        self.happy_until = self.clock + 2.5
        if cured and item["id"] == "leite":
            self.line("leite_cura")
        elif not self.line(f"{verb}_{item['id']}"):
            self.line(verb)

    def _u_exercise(self, dt: float) -> None:
        kind = self.data["kind"]
        getattr(self, f"_x_{kind}")(dt)

    def _x_caminhar(self, dt: float) -> None:
        if "target" not in self.data or self._walk_towards(self.data["target"], self.walk_speed() * 1.2, dt):
            self.data["target"] = self._roam_x(self.x + random.choice((-1, 1)) * random.uniform(150, 500))
        if self.t >= self.data["dur"]:
            self._finish_exercise()

    def _x_correr(self, dt: float) -> None:
        lo, hi = self._roam_bounds()   # de ponta a ponta (da tela ou da janela onde ele está)
        if "target" not in self.data or self._walk_towards(self.data["target"], self.walk_speed() * 3.2, dt):
            self.data["target"] = hi if self.x < (lo + hi) / 2 else lo
        self.jump = abs(math.sin(self.t * 14)) * 4 * self.s / 3
        if self.clock - self.data.get("last_sweat", -1) > 0.45:
            self.data["last_sweat"] = self.clock
            self._sweat()
        if self.t >= self.data["dur"]:
            self.jump = 0
            self._finish_exercise()

    def _x_pular(self, dt: float) -> None:
        period = 0.62
        phase = (self.t % period) / period
        if phase < self.data.get("last_phase", 0):
            self.squash = 0.7
            self.sfx("pulo")
        self.data["last_phase"] = phase
        self.jump = math.sin(phase * math.pi) * 36 * self.s / 3
        if self.t >= self.data["dur"] and phase < 0.1:
            self.jump = 0
            self._finish_exercise()

    def _x_flexao(self, dt: float) -> None:
        if self.clock - self.data.get("last_sweat", -1) > 1.2:
            self.data["last_sweat"] = self.clock
            self._sweat()
        if self.t >= self.data["dur"]:
            self._finish_exercise()

    def _x_dancar(self, dt: float) -> None:
        self.jump = abs(math.sin(self.t * 5)) * 7 * self.s / 3
        self.x = self._roam_x(self.x + math.cos(self.t * 2.5) * 40 * dt)
        if self.clock - self.data.get("last_note", -1) > 0.55:
            self.data["last_note"] = self.clock
            # passeia pela escala em passos curtos, pra soar como melodia
            note = self.data.get("note", 2) + random.choice((-2, -1, -1, 1, 1, 2))
            self.data["note"] = note = max(0, min(7, note))
            self.sfx(f"nota_{note}")
            self.particles.append(Particle(
                "note", x=random.uniform(-1, 1) * self.sprite_w, y=-self.sprite_h * 0.9,
                vx=random.uniform(-15, 15), vy=-40, life=1.8, text=random.choice("♪♫"),
                color=random.choice(("#FFEB3B", "#F48FB1", "#81D4FA", "#A5D6A7")), size=12 + self.s * 2))
        if self.t >= self.data["dur"]:
            self.jump = 0
            self._finish_exercise()

    def _x_descansar(self, dt: float) -> None:
        if self.t >= self.data["dur"]:
            self._finish_exercise()

    def _x_gato(self, dt: float) -> None:
        left, _, right, _ = self.world
        phase = self.data.setdefault("phase", "susto")
        if phase == "susto":
            if "cat_side" not in self.data:
                side = 1 if self.x < (left + right) / 2 else -1
                self.data["cat_side"] = side
                self.particles.append(Particle(
                    "icon", x=side * (self.sprite_w + 30), y=0, life=4.5, text="gato", size=12 * self.s))
                self.sfx("miau")
                self.line("inicio_gato", "reaction")
            self.jump = math.sin(min(1.0, self.t / 0.5) * math.pi) * 22 * self.s / 3
            if self.t > 0.6:
                self.jump = 0
                self.data["phase"] = "fuga"
        elif phase == "fuga":
            away = -self.data["cat_side"]
            edge = (right + self.sprite_w) if away > 0 else (left - self.sprite_w)
            if self.clock - self.data.get("last_sweat", -1) > 0.3:
                self.data["last_sweat"] = self.clock
                self._sweat()
            if self._walk_towards(edge, self.walk_speed() * 5, dt):
                self.hidden = True
                self.perch = None
                self.y = self.world[3]   # fugiu da janela também: volta pelo chão
                self.data.update(phase="longe", until=self.t + random.uniform(8, 12))
        elif phase == "longe":
            if self.t >= self.data["until"]:
                self.hidden = False
                self.data["phase"] = "volta"
        elif phase == "volta":
            away = -self.data["cat_side"]
            target = (right - self._margin() - 60) if away > 0 else (left + self._margin() + 60)
            if self._walk_towards(target, self.walk_speed(), dt):
                self._finish_exercise()

    def _x_minerar(self, dt: float) -> None:
        d = self.data
        size = 10 * self.s
        bx = self.facing * (self.sprite_w / 2 + 6 + size / 2)
        self.tool = "minerar"
        self.tool_angle *= max(0.0, 1 - dt * 8)   # a picareta volta depois do golpe
        if not self.props and self.t >= d.get("next_block", 0.0):
            block, drop, hits, _ = random.choices(ORES, weights=[o[3] for o in ORES])[0]
            self.props = [Prop("icon", block, x=bx, size=size)]
            d.update(drop=drop, hits=hits, done=0, next_hit=self.t + 0.45)
        if self.props and self.t >= d["next_hit"]:
            d["next_hit"] = self.t + 0.55
            d["done"] += 1
            self.tool_angle = 70.0
            self.squash = 0.2
            self.sfx("picareta")
            self._chips(bx, size, 3)
            self.props[0].crack = d["done"] / d["hits"]
            if d["done"] >= d["hits"]:
                self.props = []
                self.sfx("quebra")
                self._chips(bx, size, 12)
                self.progress.bump("blocos")
                d["next_block"] = self.t + 0.7
                if d["drop"]:
                    self.particles.append(Particle(
                        "icon", x=bx, y=-size * 0.3, vx=-self.facing * 50, vy=-260, gravity=700, life=1.4,
                        text=d["drop"], size=6 * self.s))
                if d["drop"] == "diamante":
                    self.progress.bump("diamantes")
                    self.happy_until = self.clock + 2.5
                    self.line("minerar_diamante", "reaction")
        if self.t >= d["dur"]:
            self._finish_exercise()

    def _chips(self, x: float, size: float, count: int) -> None:
        for _ in range(count):
            self.particles.append(Particle(
                "debris", x=x + random.uniform(-0.4, 0.4) * size, y=-random.uniform(0.2, 0.9) * size,
                vx=random.uniform(-90, 90), vy=random.uniform(-200, -60), gravity=900, life=random.uniform(0.5, 0.9),
                color=random.choice(("#8E8E8E", "#A5A5A5", "#6E6E6E")), size=self.s * random.choice((1, 1.5))))

    def _x_pescar(self, dt: float) -> None:
        d = self.data
        f = self.facing
        water_x = f * (self.sprite_w / 2 + 60)   # cabe na janela até no tamanho grande
        self.tool = "vara"
        if not self.props:
            self.props = [Prop("water", x=water_x, size=80), Prop("line")]
            d.update(phase="lancar", pt=0.0)
        d["pt"] += dt
        phase, pt = d["phase"], d["pt"]
        tip_x, tip_y = self.rod_tip()
        float_y = -3.0
        if phase == "lancar":       # balança a vara e a boia voa num arco até a água
            k = min(1.0, pt / 0.6)
            self.tool_angle = -35 * math.sin(k * math.pi)
            bx = tip_x + (water_x - tip_x) * k
            by = tip_y + (float_y - tip_y) * k - math.sin(k * math.pi) * 60
            if k >= 1:
                d.update(phase="esperar", pt=0.0, bite=random.uniform(3, 7))
                self.sfx("splash", 0.35)
                self._splash(water_x, 4)
        elif phase == "esperar":
            bx, by = water_x, float_y + math.sin(self.clock * 3) * 1.5
            if pt >= d["bite"]:
                d.update(phase="fisgou", pt=0.0)
                self.sfx("splash")
                self._splash(water_x, 8)
                self.particles.append(Particle("note", x=water_x, y=-30, vy=-25, life=0.9, text="!",
                                               color="#FFEB3B", size=14 + self.s * 2))
        elif phase == "fisgou":     # a boia afunda
            bx, by = water_x, float_y + (5 if pt < 0.45 else 2)
            if pt >= 0.55:
                d.update(phase="puxar", pt=0.0, catch=self._roll_catch())
        else:                       # puxar: a boia volta pra vara trazendo o que pegou
            k = min(1.0, pt / 0.6)
            self.tool_angle = 30 * (1 - k)
            bx = water_x + (tip_x - water_x) * k
            by = float_y + (tip_y - float_y) * k - math.sin(k * math.pi) * 40
            if k >= 1:
                self._caught(d["catch"], bx, by)
                d.update(phase="lancar", pt=0.0)
        line = self.props[1]
        line.x, line.y, line.x2, line.y2 = tip_x, tip_y, bx, by
        if self.t >= d["dur"] and phase in ("lancar", "esperar"):
            self._finish_exercise()

    def _roll_catch(self) -> tuple[str, str]:
        """("peixe" | "bota" | "tesouro", ícone)."""
        kind = random.choices([c for c, _ in CATCHES], weights=[w for _, w in CATCHES])[0]
        if kind == "tesouro":
            item = self.progress.random_special()
            if item:
                return "tesouro", item["id"]
            kind = "peixe"
        return kind, kind

    def _caught(self, catch: tuple[str, str], x: float, y: float) -> None:
        kind, icon = catch
        self.particles.append(Particle("icon", x=x, y=y + 10, vy=-70, life=1.5, text=icon, size=7 * self.s))
        self.sfx("pop")
        if kind == "peixe":
            self.progress.bump("peixes")
            self.line("pescar_peixe", "reaction")
        elif kind == "bota":
            self.line("pescar_lixo", "reaction")
        else:
            self.progress.give(icon)
            self.progress.bump("tesouros")
            self.sfx("brilho")
            self.happy_until = self.clock + 2.5
            self.line("pescar_tesouro", "reaction", item=self.items.get(icon)["nome"])

    def _splash(self, x: float, count: int) -> None:
        for _ in range(count):
            self.particles.append(Particle(
                "spark", x=x + random.uniform(-8, 8), y=-2, vx=random.uniform(-60, 60), vy=random.uniform(-160, -70),
                gravity=600, life=0.6, color=random.choice(("#90CAF9", "#E3F2FD", "#64B5F6")), size=self.s * 1.2))

    def _x_plantar(self, dt: float) -> None:
        d = self.data
        px = self.facing * (self.sprite_w / 2 + 14)
        if self.t < 3.0:   # cava com os pés (creeper não tem mão)
            if self.clock - d.get("last_dig", -1.0) > 0.45:
                d["last_dig"] = self.clock
                self.squash = 0.35
                self.sfx("cavar")
                for _ in range(5):
                    self.particles.append(Particle(
                        "crumb", x=px + random.uniform(-6, 6), y=-2, vx=random.uniform(-70, 70),
                        vy=random.uniform(-180, -80), gravity=700, life=0.7,
                        color=random.choice(("#795548", "#5D4037", "#8D6E63")), size=self.s * 1.2))
        else:
            stage = 0 if self.t < 7 else 1 if self.t < 11 else 2
            if d.get("stage") != stage:
                d["stage"] = stage
                name, size = (("plantar", 5 * self.s), ("plantar", 8 * self.s), ("flor", 9 * self.s))[stage]
                self.props = [Prop("icon", name, x=px, size=size)]
                self.sfx("brilho" if stage == 2 else "pop")
                if stage == 2:
                    self.happy_until = self.clock + 3.0
            if stage < 2 and self.clock - d.get("last_meal", -1.0) > 0.5:   # farinha de osso brilhando
                d["last_meal"] = self.clock
                self.particles.append(Particle(
                    "spark", x=px + random.uniform(-10, 10), y=-random.uniform(4, 22), vy=-20, life=0.8,
                    color=random.choice(("#7CFC5A", "#C6FF9E")), size=self.s * 1.5))
        if self.t >= d["dur"]:
            self._finish_exercise()

    def _x_porco(self, dt: float) -> None:
        d = self.data
        if "target" not in d or self._walk_towards(d["target"], self.walk_speed() * 1.8, dt):
            d["target"] = self._roam_x(self.x + random.choice((-1, 1)) * random.uniform(150, 450))
        scale = self.s * 1.25
        frame = 1 + int(self.t * 6) % 2
        self.props = [Prop("big", f"porco_{frame}", size=scale, flip=self.facing < 0)]
        self.jump = 7 * scale + abs(math.sin(self.t * 9)) * self.s   # montado, balançando
        if self.clock - d.get("last_oink", 0.0) > d.get("oink_gap", 0.8):
            d["last_oink"] = self.clock
            d["oink_gap"] = random.uniform(2, 4)
            self.sfx("oinc")
        if self.t >= d["dur"]:
            self.squash = 0.5
            self._finish_exercise()

    def _x_fogos(self, dt: float) -> None:
        d = self.data
        if self.clock - d.get("last_launch", -10.0) > 1.6 and self.t < d["dur"] - 1.5:
            d["last_launch"] = self.clock
            self.particles.append(Particle(
                "rocket", x=self.facing * (self.sprite_w / 2 + 18) + random.uniform(-12, 12), y=-8,
                vx=random.uniform(-25, 25), vy=-430, gravity=180, life=random.uniform(0.75, 0.95),
                color=random.choice(FIREWORK_COLORS), size=self.s))
            self.sfx("foguete")
        for p in [p for p in self.particles if p.kind == "rocket"]:
            self.particles.append(Particle("spark", x=p.x, y=p.y + 5, vx=random.uniform(-10, 10), vy=30,
                                           life=0.35, color="#FFD180", size=self.s))   # rastro
            if p.age + dt >= p.life:
                self._burst(p.x, p.y, p.color)
        if self.t >= d["dur"]:
            self._finish_exercise()

    def _burst(self, x: float, y: float, color: str) -> None:
        self.sfx("estouro")
        n = 36
        for i in range(n):
            ang = i / n * math.tau + random.uniform(-0.1, 0.1)
            spd = random.uniform(90, 150)
            self.particles.append(Particle(
                "spark", x=x, y=y, vx=math.cos(ang) * spd, vy=math.sin(ang) * spd, gravity=120,
                life=random.uniform(0.9, 1.4), color=random.choice((color, color, "#FFFFFF")), size=self.s * 1.5))

    def _hop_tick(self, dt: float) -> None:
        """Poção de salto: de vez em quando ele dá um pulo altíssimo, parado ou andando."""
        if self.hop is None:
            if (self.needs.has("salto") and self.state in ("idle", "walk") and not self.hidden
                    and random.random() < dt * 0.7):
                self.hop = 0.0
                self.sfx("pulo")
            return
        self.hop += dt
        phase = self.hop / HOP_TIME
        if phase >= 1:
            self.hop = None
            self.jump = 0.0
            self.squash = 0.7
            self.sfx("pouso", 0.3)
            return
        self.jump = math.sin(phase * math.pi) * self.sprite_h * 1.1

    def _finish_exercise(self) -> None:
        kind = self.data["kind"]
        self.needs.apply(self.items.get(kind).get("efeitos"))
        prog = self.progress
        prog.bump("atividades")
        prog.collect("atividades", kind)
        if kind in ACTIVITY_COUNTERS:
            prog.bump(ACTIVITY_COUNTERS[kind])
        if not self.data.get("solo"):
            self._xp_fx(prog.care("gato" if kind == "gato" else "atividade"))
        self.jump = 0
        self.hidden = False
        self.set_state("idle", dur=random.uniform(3, 5))
        self.line(f"fim_{kind}")
        if kind != "gato":
            self.happy_until = self.clock + 2.0

    def _u_hiss(self, dt: float) -> None:
        dur = 2.4
        progress = min(1.0, self.t / dur)
        self.flash = (math.sin(self.t * (6 + 22 * progress)) + 1) / 2 * (0.4 + 0.5 * progress)
        self.swell = 0.14 * progress
        if self.needs.annoyance < 70:
            self.flash = self.swell = 0.0
            self.sfx_stop("chiado")
            self.progress.bump("acalmou")
            self.set_state("idle", dur=3)
            self.line("carinho_acalmou", "reaction")
            return
        if self.t >= dur:
            self.explode()

    def explode(self) -> None:
        self.flash = self.swell = 0.0
        self.hidden = True
        self.perch = None
        h = self.sprite_h
        charged = self.settings.charged   # creeper carregado explode maior, como no jogo
        skin = cosmetics.SKINS.get(self.settings.skin)
        colors = skin["tons"][:5] if skin else ("#1F6B1C", "#2F8A28", "#3FA535", "#55BC48", "#74D166")
        for _ in range(70 if charged else 46):
            ang = random.uniform(0, math.tau)
            spd = random.uniform(150, 520) * (1.25 if charged else 1.0)
            self.particles.append(Particle(
                "debris", x=random.uniform(-0.4, 0.4) * self.sprite_w, y=-random.uniform(0.1, 0.9) * h,
                vx=math.cos(ang) * spd, vy=math.sin(ang) * spd - 220, gravity=1300,
                life=random.uniform(1.2, 2.2), color=random.choice(colors), size=random.choice((1, 2, 2, 3)) * self.s))
        for _ in range(16):
            ang = random.uniform(0, math.tau)
            spd = random.uniform(20, 120)
            self.particles.append(Particle(
                "smoke", x=random.uniform(-0.5, 0.5) * self.sprite_w, y=-random.uniform(0.2, 0.8) * h,
                vx=math.cos(ang) * spd, vy=math.sin(ang) * spd - 40, life=random.uniform(1.2, 2.0),
                color=random.choice(("#EEEEEE", "#BDBDBD", "#9E9E9E")), size=random.uniform(8, 18) * self.s / 3))
        self.particles.append(Particle("boom", x=0, y=-h / 2, life=0.35, size=h * (1.7 if charged else 1.2)))
        self.needs.annoyance = 0.0
        self.needs.sulk(10 * 60)
        self.needs.add_effect("chamuscado")
        self.held = None
        self.set_state("exploded")
        self.sfx("explosao")
        self.progress.bump("explosoes")

    def _u_exploded(self, dt: float) -> None:
        if self.t >= 3.5:
            left, top, right, ground = self.world
            self.hidden = False
            self.y = max(top + self.sprite_h + 20, ground - 500)
            self.vy = self.vx = 0
            self.set_state("fall", from_y=self.y, respawn=True)

    def _u_fall(self, dt: float) -> None:
        left, top, right, ground = self.world
        prev_y = self.y
        self.vy += GRAVITY * dt
        self.y += self.vy * dt
        self.x += self.vx * dt
        self.vx *= max(0.0, 1 - 2.5 * dt)
        if self.x < left + self.sprite_w / 2 or self.x > right - self.sprite_w / 2:
            self.vx = -self.vx * 0.5
            self.x = max(left + self.sprite_w / 2, min(right - self.sprite_w / 2, self.x))
        self.tilt *= max(0.0, 1 - 6 * dt)
        if self.vy > 0:   # caindo: pode pousar em cima de uma janela no caminho
            for plat in self.platforms:
                y, x1, x2 = plat
                if x1 <= self.x <= x2 and prev_y <= y <= self.y and y < ground - 5:
                    self.perch = plat
                    ground = y
                    break
        if self.y >= ground:
            self.y = ground
            height = ground - self.data.get("from_y", ground)
            self.squash = min(1.0, self.vy / 1400)
            self.vy = self.vx = 0
            self.tilt = 0
            respawn = self.data.get("respawn")
            if respawn or height > 40:
                self.sfx("pouso", min(1.0, 0.35 + height / 600))
            self.set_state("idle", dur=2.5)
            if respawn:
                self.line("explodiu", "reaction")
            elif height > 300:
                self.line("solto_alto", "reaction")
            elif height > 40 and random.random() < 0.35:
                self.line("solto", "reaction")

    def _u_dragged(self, dt: float) -> None:
        pass

    # ---- ações vindas do usuário -----------------------------------------
    def feed(self, item_id: str) -> None:
        item = self.items.get(item_id)
        if not self.can_interact() or self.busy() or not self.progress.unlocked(item):
            return
        if self.progress.stock(item) == 0:
            self.line("sem_estoque", "reaction", item=item["nome"])
            return
        if self.state == "sleep":
            self.wake(forced=True)
        food = item["categoria"] == "comidas"
        stat = "fome" if food else "sede"
        if self.needs[stat] >= 95:
            self.line("comer_cheio" if food else "beber_cheio", "reaction")
            return
        self.progress.take(item)
        self.held = item_id
        self.set_state("eat" if food else "drink", item=item_id)
        self.sfx("pop")

    def do_activity(self, act_id: str, solo: bool = False) -> None:
        """Começa uma atividade. solo=True: foi ele que quis (não dá XP de cuidado)."""
        item = self.items.get(act_id)
        if not self.can_interact() or self.busy() or not self.progress.unlocked(item):
            return
        if self.state == "sleep":
            self.wake(forced=True)
        if self.needs["energia"] < 15 and act_id not in ("descansar", "gato"):
            self.line("atividade_cansado", "reaction")
            return
        self.set_state("exercise", kind=act_id, dur=float(item.get("duracao", 10)), solo=solo)
        if solo:
            self.line("brincar_sozinho", "chat")
        elif act_id != "gato":
            self.sfx("pop")
            self.line(f"inicio_{act_id}", "reaction")

    def request_sleep(self) -> None:
        if not self.can_interact() or self.busy() or self.state == "sleep":
            return
        if self.needs.has("cafeinado"):
            self.line("dormir_cafe", "reaction")
        elif self.needs["sono"] >= 85:
            self.line("dormir_sem_sono", "reaction")
        else:
            self.line("dormir", "reaction")
            self.start_sleep()

    def start_sleep(self, nap: bool = False) -> None:
        self.held = None
        self.jump = 0
        self.set_state("sleep", nap=nap, next_dream=random.uniform(60, 150))

    def wake(self, forced: bool = False) -> None:
        if self.state != "sleep":
            return
        nap = self.data.get("nap")
        self.set_state("idle", dur=3)
        if nap:
            self.line("cochilo_volta", "reaction")
        elif forced and self.needs["sono"] < 60:
            self.needs.annoy(20)
            self.line("acordar_forcado", "reaction")
        else:
            self.line("acordar_natural", "reaction")

    def poke(self) -> None:
        if self.state == "hide":
            if self.data.get("phase") == "escondido":
                self._end_hide(found=True)   # achou!
            return
        if not self.can_interact():
            return
        now = self.clock
        self.flinch_until = now + 0.35
        self.squash = 0.5
        self.sfx("cutucao")
        if self.state == "sleep":
            self.needs.annoy(10)
            self.wake(forced=True)
            self.last_poke = now
            return
        quick = now - self.last_poke < 2.0
        self.last_poke = now
        if self.needs.sulking():
            self.needs.annoy(5)
            self.line("emburrado", "reaction")
            return
        self.needs.annoy(16 if quick else 9)
        a = self.needs.annoyance
        if a >= 100:
            self.start_hiss()
        elif a >= 75:
            self.line("poke_aviso", "reaction")
        elif a >= 45:
            self.line("poke_irritado", "reaction")
        else:
            self.line("poke", "reaction")

    def start_hiss(self) -> None:
        self.held = None
        self.jump = 0
        self.set_state("hiss")
        self.sfx("chiado")
        self.line("sibilar", "reaction")

    def stroke(self) -> None:
        """Carinho (passar o mouse de um lado pro outro em cima dele)."""
        if self.hidden or self.state in ("exploded", "dragged", "fall"):
            return
        now = self.clock
        self.needs.annoyance = max(0.0, self.needs.annoyance - 14)
        if now - self.last_pet_fun > 1.0:
            self.last_pet_fun = now
            self.needs.apply({"diversao": 2})
            self.sfx("carinho")
            self.progress.bump("carinhos")
            self._xp_fx(self.progress.care("carinho"), sound=False)
            self.particles.append(Particle(
                "heart", x=random.uniform(-0.5, 0.5) * self.sprite_w, y=-self.sprite_h * 0.95,
                vx=random.uniform(-10, 10), vy=-35, life=1.4, size=self.s * 3))
        if self.state == "hiss":
            return  # _u_hiss decide se acalmou
        self.happy_until = now + 1.5
        if self.needs.reduce_sulk(45):
            self.line("desemburrou", "reaction")
            self.last_pet_line = now
        elif self.state != "sleep" and not self.needs.sulking() and now - self.last_pet_line > 25:
            self.last_pet_line = now
            self.line("carinho", "reaction")

    def start_drag(self) -> bool:
        if self.state in ("exploded", "hiss", "hide") or self.hidden:
            return False
        if self.state == "sleep":
            self.wake(forced=True)
        self.perch = None
        self.held = None
        self.jump = 0
        self.set_state("dragged")
        self._drag_samples.clear()
        self._reversals.clear()
        if random.random() < 0.5:
            self.line("arrastado", "reaction")
        return True

    def drag_to(self, x: float, y: float) -> None:
        now = self.clock
        if self._drag_samples:
            px, py, pt = self._drag_samples[-1]
            dt = max(1e-3, now - pt)
            vx = (x - px) / dt
            if abs(vx) > 900:
                last_dir = self.data.get("dir", 0)
                d = 1 if vx > 0 else -1
                if last_dir and d != last_dir:
                    self._reversals.append(now)
                self.data["dir"] = d
        self._drag_samples.append((x, y, now))
        self.x, self.y = x, y
        recent = [t for t in self._reversals if now - t < 1.2]
        if len(recent) >= 4:
            self._reversals.clear()
            if now >= self.dizzy_until:
                self.sfx("tonto")
                self.progress.bump("tonto")
            self.dizzy_until = now + 3.0
            self.needs.annoy(6)
            if now - self.last_shake_line > 6:
                self.last_shake_line = now
                self.line("chacoalhado", "reaction")
        # inclina conforme a velocidade
        if len(self._drag_samples) >= 2:
            (x0, _, t0), (x1, _, t1) = self._drag_samples[0], self._drag_samples[-1]
            vx = (x1 - x0) / max(1e-3, t1 - t0)
            self.tilt = max(-28.0, min(28.0, vx * 0.03))

    def end_drag(self) -> None:
        if self.state != "dragged":
            return
        vx = 0.0
        if len(self._drag_samples) >= 2:
            (x0, _, t0), (x1, _, t1) = self._drag_samples[0], self._drag_samples[-1]
            if self.clock - t1 < 0.1:
                vx = (x1 - x0) / max(1e-3, t1 - t0)
        self.vx = max(-900.0, min(900.0, vx * 0.6))
        self.vy = 0.0
        self.set_state("fall", from_y=self.y)

    def user_idle(self, seconds: float | None) -> None:
        """Chamado periodicamente com o tempo sem mexer no PC."""
        if seconds is None:
            return
        if seconds < 60 and self.state == "sleep" and self.data.get("nap"):
            self.wake()
        elif seconds > 15 * 60 and self.state in ("idle", "walk", "sit") and self.needs["sono"] < 75:
            self.start_sleep(nap=True)

    # ---- falas espontâneas -----------------------------------------------
    def maybe_chat(self) -> None:
        now = time.monotonic()
        mode = self.settings.chattiness
        if now - self.last_chat < CHAT_COOLDOWN.get(mode, 160):
            return
        if random.random() > CHAT_CHANCE.get(mode, 0.4):
            return
        hour = datetime.now().hour
        key = "idle"
        if self.needs.sulking():
            key = "emburrado"
        elif self.progress.presents and random.random() < 0.6:
            key = "presente_esperando"
        elif (hour >= 22 or hour < 5) and random.random() < 0.4:
            key = "idle_noite"
        elif 6 <= hour < 10 and random.random() < 0.3:
            key = "idle_manha"
        self.line(key)

    def _check_needs(self) -> None:
        if self.state in ("sleep", "exploded", "hiss", "dragged", "fall", "eat", "drink", "hide", "leap") or self.hidden:
            return
        stat, value = self.needs.worst()
        if value >= 35:
            return
        critical = value < 15
        gap = 150 if critical else 360
        now = time.monotonic()
        if now - self.last_need.get(stat, -1e9) < gap:
            return
        self.last_need[stat] = now
        normal, crit = NEED_LINES[stat]
        self.line(crit if critical else normal, "need_critical" if critical else "need")

    # ---- subir nas janelas -----------------------------------------------
    def leap_to(self, x: float, y: float, perch=None, then: tuple | None = None) -> None:
        """Pulo em arco até (x, y). perch = a janela onde vai ficar; then = (estado, dados) depois."""
        self.set_state("leap", x0=self.x, y0=self.y, x1=x, y1=y, perch=perch, then=then,
                       arc=max(30.0, (self.y - y) * 0.35 + 30), dur=0.55 + min(0.4, abs(self.y - y) / 1500))
        self.perch = None
        self.sfx("pulo")

    def _u_leap(self, dt: float) -> None:
        d = self.data
        k = min(1.0, self.t / d["dur"])
        self.x = d["x0"] + (d["x1"] - d["x0"]) * k
        self.y = d["y0"] + (d["y1"] - d["y0"]) * k - math.sin(k * math.pi) * d["arc"]
        if d["x1"] != d["x0"]:
            self.facing = 1 if d["x1"] > d["x0"] else -1
        if k < 1:
            return
        self.y = d["y1"]
        self.perch = d["perch"]
        self.squash = 0.6
        self.sfx("pouso", 0.4)
        then = d["then"]
        if then:
            self.set_state(then[0], **then[1])
        else:
            self.set_state("idle", dur=random.uniform(2, 5))
            if self.perch:
                self.progress.bump("janelas")
                if random.random() < 0.4:
                    self.line("subiu_janela")

    def _climb_spot(self) -> tuple[float, float, tuple] | None:
        """Uma janela aqui por cima onde dá pra pular (perto, nem alta demais, com espaço pro corpo)."""
        left, top, right, _ = self.world
        spots = []
        for plat in self.platforms:
            y, x1, x2 = plat
            if not (60 <= self.y - y <= 450) or y - self.sprite_h - 10 < top:
                continue
            if x2 - x1 < self.sprite_w + 20 or x2 < left or x1 > right:
                continue
            tx = max(x1 + self.sprite_w / 2 + 6, min(x2 - self.sprite_w / 2 - 6, self.x))
            if abs(tx - self.x) <= 300:
                spots.append((tx, y, plat))
        return random.choice(spots) if spots else None

    def _get_down(self, then: tuple) -> bool:
        """Se estiver em cima de uma janela, pula pro chão e depois faz `then`."""
        if not self.perch:
            return False
        self.leap_to(self.x, self.world[3], None, then=then)
        return True

    # ---- vir quando chamado ------------------------------------------------
    def call(self, x: float) -> None:
        """Você chamou: ele corre até o x do mouse."""
        if self.hidden or self.state in ("exploded", "dragged", "fall", "hiss", "hide", "leap"):
            return
        if self.state == "sleep":
            self.wake()
        self.held = None
        self.line("chamado", "reaction")
        if not self._get_down(("come", {"target": x})):
            self.set_state("come", target=x)

    def _u_come(self, dt: float) -> None:
        self.jump = abs(math.sin(self.t * 14)) * 4 * self.s / 3
        if self._walk_towards(self._clamp_x(self.data["target"]), self.walk_speed() * 3, dt):
            self.jump = 0
            self.set_state("idle", dur=4)
            self.happy_until = self.clock + 2.0
            self.line("chamado_chegou", "reaction")

    # ---- bolinha ---------------------------------------------------------
    def start_ball(self) -> None:
        self.line("bolinha_inicio", "reaction")
        if not self._get_down(("fetch", {"phase": "wait"})):
            self.set_state("fetch", phase="wait")

    def fetch(self) -> None:
        """Você jogou a bolinha: ele vai buscar."""
        if not self.ball or self.hidden or self.state in ("exploded", "dragged", "fall", "hiss", "hide", "leap"):
            return
        if self.state == "sleep":
            self.wake()
        if not self._get_down(("fetch", {"phase": "go"})):
            self.set_state("fetch", phase="go")

    def _u_fetch(self, dt: float) -> None:
        b, d = self.ball, self.data
        if not b or not b.active:
            self.jump = 0
            self.set_state("idle", dur=2)
            return
        phase = d["phase"]
        if phase == "wait":
            self.facing = 1 if b.x > self.x else -1
            self.jump = abs(math.sin(self.t * 7)) * 4 * self.s / 3 if (self.t % 3) < 0.9 else 0.0   # ansioso
            if b.held == "none" and not b.resting and abs(b.x - self.x) > 80:
                d["phase"] = "go"    # a bolinha saiu rolando sozinha
            elif self.t > 120:
                self.end_ball()
        elif phase == "go":
            if b.held == "user":
                self.jump = 0
                self.set_state("fetch", phase="wait")
                return
            self._walk_towards(self._clamp_x(b.x), self.walk_speed() * 3.2, dt)
            self.jump = abs(math.sin(self.t * 14)) * 3 * self.s / 3
            if abs(b.x - self.x) < self.sprite_w * 0.7 and b.y > self.y - self.sprite_h * 0.45:
                b.held = "pet"
                self.held = "bola"
                self.sfx("pop")
                d.update(phase="back", target=self._clamp_x(b.thrown_from))
        else:   # back: traz de volta pra perto de onde você jogou
            self.jump = abs(math.sin(self.t * 12)) * 3 * self.s / 3
            if self._walk_towards(d["target"], self.walk_speed() * 2.5, dt):
                self.jump = 0
                self._drop_ball()
                self.needs.apply({"diversao": 4})
                self.progress.bump("bolinha")
                self._xp_fx(self.progress.care("carinho"), sound=False)
                self.happy_until = self.clock + 2.0
                self.line("bolinha_trouxe", "reaction")
                self.set_state("fetch", phase="wait")

    def _drop_ball(self) -> None:
        if self.held == "bola":
            self.held = None
        if self.ball and self.ball.held == "pet":
            self.ball.place(self.x + self.facing * (self.sprite_w * 0.6 + 12), self.y - self.sprite_h * 0.5 - self.jump)

    def end_ball(self) -> None:
        """Guarda a bolinha (ou ele cansou de brincar)."""
        if self.held == "bola":
            self.held = None
        if self.ball:
            self.ball.active = False
        self.jump = 0
        if self.state == "fetch":
            self.set_state("idle", dur=3)
        self.line("bolinha_fim", "reaction")

    # ---- esconde-esconde ---------------------------------------------------
    def hide_and_seek(self, windows: list) -> None:
        """Começa o esconde-esconde. windows = janelas abertas (pra se esconder atrás delas)."""
        if not self.can_interact() or self.busy():
            return
        if self.state == "sleep":
            self.wake()
        self.held = None
        self.line("esconde_inicio", "reaction")
        self.set_state("hide", phase="contar", windows=windows)

    def _u_hide(self, dt: float) -> None:
        d = self.data
        if d["phase"] == "contar":
            if self.t < 2.5:
                return
            self.sfx("poof")   # só o som: fumaça acompanharia ele e entregaria o esconderijo
            spot = self._hide_spot(d["windows"])
            self.perch = None
            self.x, self.y, self.facing, self.occluder = spot["x"], spot["y"], spot["facing"], spot["occluder"]
            d.update(phase="escondido", base_x=self.x, base_y=self.y, peek=spot["peek"],
                     until=self.t + HIDE_SECONDS, giggle=self.t + random.uniform(10, 18), world=self.world)
            return
        # escondido: de vez em quando espia pra fora e dá uma risadinha
        cycle = self.t % 4.0
        lean = math.sin((cycle - 3.2) / 0.8 * math.pi) if cycle > 3.2 else 0.0
        if d["peek"]:
            self.x = d["base_x"] + d["peek"] * lean * self.sprite_w * 0.25
        else:
            self.y = d["base_y"] - lean * self.sprite_h * 0.12
        if self.t >= d["giggle"]:
            d["giggle"] = self.t + random.uniform(12, 20)
            self.sfx("risadinha")
        if self.t >= d["until"]:
            self._end_hide(found=False)

    def _hide_spot(self, windows: list) -> dict:
        """Escolhe onde se esconder: atrás da borda da tela, atrás de uma janela ou enterrado no chão."""
        left, top, right, ground = self.world
        w, h, far = self.sprite_w, self.sprite_h, 5000.0
        spots = [
            dict(x=left - w * 0.15, y=ground, facing=1, peek=1, occluder=(left - far, top - far, left, ground + far)),
            dict(x=right + w * 0.15, y=ground, facing=-1, peek=-1, occluder=(right, top - far, right + far, ground + far)),
            dict(x=random.uniform(left + w * 2, right - w * 2), y=ground + h * 0.72, facing=random.choice((-1, 1)),
                 peek=0, occluder=(left - far, ground, right + far, ground + far)),
        ]
        behind = []
        for wl, wt, wr, wb in windows:
            # janela que chega no chão e é alta o bastante pra ele caber atrás
            if wb < ground - 4 or wt > ground - h - 10 or wr < left or wl > right:
                continue
            if wl > left + w * 1.5:
                behind.append(dict(x=wl + w * 0.15, y=ground, facing=-1, peek=-1, occluder=(wl, wt, wr, wb)))
            if wr < right - w * 1.5:
                behind.append(dict(x=wr - w * 0.15, y=ground, facing=1, peek=1, occluder=(wl, wt, wr, wb)))
        if behind and random.random() < 0.6:
            return random.choice(behind)
        return random.choice(spots)

    def _end_hide(self, found: bool) -> None:
        d = self.data
        left, top, right, ground = d.get("world", self.world)
        self.occluder = None
        m = self._margin()
        self.x = max(left + m, min(right - m, d.get("base_x", self.x)))
        self.y = ground
        self.squash = 0.6
        self.set_state("idle", dur=3)
        self.happy_until = self.clock + 2.5
        self.sfx("pulo")
        if found:
            self.progress.bump("esconde")
            self._xp_fx(self.progress.care("atividade"))
            self.line("esconde_achou", "reaction")
        else:
            self.line("esconde_ganhei", "reaction")

    def _poof(self) -> None:
        self.sfx("poof")
        for _ in range(10):
            ang = random.uniform(0, math.tau)
            self.particles.append(Particle(
                "smoke", x=math.cos(ang) * self.sprite_w * 0.4, y=-self.sprite_h * 0.5 + math.sin(ang) * 20,
                vx=math.cos(ang) * 60, vy=math.sin(ang) * 60 - 20, life=0.7, color="#E0E0E0", size=10 * self.s / 3))

    # ---- progresso -------------------------------------------------------
    def _on_progress(self, event: tuple) -> None:
        kind = event[0]
        if kind == "level":
            _, level, unlocked = event
            visual = [u for u in unlocked if u.get("tipo") in ("chapeu", "cor", "rastro", "carregado")]
            learned = [u for u in unlocked if u.get("tipo") == "truque"]
            for u in visual:
                self.wear(u["tipo"], u["id"])   # coisa nova do guarda-roupa já vem vestida
            names = ", ".join(i["nome"] for i in unlocked)
            if learned:   # comportamento novo: explica como usar
                self.line(f"truque_{learned[0]['id']}", "reaction", nivel=level)
            elif visual and len(visual) == len(unlocked):
                self.line("desbloqueou_visual", "reaction", nivel=level, itens=names)
            elif unlocked:
                self.line("desbloqueou", "reaction", nivel=level, itens=names)
            else:
                self.line("subiu_nivel", "reaction", nivel=level)
            self.happy_until = self.clock + 3.0
            self.sfx("nivel")
            if not self.hidden:
                self._orbs(24, burst=True)
        elif kind == "achievement":
            self.on_achievement(event[1])
        elif kind == "present":
            if not self.hidden and self.state != "sleep":
                self.line("achou_presente", "reaction")
                self.sfx("pop")
        elif kind == "losing":
            self.line("perdendo_xp", "need")

    # ---- guarda-roupa ----------------------------------------------------
    def wear(self, kind: str, value) -> None:
        """Veste algo: kind = "chapeu" | "cor" | "rastro" (id ou "") ou "carregado" (liga/desliga)."""
        s = self.settings
        if kind == "carregado":
            s.charged = bool(value)
            if s.charged:
                self.strike()
            return
        setattr(s, {"chapeu": "hat", "cor": "skin", "rastro": "trail"}[kind], value or "")
        if value:
            self.sfx("pop")
            self.happy_until = self.clock + 1.5

    def strike(self) -> None:
        """Raio! É assim que um creeper vira carregado."""
        if self.hidden:
            return
        head = -self.sprite_h * 0.95 - self.jump
        x, y, pts = random.uniform(-20, 20), head - 480, []
        while y < head:
            pts.append((x, y))
            y += random.uniform(25, 45)
            x = max(-110.0, min(110.0, x + random.uniform(-28, 28)))
        pts.append((0.0, head))
        self.particles.append(Particle("bolt", x=0, y=0, life=0.45, points=tuple(pts)))
        self.sfx("trovao")
        self.flinch_until = self.clock + 0.6
        for _ in range(14):
            ang = random.uniform(0, math.tau)
            self.particles.append(Particle(
                "spark", x=math.cos(ang) * self.sprite_w * 0.4, y=head + math.sin(ang) * 10,
                vx=math.cos(ang) * 120, vy=math.sin(ang) * 120, life=0.5,
                color=random.choice(("#4FC3F7", "#E1F5FE", "#FFFFFF")), size=self.s * 1.5))

    def _trail_tick(self, dt: float) -> None:
        """Rastro do guarda-roupa: sai de trás dele enquanto anda."""
        moved = abs(self.x - self._last_x)
        self._last_x = self.x
        trail = self.settings.trail
        if not trail or self.hidden or moved < 0.3 or self.state in ("dragged", "fall"):
            return
        self._trail_timer += dt
        if self._trail_timer < 0.12:
            return
        self._trail_timer = 0.0
        x = -self.facing * self.sprite_w * 0.45 + random.uniform(-4, 4)
        y = -random.uniform(0.05, 0.6) * self.sprite_h - self.jump
        if trail == "folhas":
            self.particles.append(Particle(
                "crumb", x=x, y=y, vx=-self.facing * random.uniform(10, 30), vy=-20, gravity=90, life=1.4,
                color=random.choice(("#7CB342", "#558B2F", "#C0CA33", "#F9A825")), size=self.s * 1.5))
        elif trail == "faiscas":
            self.particles.append(Particle(
                "spark", x=x, y=y, vx=-self.facing * 20, vy=random.uniform(-40, -10), life=0.5,
                color=random.choice(("#FFD54F", "#FFF59D", "#FFFFFF")), size=self.s * 1.5))
        elif trail == "coracoes":
            self.particles.append(Particle("heart", x=x, y=y, vx=-self.facing * 10, vy=-30, life=1.1,
                                           size=self.s * 1.5))

    def self_care(self, kind: str) -> None:
        """Você apertou "Fiz!" no lembrete de água ou de pausa."""
        gain = self.progress.self_care(kind)
        self.happy_until = self.clock + 2.0
        self.line(f"fiz_{kind}", "reaction")
        self._xp_fx(gain)

    def open_present(self) -> None:
        result = self.progress.open_present()
        if result is None:
            return
        what, qty = result
        self.sfx("brilho")
        self.happy_until = self.clock + 2.5
        if what == "xp":
            self.line("presente_xp", "reaction", xp=qty)
            self._xp_fx(qty, sound=False)
        else:
            name = self.items.get(what)["nome"]
            self.line("presente_item", "reaction", item=f"{qty}x {name}" if qty > 1 else name)
        for _ in range(10):
            self.particles.append(Particle(
                "spark", x=-self.sprite_w * 0.9 + random.uniform(-10, 10), y=-random.uniform(4, 30) * self.s / 3,
                vx=random.uniform(-40, 40), vy=random.uniform(-90, -30), life=0.8,
                color=random.choice(("#FFF59D", "#FFD54F", "#FFFFFF", "#E53935")), size=self.s * 1.5))

    def _xp_fx(self, amount: float, sound: bool = True) -> None:
        """Bolinhas de XP e o "+N" subindo."""
        if amount <= 0 or self.hidden:
            return
        if sound:
            self.sfx("xp")
        self._orbs(min(8, 2 + int(amount) // 5))
        self.particles.append(Particle(
            "note", x=self.sprite_w * 0.55, y=-self.sprite_h * 0.7, vy=-30, life=1.3,
            text=f"+{int(amount)}", color="#B5F23A", size=8 + self.s * 2))

    def _orbs(self, count: int, burst: bool = False) -> None:
        for _ in range(count):
            if burst:
                ang, spd = random.uniform(0, math.tau), random.uniform(80, 260)
            else:
                ang, spd = random.uniform(math.pi * 1.1, math.pi * 1.9), random.uniform(40, 110)
            self.particles.append(Particle(
                "orb", x=random.uniform(-0.4, 0.4) * self.sprite_w, y=-self.sprite_h * random.uniform(0.3, 0.8),
                vx=math.cos(ang) * spd, vy=math.sin(ang) * spd, life=random.uniform(0.7, 1.3),
                color=random.choice(("#B5F23A", "#D7FF6B", "#7FD321")), size=self.s * random.choice((1.5, 2, 2.5))))

    # ---- partículas ------------------------------------------------------
    def _sweat(self) -> None:
        side = random.choice((-1, 1))
        self.particles.append(Particle(
            "sweat", x=side * self.sprite_w * 0.5, y=-self.sprite_h * 0.85,
            vx=side * random.uniform(30, 60), vy=-70, gravity=420, life=0.8, size=self.s * 1.5))

    def _effects_fx(self, dt: float) -> None:
        if self.hidden:
            return
        self._fx_timer += dt
        if self._fx_timer < 0.25:
            return
        self._fx_timer = 0
        if self.needs.has("dourado"):
            self.particles.append(Particle(
                "spark", x=random.uniform(-0.6, 0.6) * self.sprite_w, y=-random.uniform(0.05, 1.0) * self.sprite_h,
                vy=-15, life=0.7, color=random.choice(("#FFF59D", "#FFD54F", "#FFFFFF")), size=self.s * 1.5))
        if self.needs.has("chamuscado") and random.random() < 0.15:
            self.particles.append(Particle(
                "smoke", x=random.uniform(-0.3, 0.3) * self.sprite_w, y=-self.sprite_h * 0.9,
                vy=-25, life=1.6, color="#9E9E9E", size=4 * self.s / 3))
        if self.needs.has("velocidade") and self.state == "walk" and random.random() < 0.5:
            self.particles.append(Particle(
                "spark", x=-self.facing * self.sprite_w * 0.6, y=-random.uniform(0.1, 0.8) * self.sprite_h,
                vx=-self.facing * 30, life=0.4, color="#B3E5FC", size=self.s * 1.5))
        for effect, color in POTION_SWIRL.items():   # redemoinho da poção, como no jogo
            if self.needs.has(effect) and random.random() < 0.45:
                self.particles.append(Particle(
                    "spark", x=random.uniform(-0.5, 0.5) * self.sprite_w,
                    y=-random.uniform(0.1, 0.9) * self.sprite_h - self.jump,
                    vx=random.uniform(-8, 8), vy=-25, life=0.9, color=color, size=self.s * 1.5))

    def _update_particles(self, dt: float) -> None:
        alive = []
        for p in self.particles:
            p.age += dt
            if p.age >= p.life:
                continue
            p.vy += p.gravity * dt
            p.x += p.vx * dt
            p.y += p.vy * dt
            if p.gravity and p.y > 0:
                p.y = 0
                p.vy = -p.vy * 0.3
                p.vx *= 0.6
            alive.append(p)
        self.particles = alive[-250:]

    # ---- aparência -------------------------------------------------------
    def _look(self) -> tuple[int, int]:
        if self.cursor is not None:
            cx, cy = self.cursor
            dx = cx - self.x
            dy = cy - (self.y - self.sprite_h * 0.8)
            if dx * dx + dy * dy < 700 * 700:
                lx = 1 if dx > 50 else -1 if dx < -50 else 0
                ly = -1 if dy < -80 else 1 if dy > 80 else 0
                return lx, ly
        if self.state in ("walk", "exercise"):
            return self.facing, 0
        return self.data.get("look", 0), 0

    def pose(self) -> Pose:
        n = self.needs
        st = self.state
        clock = self.clock
        mood = n.mood()

        eyes, mouth = "open", "classic"
        blush = tear = False
        bob = 1 if (clock % 2.6) > 1.3 else 0
        lift_l = lift_r = sit = 0
        tint = "gold" if n.has("dourado") else None

        if mood == "feliz":
            eyes = "glint"
        elif mood == "chateado":
            eyes = "sad"
        elif mood == "péssimo":
            eyes, tear = "sad", True
        elif mood == "irritado":
            eyes = "angry"
        elif mood == "emburrado":
            eyes = "half"
        if n["sono"] < 25:
            eyes = "half"
        if n.has("enjoado"):
            eyes, mouth, tint = "squint", "wavy", "sick"

        lx, ly = self._look()
        if mood == "emburrado" and self.cursor is not None:
            lx = -lx or 1  # emburrado: desvia o olhar de você

        walking = st == "walk" or (st == "exercise" and self.data.get("kind") in ("caminhar", "correr", "gato")
                                   and self.data.get("phase") != "longe")
        if walking:
            rate = 4.0 if st == "walk" else 7.0
            phase = (clock * rate) % 1.0
            lift_l, lift_r = (2, 0) if phase < 0.5 else (0, 2)
            bob = 1 if phase % 0.5 < 0.25 else 0

        if st == "sit" or (st == "exercise" and self.data.get("kind") == "descansar"):
            sit, bob = 5, 0
        elif st == "sleep":
            eyes, sit, mouth = "closed", 5, "classic"
            bob = 1 if (clock % 3.2) > 1.6 else 0
        elif st == "eat":
            eyes = "happy"
            mouth = "open" if (self.t * 4) % 1 < 0.5 else "chew"
        elif st == "drink":
            eyes, mouth = "closed", "o"
        elif st == "hiss":
            eyes, mouth = "angry", "hiss"
        elif st in ("dragged", "fall"):
            eyes, mouth, bob = "wide", "o", 0
        elif st == "exercise":
            kind = self.data.get("kind")
            if kind == "correr":
                eyes = "angry"
            elif kind == "pular":
                eyes = "happy"
            elif kind == "flexao":
                cyc = 0.5 - 0.5 * math.cos(self.t * math.tau / 1.1)
                sit = int(round(cyc * 6))
                eyes = "squint" if cyc > 0.6 else "angry"
            elif kind == "dancar":
                eyes, blush = "happy", True
                lift_l, lift_r = (2, 0) if (self.t * 3) % 1 < 0.5 else (0, 2)
            elif kind == "gato":
                eyes, mouth = "wide", "o"
            elif kind == "minerar":
                eyes, lx, ly = ("squint" if self.tool_angle > 30 else "angry"), self.facing, 1
            elif kind == "pescar":
                phase = self.data.get("phase")
                eyes = "wide" if phase in ("fisgou", "puxar") else "half"
                mouth = "o" if phase == "fisgou" else mouth
                lx = self.facing
            elif kind == "plantar":
                eyes, lx, ly = "happy", self.facing, 1
            elif kind == "porco":
                sit, bob, eyes, blush = 5, 0, "happy", True
            elif kind == "fogos":
                eyes, ly, blush = "wide", -1, True
        elif st == "leap":
            eyes, mouth, lift_l, lift_r, bob = "wide", "o", 2, 2, 0
        elif st in ("come", "fetch"):
            eyes, blush = "happy", True
            if st == "come" or self.data.get("phase") != "wait":   # correndo
                phase = (clock * 7.0) % 1.0
                lift_l, lift_r = (2, 0) if phase < 0.5 else (0, 2)
        elif st == "hide":
            eyes = "glint" if self.data.get("phase") == "escondido" else "closed"
            mouth = "smile"

        if clock < self.happy_until and st not in ("sleep", "hiss"):
            eyes, blush = "happy", True
        if clock < self.flinch_until:
            eyes = "squint"
        if clock < self.dizzy_until:
            eyes, mouth = "x", "o"
        if clock < self.blink_until and eyes in ("open", "glint", "sad", "angry", "wide"):
            eyes = "closed"

        return Pose(
            eyes=eyes, mouth=mouth, look_x=lx, look_y=ly, blush=blush, tear=tear,
            bob=bob, lift_l=lift_l, lift_r=lift_r, sit=sit, singed=n.has("chamuscado"),
            tint=tint, flash=round(self.flash * 10) / 10 if st == "hiss" else 0.0,
            skin=self.settings.skin or None)

    # ---- persistência ----------------------------------------------------
    def to_dict(self) -> dict:
        return {"needs": self.needs.to_dict(), "x": self.x, "progress": self.progress.to_dict()}
