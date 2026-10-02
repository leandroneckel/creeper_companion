"""Progresso: XP, níveis, estoque dos itens limitados, presentes e conquistas.

Não sabe nada de janela nem de sons: só guarda números e enfileira eventos
(subiu de nível, conquista, presente achado...) que o Pet transforma em reação.
"""
import random
import time
from datetime import date, timedelta

# Fontes de XP
TIME_XP_PER_MIN = 1.0        # app aberto e você usando o PC
WELL_XP_PER_MIN = 0.5        # bônus enquanto ele está bem cuidado
WELL_THRESHOLD = 70.0        # bem-estar mínimo pro bônus
NEGLECT_XP_PER_MIN = 2.0     # perda enquanto alguma necessidade está crítica (nunca rebaixa de nível)
NEGLECT_THRESHOLD = 15.0
CARE_XP = {"comer": 6, "beber": 5, "atividade": 10, "gato": 3, "carinho": 1}
CARE_BUDGET = 60             # XP de cuidados por hora, no máximo: não dá pra subir de nível só clicando
SELF_CARE_XP = {"agua": 15, "pausa": 20}
PRESENT_EVERY = (2 * 3600, 4 * 3600)   # tempo de uso entre presentes achados
PRESENT_XP = 50              # presente que vem "só" com XP
PRESENT_XP_CHANCE = 0.25


def xp_to_next(level: int) -> int:
    """XP pra passar de `level` pro próximo. Os primeiros níveis saem em horas;
    do 20 em diante, cerca de um dia de uso cada (tudo desbloqueado em ~1 mês)."""
    return min(1200, 60 * level + 40)


