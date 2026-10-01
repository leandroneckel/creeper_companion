"""Necessidades, efeitos temporários e humor do creeper.

Todas as necessidades vão de 0 a 100, onde 100 = totalmente satisfeito
(barriga cheia, hidratado, cheio de energia, descansado, animado).
"""
import time
from datetime import datetime

STATS = ("fome", "sede", "energia", "sono", "diversao")

LABELS = {
    "fome": "Fome",
    "sede": "Sede",
    "energia": "Energia",
    "sono": "Sono",
    "diversao": "Diversão",
}

# Palavra que descreve o nível de cada necessidade: [<15, <40, <75, resto]
LEVEL_WORDS = {
    "fome": ("faminto", "com fome", "ok", "satisfeito"),
    "sede": ("desidratado", "com sede", "ok", "hidratado"),
    "energia": ("exausto", "cansado", "ok", "cheio de energia"),
    "sono": ("caindo de sono", "com sono", "ok", "descansado"),
    "diversao": ("morrendo de tédio", "entediado", "ok", "animado"),
}

# Efeitos temporários e sua duração em segundos.
EFFECTS = {
    "dourado": 10 * 60,
    "enjoado": 10 * 60,
    "cafeinado": 20 * 60,
    "velocidade": 3 * 60,
    "chamuscado": 10 * 60,
}
BAD_EFFECTS = {"enjoado", "cafeinado"}
EFFECT_LABELS = {
    "dourado": "brilhando",
    "enjoado": "enjoado",
    "cafeinado": "cafeinado",
    "velocidade": "veloz",
    "chamuscado": "chamuscado",
}

# Taxas em pontos por hora (com velocidade 1.0).
DECAY_FOOD = 10.0
DECAY_WATER = 14.0
DECAY_FUN = 9.0
SLEEPINESS_DAY = 6.0
SLEEPINESS_NIGHT = 10.0
SLEEP_RESTORE = 60.0
ENERGY_IDLE = 8.0
ENERGY_SIT = 30.0
ENERGY_SLEEP = 40.0
ENERGY_WALK = -4.0

# Irritação: sobe com maus-tratos, cai com o tempo. Em 100 ele chia.
ANNOYANCE_DECAY_PER_MIN = 3.0
NEGLECT_ANNOYANCE_PER_MIN = 1.0
NEGLECT_CAP = 85.0  # descuido sozinho não faz explodir; precisa de um cutucão


def is_night(now: float | None = None) -> bool:
    hour = datetime.fromtimestamp(now or time.time()).hour
    return hour >= 22 or hour < 7


def clamp(value: float, lo: float = 0.0, hi: float = 100.0) -> float:
    return max(lo, min(hi, value))


