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
BUSY = {"eat", "drink", "exercise", "hiss", "exploded", "dragged", "fall"}
NO_INTERACTION = {"hiss", "exploded", "dragged", "fall"}

GRAVITY = 2200.0


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
        self.held: str | None = None   # ícone do item que está comendo/bebendo
        self.hidden = False            # invisível (explodiu / fugiu do gato)

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
    def sprite_w(self) -> int:
        return 16 * self.s

    @property
    def sprite_h(self) -> int:
        return 40 * self.s

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

        getattr(self, f"_u_{self.state}")(dt)

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
        if self.state in ("dragged", "fall", "exploded"):
            return
        if self.state == "exercise" and self.data.get("kind") == "gato":
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
        r = random.random()
        if n["energia"] < 25 and r < 0.5:
            self.set_state("sit", dur=random.uniform(20, 45))
            return
        if r < 0.5:
            target = self._clamp_x(self.x + random.uniform(-450, 450))
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
        if item.get("status"):
            n.add_effect(item["status"])
        verb = "comer" if item["categoria"] == "comidas" else "beber"
        prog = self.progress
        prog.bump("comeu" if verb == "comer" else "bebeu")
        prog.collect(item["categoria"], item["id"])
        if item["id"] == "maca_dourada":
            prog.bump("maca_dourada")
        self._xp_fx(prog.care(verb))
        if item.get("status") in ("dourado", "velocidade"):
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
        if cured:
            self.line("leite_cura")
        elif not self.line(f"{verb}_{item['id']}"):
            self.line(verb)

    def _u_exercise(self, dt: float) -> None:
        kind = self.data["kind"]
        getattr(self, f"_x_{kind}")(dt)

    def _x_caminhar(self, dt: float) -> None:
        if "target" not in self.data or self._walk_towards(self.data["target"], self.walk_speed() * 1.2, dt):
            self.data["target"] = self._clamp_x(self.x + random.choice((-1, 1)) * random.uniform(150, 500))
        if self.t >= self.data["dur"]:
            self._finish_exercise()

    def _x_correr(self, dt: float) -> None:
        left, _, right, _ = self.world
        if "target" not in self.data or self._walk_towards(self.data["target"], self.walk_speed() * 3.2, dt):
            m = self._margin()
            self.data["target"] = right - m if self.x < (left + right) / 2 else left + m
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
        self.x = self._clamp_x(self.x + math.cos(self.t * 2.5) * 40 * dt)
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
                    "icon", x=side * (self.sprite_w + 30), y=0, life=4.5, text="gato", size=2 * self.s))
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

    def _finish_exercise(self) -> None:
        kind = self.data["kind"]
        self.needs.apply(self.items.get(kind).get("efeitos"))
        prog = self.progress
        prog.bump("atividades")
        prog.collect("atividades", kind)
        if kind in ("dancar", "gato"):
            prog.bump("dancou" if kind == "dancar" else "gato")
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
        h = self.sprite_h
        for _ in range(46):
            ang = random.uniform(0, math.tau)
            spd = random.uniform(150, 520)
            self.particles.append(Particle(
                "debris", x=random.uniform(-0.4, 0.4) * self.sprite_w, y=-random.uniform(0.1, 0.9) * h,
                vx=math.cos(ang) * spd, vy=math.sin(ang) * spd - 220, gravity=1300,
                life=random.uniform(1.2, 2.2), color=random.choice(("#3FA535", "#55BC48", "#2F8A28", "#74D166", "#1F6B1C")),
                size=random.choice((1, 2, 2, 3)) * self.s))
        for _ in range(16):
            ang = random.uniform(0, math.tau)
            spd = random.uniform(20, 120)
            self.particles.append(Particle(
                "smoke", x=random.uniform(-0.5, 0.5) * self.sprite_w, y=-random.uniform(0.2, 0.8) * h,
                vx=math.cos(ang) * spd, vy=math.sin(ang) * spd - 40, life=random.uniform(1.2, 2.0),
                color=random.choice(("#EEEEEE", "#BDBDBD", "#9E9E9E")), size=random.uniform(8, 18) * self.s / 3))
        self.particles.append(Particle("boom", x=0, y=-h / 2, life=0.35, size=h * 1.2))
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
        self.vy += GRAVITY * dt
        self.y += self.vy * dt
        self.x += self.vx * dt
        self.vx *= max(0.0, 1 - 2.5 * dt)
        if self.x < left + self.sprite_w / 2 or self.x > right - self.sprite_w / 2:
            self.vx = -self.vx * 0.5
            self.x = max(left + self.sprite_w / 2, min(right - self.sprite_w / 2, self.x))
        self.tilt *= max(0.0, 1 - 6 * dt)
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

    def do_activity(self, act_id: str) -> None:
        item = self.items.get(act_id)
        if not self.can_interact() or self.busy() or not self.progress.unlocked(item):
            return
        if self.state == "sleep":
            self.wake(forced=True)
        if self.needs["energia"] < 15 and act_id not in ("descansar", "gato"):
            self.line("atividade_cansado", "reaction")
            return
        self.set_state("exercise", kind=act_id, dur=float(item.get("duracao", 10)))
        if act_id != "gato":
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
        if self.state in ("exploded", "hiss") or self.hidden:
            return False
        if self.state == "sleep":
            self.wake(forced=True)
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
        if self.state in ("sleep", "exploded", "hiss", "dragged", "fall", "eat", "drink") or self.hidden:
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

    # ---- progresso -------------------------------------------------------
    def _on_progress(self, event: tuple) -> None:
        kind = event[0]
        if kind == "level":
            _, level, unlocked = event
            if unlocked:
                self.line("desbloqueou", "reaction", nivel=level, itens=", ".join(i["nome"] for i in unlocked))
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
            tint=tint, flash=round(self.flash * 10) / 10 if st == "hiss" else 0.0)

    # ---- persistência ----------------------------------------------------
    def to_dict(self) -> dict:
        return {"needs": self.needs.to_dict(), "x": self.x, "progress": self.progress.to_dict()}