class Progress:
    def __init__(self, items, achievements: list[dict]):
        self.items = items
        self.achievements = achievements
        self.level = 1
        self.xp = 0.0                    # XP dentro do nível atual
        self.total_xp = 0.0
        self.inventory: dict[str, int] = {}
        self.presents = 0                # presentes esperando pra ser abertos
        self.counters: dict[str, int] = {}
        self.seen: dict[str, list[str]] = {}
        self.done: dict[str, float] = {}  # conquista -> quando foi feita
        self.care_budget = float(CARE_BUDGET)
        self.active_time = 0.0
        self.next_present = random.uniform(*PRESENT_EVERY)
        self.last_day = ""
        self.water_day = ""
        self.water_streak = 0
        self.losing = False
        self.events: list[tuple] = []
        self._fill_inventory()

    def _fill_inventory(self) -> None:
        """Itens limitados que ainda não estão no estoque (save novo ou item novo) ganham as unidades iniciais."""
        for item in self.items.limited():
            self.inventory.setdefault(item["id"], int(item["limitado"].get("inicial", 0)))

    # ---- XP e níveis -----------------------------------------------------
    @property
    def needed(self) -> int:
        return xp_to_next(self.level)

    def fraction(self) -> float:
        return min(1.0, self.xp / self.needed)

    def add_xp(self, amount: float) -> None:
        if amount <= 0:
            return
        self.xp += amount
        self.total_xp += amount
        while self.xp >= self.needed:
            self.xp -= self.needed
            self.level += 1
            self.presents += 1           # todo nível traz um presente
            unlocked = [i for i in self.items.all() if i.get("nivel") == self.level]
            self.events.append(("level", self.level, unlocked))
            self.record("nivel", self.level)

    def lose_xp(self, amount: float) -> None:
        self.xp = max(0.0, self.xp - amount)

    def care(self, kind: str) -> int:
        """XP por cuidar dele, limitado por hora. Devolve quanto ganhou."""
        gain = min(CARE_XP.get(kind, 0), int(self.care_budget))
        if gain <= 0:
            return 0
        self.care_budget -= gain
        self.add_xp(gain)
        return gain

    def self_care(self, kind: str) -> int:
        """Você apertou "Fiz!" num lembrete (agua ou pausa)."""
        gain = SELF_CARE_XP[kind]
        if kind == "agua":
            today = date.today()
            if self.water_day != today.isoformat():
                yesterday = (today - timedelta(days=1)).isoformat()
                self.water_streak = self.water_streak + 1 if self.water_day == yesterday else 1
                self.water_day = today.isoformat()
                self.record("agua_seguidos", self.water_streak)
            self.bump("agua_feita")
        else:
            self.bump("pausas_feitas")
        self.add_xp(gain)
        return gain

    def tick(self, dt: float, active: bool, needs) -> None:
        """Chamado periodicamente: XP pelo tempo junto, bônus/perda conforme o cuidado, presentes."""
        minutes = dt / 60.0
        self.care_budget = min(float(CARE_BUDGET), self.care_budget + CARE_BUDGET * dt / 3600.0)
        critical = needs.worst()[1] < NEGLECT_THRESHOLD
        if critical:
            if not self.losing:
                self.events.append(("losing",))
            self.losing = True
            self.lose_xp(NEGLECT_XP_PER_MIN * minutes)
        else:
            self.losing = False
        if not active:
            return
        today = date.today().isoformat()
        if today != self.last_day:
            self.last_day = today
            self.bump("dias_juntos")
        gain = TIME_XP_PER_MIN * minutes
        if not critical and not needs.sulking() and needs.wellbeing() >= WELL_THRESHOLD:
            gain += WELL_XP_PER_MIN * minutes
        self.add_xp(gain)
        if min(needs.values.values()) >= 90:
            self.record("tudo_cheio", 1)
        self.active_time += dt
        if self.active_time >= self.next_present and needs.mood() in ("feliz", "de boa"):
            self.active_time = 0.0
            self.next_present = random.uniform(*PRESENT_EVERY)
            self.presents += 1
            self.events.append(("present",))

    # ---- itens e presentes -----------------------------------------------
    def unlocked(self, item: dict) -> bool:
        return int(item.get("nivel", 1)) <= self.level

    def stock(self, item: dict) -> int | None:
        """Quantas unidades tem, ou None se o item é infinito."""
        if not item.get("limitado"):
            return None
        return self.inventory.get(item["id"], 0)

    def take(self, item: dict) -> bool:
        """Gasta uma unidade (se for limitado). False se acabou."""
        left = self.stock(item)
        if left is None:
            return True
        if left <= 0:
            return False
        self.inventory[item["id"]] = left - 1
        return True

    def random_special(self) -> dict | None:
        """Sorteia um item limitado já desbloqueado (pelo peso de cada um)."""
        pool = [i for i in self.items.limited() if self.unlocked(i)]
        if not pool:
            return None
        return random.choices(pool, weights=[float(i["limitado"].get("peso", 1)) for i in pool])[0]

    def give(self, item_id: str, qty: int = 1) -> None:
        self.inventory[item_id] = self.inventory.get(item_id, 0) + qty

    def open_present(self) -> tuple[str, int] | None:
        """Abre um presente: ("xp", quantidade) ou (id do item, quantidade)."""
        if self.presents <= 0:
            return None
        self.presents -= 1
        item = self.random_special()
        if item is None or random.random() < PRESENT_XP_CHANCE:
            result = ("xp", PRESENT_XP)
            self.add_xp(PRESENT_XP)
        else:
            qty = int(item["limitado"].get("presente", 1))
            self.give(item["id"], qty)
            result = (item["id"], qty)
        self.bump("presentes")
        return result

    # ---- contadores e conquistas -----------------------------------------
    def bump(self, counter: str, by: int = 1) -> None:
        self.counters[counter] = self.counters.get(counter, 0) + by
        self._check()

    def record(self, counter: str, value: int) -> None:
        """Guarda o maior valor já visto (nível, dias seguidos...)."""
        if value > self.counters.get(counter, 0):
            self.counters[counter] = value
            self._check()

    def collect(self, kind: str, item_id: str) -> None:
        """Conta itens diferentes (comidas_diferentes, atividades_diferentes...)."""
        seen = self.seen.setdefault(kind, [])
        if item_id not in seen:
            seen.append(item_id)
            self.record(f"{kind}_diferentes", len(seen))

    def _check(self) -> None:
        for ach in self.achievements:
            if ach["id"] in self.done:
                continue
            if self.counters.get(ach.get("contador"), 0) >= int(ach.get("meta", 1)):
                self.done[ach["id"]] = time.time()
                self.events.append(("achievement", ach))
                self.add_xp(float(ach.get("xp", 0)))

    def drain(self) -> list[tuple]:
        events, self.events = self.events, []
        return events

    # ---- persistência ----------------------------------------------------
    def to_dict(self) -> dict:
        return {
            "level": self.level, "xp": self.xp, "total_xp": self.total_xp,
            "inventory": self.inventory, "presents": self.presents,
            "counters": self.counters, "seen": self.seen, "done": self.done,
            "care_budget": self.care_budget, "active_time": self.active_time,
            "next_present": self.next_present, "last_day": self.last_day,
            "water_day": self.water_day, "water_streak": self.water_streak,
        }

    @classmethod
    def from_dict(cls, data: dict | None, items, achievements: list[dict]) -> "Progress":
        prog = cls(items, achievements)
        if not data:
            return prog
        prog.level = max(1, int(data.get("level", 1)))
        prog.xp = max(0.0, float(data.get("xp", 0)))
        prog.total_xp = float(data.get("total_xp", 0))
        prog.inventory = {k: max(0, int(v)) for k, v in (data.get("inventory") or {}).items()}
        prog.presents = max(0, int(data.get("presents", 0)))
        prog.counters = {k: int(v) for k, v in (data.get("counters") or {}).items()}
        prog.seen = {k: list(v) for k, v in (data.get("seen") or {}).items()}
        prog.done = {k: float(v) for k, v in (data.get("done") or {}).items()}
        prog.care_budget = min(float(CARE_BUDGET), float(data.get("care_budget", CARE_BUDGET)))
        prog.active_time = float(data.get("active_time", 0))
        prog.next_present = float(data.get("next_present", prog.next_present))
        prog.last_day = str(data.get("last_day", ""))
        prog.water_day = str(data.get("water_day", ""))
        prog.water_streak = int(data.get("water_streak", 0))
        prog._fill_inventory()
        prog._check()   # conquistas novas no YAML que já estavam cumpridas
        return prog
