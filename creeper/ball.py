"""A bolinha que você joga e ele busca: só a física (sem Qt).

Ela quica no chão (a barra de tarefas) e nas bordas da tela. Atravessa as janelas, como se
estivesse "na área de trabalho", pra ele sempre conseguir buscar.
"""
import math

GRAVITY = 1800.0
BOUNCE = 0.55        # quanto da velocidade sobra no quique
RADIUS = 9.0


class Ball:
    def __init__(self):
        self.active = False      # está em jogo (visível ou na boca dele)
        self.held = "none"       # none | user (arrastando) | pet (na boca dele)
        self.x = self.y = 0.0    # centro, coordenadas da tela
        self.vx = self.vy = 0.0
        self.world = (0.0, 0.0, 1920.0, 1040.0)   # esquerda, topo, direita, chão
        self.thrown_from = 0.0   # x de onde você jogou (é pra lá que ele devolve)
        self.on_bounce = lambda strength: None

    @property
    def resting(self) -> bool:
        return self.held == "none" and self.on_ground and abs(self.vx) < 15

    @property
    def on_ground(self) -> bool:
        return self.y >= self.world[3] - RADIUS - 0.5

    def place(self, x: float, y: float) -> None:
        self.active, self.held = True, "none"
        self.x, self.y, self.vx, self.vy = x, y, 0.0, 0.0

    def throw(self, vx: float, vy: float) -> None:
        self.held = "none"
        limit = 2200.0
        speed = math.hypot(vx, vy)
        if speed > limit:
            vx, vy = vx * limit / speed, vy * limit / speed
        self.vx, self.vy = vx, vy
        self.thrown_from = self.x

    def update(self, dt: float) -> None:
        if not self.active or self.held != "none":
            return
        left, top, right, ground = self.world
        self.vy += GRAVITY * dt
        self.x += self.vx * dt
        self.y += self.vy * dt
        if self.y >= ground - RADIUS:
            self.y = ground - RADIUS
            if self.vy > 120:
                self.on_bounce(min(1.0, self.vy / 1400))
                self.vy = -self.vy * BOUNCE
            else:
                self.vy = 0.0
            self.vx *= max(0.0, 1 - 2.5 * dt)        # rola e vai parando
            if abs(self.vx) < 8:
                self.vx = 0.0
        if self.y < top + RADIUS:
            self.y, self.vy = top + RADIUS, abs(self.vy) * BOUNCE
        if self.x < left + RADIUS or self.x > right - RADIUS:
            self.x = max(left + RADIUS, min(right - RADIUS, self.x))
            self.vx = -self.vx * BOUNCE
            self.on_bounce(min(1.0, abs(self.vx) / 1400))