class Needs:
    def __init__(self):
        self.values = {stat: 80.0 for stat in STATS}
        self.effects: dict[str, float] = {}  # nome -> expira em (epoch)
        self.annoyance = 0.0
        self.sulk_until = 0.0

    # ---- consultas -------------------------------------------------------
    def __getitem__(self, stat: str) -> float:
        return self.values[stat]

    def has(self, effect: str) -> bool:
        return self.effects.get(effect, 0) > time.time()

    def sulking(self) -> bool:
        return self.sulk_until > time.time()

    def wellbeing(self) -> float:
        vals = list(self.values.values())
        return 0.6 * (sum(vals) / len(vals)) + 0.4 * min(vals)

    def mood(self) -> str:
        if self.sulking():
            return "emburrado"
        if self.annoyance >= 60:
            return "irritado"
        w = self.wellbeing()
        if w >= 75:
            return "feliz"
        if w >= 50:
            return "de boa"
        if w >= 30:
            return "chateado"
        return "péssimo"

    def level_word(self, stat: str) -> str:
        v = self.values[stat]
        idx = 0 if v < 15 else 1 if v < 40 else 2 if v < 75 else 3
        return LEVEL_WORDS[stat][idx]

    def worst(self) -> tuple[str, float]:
        stat = min(self.values, key=self.values.get)
        return stat, self.values[stat]

    def active_effects(self) -> list[str]:
        now = time.time()
        return [e for e, until in self.effects.items() if until > now]

    # ---- mudanças --------------------------------------------------------
    def apply(self, deltas: dict) -> None:
        for stat, delta in (deltas or {}).items():
            if stat in self.values:
                self.values[stat] = clamp(self.values[stat] + float(delta))

    def add_effect(self, effect: str, seconds: float | None = None) -> None:
        self.effects[effect] = time.time() + (seconds or EFFECTS.get(effect, 300))

    def cure(self) -> bool:
        cured = [e for e in BAD_EFFECTS if self.has(e)]
        for e in cured:
            self.effects.pop(e, None)
        return bool(cured)

    def annoy(self, amount: float) -> None:
        self.annoyance = clamp(self.annoyance + amount)

    def sulk(self, seconds: float) -> None:
        self.sulk_until = max(self.sulk_until, time.time() + seconds)

    def reduce_sulk(self, seconds: float) -> bool:
        """Diminui o tempo emburrado. Retorna True se ele desemburrou agora."""
        if not self.sulking():
            return False
        self.sulk_until -= seconds
        return not self.sulking()

    def tick(self, dt: float, activity: str, speed: float = 1.0) -> list[str]:
        """Avança o tempo. Retorna efeitos que acabaram de expirar."""
        now = time.time()
        h = dt / 3600.0
        v = self.values
        sleeping = activity == "sleep"
        golden = self.has("dourado")
        decay = 0.0 if golden else speed

        body = 0.5 if sleeping else 1.0
        v["fome"] -= DECAY_FOOD * h * decay * body
        v["sede"] -= DECAY_WATER * h * decay * body
        if not sleeping:
            fun = DECAY_FUN * (2.0 if self.has("enjoado") else 1.0)
            v["diversao"] -= fun * h * decay

        if sleeping:
            v["energia"] += ENERGY_SLEEP * h
        elif activity == "sit":
            v["energia"] += ENERGY_SIT * h
        elif activity == "walk":
            v["energia"] += ENERGY_WALK * h * decay
        elif activity == "idle":
            v["energia"] += ENERGY_IDLE * h

        caffeine = self.has("cafeinado")
        if sleeping:
            v["sono"] += SLEEP_RESTORE * h * (0.5 if caffeine else 1.0)
        elif not caffeine:
            rate = SLEEPINESS_NIGHT if is_night(now) else SLEEPINESS_DAY
            v["sono"] -= rate * h * decay

        for stat in STATS:
            v[stat] = clamp(v[stat])

        minutes = dt / 60.0
        if self.wellbeing() < 25 and not sleeping:
            if self.annoyance < NEGLECT_CAP:
                self.annoyance = min(NEGLECT_CAP, self.annoyance + NEGLECT_ANNOYANCE_PER_MIN * minutes)
        else:
            self.annoyance = clamp(self.annoyance - ANNOYANCE_DECAY_PER_MIN * minutes)

        expired = [e for e, until in self.effects.items() if until <= now]
        for e in expired:
            del self.effects[e]
        return expired

    def apply_offline(self, elapsed: float, speed: float = 1.0) -> None:
        """Aplica o tempo em que o app ficou fechado, de forma bem mais suave."""
        if elapsed <= 0:
            return
        hours = min(elapsed, 3 * 24 * 3600) / 3600.0
        soft = 0.35 * speed
        v = self.values
        for stat, rate in (("fome", DECAY_FOOD), ("sede", DECAY_WATER), ("diversao", DECAY_FUN)):
            floor = min(v[stat], 15.0)
            v[stat] = max(floor, v[stat] - rate * hours * soft)
        v["energia"] = clamp(v["energia"] + ENERGY_IDLE * hours)
        if hours >= 6:
            v["sono"] = 100.0  # dormiu enquanto você estava fora
        else:
            v["sono"] = max(min(v["sono"], 15.0), v["sono"] - SLEEPINESS_DAY * hours * soft)
        if hours >= 1:
            self.annoyance = 0.0
        now = time.time()
        self.effects = {e: t for e, t in self.effects.items() if t > now}

    # ---- persistência ----------------------------------------------------
    def to_dict(self) -> dict:
        return {
            "values": self.values,
            "effects": self.effects,
            "annoyance": self.annoyance,
            "sulk_until": self.sulk_until,
        }

    @classmethod
    def from_dict(cls, data: dict | None) -> "Needs":
        needs = cls()
        if not data:
            return needs
        for stat, value in (data.get("values") or {}).items():
            if stat in needs.values:
                needs.values[stat] = clamp(float(value))
        needs.effects = {k: float(v) for k, v in (data.get("effects") or {}).items()}
        needs.annoyance = clamp(float(data.get("annoyance", 0)))
        needs.sulk_until = float(data.get("sulk_until", 0))
        return needs
