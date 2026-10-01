"""Sons do creeper, sintetizados por código. Nenhum áudio do Minecraft é usado.

Python puro (sem numpy): cada som é uma lista de amostras float em -1..1, mono,
a SR Hz. render(nome) devolve o WAV pronto. Gerar tudo leva perto de um segundo,
por isso o player guarda os WAV em cache.
"""
import io
import math
import random
import sys
import wave
from array import array

SR = 22050
TAU = math.tau


def _len(sec: float) -> int:
    return max(1, int(sec * SR))


def _fn(value):
    """Número ou função de u (0..1 ao longo do som) -> função de u."""
    return value if callable(value) else (lambda _u: value)


# ---- blocos básicos ---------------------------------------------------------
def _blep(p: float, dt: float) -> float:
    """Correção polyBLEP: tira o chiado de aliasing das ondas com degrau."""
    if p < dt:
        x = p / dt
        return x + x - x * x - 1
    if p > 1 - dt:
        x = (p - 1) / dt
        return x * x + x + x + 1
    return 0.0


def osc(dur: float, freq, shape: str = "sine", vibrato: float = 0.0, vib_rate: float = 6.0) -> list:
    """Oscilador. freq pode ser função de u; vibrato é a profundidade relativa."""
    n = _len(dur)
    f = _fn(freq)
    sin = math.sin
    out = [0.0] * n
    phase = 0.0
    for i in range(n):
        hz = f(i / n)
        if vibrato:
            hz *= 1 + vibrato * sin(TAU * vib_rate * i / SR)
        dt = hz / SR
        phase = (phase + dt) % 1.0
        if shape == "sine":
            out[i] = sin(TAU * phase)
        elif shape == "saw":
            out[i] = 2 * phase - 1 - _blep(phase, dt)
        elif shape == "square":
            out[i] = (1.0 if phase < 0.5 else -1.0) + _blep(phase, dt) - _blep((phase + 0.5) % 1.0, dt)
        else:  # triangular
            out[i] = 4 * abs(phase - 0.5) - 1
    return out


def noise(dur: float, rng: random.Random) -> list:
    r = rng.random
    return [r() * 2 - 1 for _ in range(_len(dur))]


def svf(x: list, cutoff, q: float = 0.707, mode: str = "low") -> list:
    """Filtro de estado variável (TPT): passa-baixa, passa-banda ou passa-alta.

    cutoff pode ser função de u; nesse caso os coeficientes são refeitos a cada 16 amostras.
    """
    n = len(x)
    f = _fn(cutoff)
    k = 1 / q
    tan = math.tan
    ic1 = ic2 = 0.0
    a1 = a2 = a3 = 0.0
    out = [0.0] * n
    for i in range(n):
        if i == 0 or (callable(cutoff) and (i & 15) == 0):
            g = tan(math.pi * min(f(i / n), SR * 0.45) / SR)
            a1 = 1 / (1 + g * (g + k))
            a2 = g * a1
            a3 = g * a2
        v0 = x[i]
        v3 = v0 - ic2
        v1 = a1 * ic1 + a2 * v3
        v2 = ic2 + a2 * ic1 + a3 * v3
        ic1 = 2 * v1 - ic1
        ic2 = 2 * v2 - ic2
        if mode == "low":
            out[i] = v2
        elif mode == "band":
            out[i] = k * v1        # ganho 1 no centro
        else:
            out[i] = v0 - k * v1 - v2
    return out


def decay_env(dur: float, attack: float, tau: float, hold: float = 0.0) -> list:
    """Sobe em `attack` s, segura `hold` s e cai exponencialmente (constante `tau` s)."""
    n = _len(dur)
    a = max(1, int(attack * SR))
    h = a + int(hold * SR)
    r = math.exp(-1 / (tau * SR))
    out = [0.0] * n
    v = 1.0
    for i in range(n):
        if i < a:
            out[i] = i / a
        elif i < h:
            out[i] = 1.0
        else:
            out[i] = v
            v *= r
    return out


def ar_env(dur: float, attack: float, release: float) -> list:
    """Sobe em `attack` s, fica no máximo e some suavemente nos últimos `release` s."""
    n = _len(dur)
    a = max(1, int(attack * SR))
    r = max(1, int(release * SR))
    out = [1.0] * n
    for i in range(min(a, n)):
        out[i] = i / a
    for j in range(min(r, n)):
        out[n - 1 - j] *= 0.5 - 0.5 * math.cos(math.pi * j / r)
    return out


def mul(x: list, y: list) -> list:
    return [a * b for a, b in zip(x, y)]


def add_at(base: list, x: list, start: float = 0.0, gain: float = 1.0) -> list:
    """Soma x em base a partir de `start` s (aumenta base se precisar)."""
    s = int(start * SR)
    if len(base) < s + len(x):
        base.extend([0.0] * (s + len(x) - len(base)))
    for i, v in enumerate(x):
        base[s + i] += v * gain
    return base


def partials(freq: float, dur: float, tau: float, parts, tau_exp: float = 0.6, attack: float = 0.002) -> list:
    """Soma de senoides que decaem (sino, harpa). Parciais mais agudas somem antes."""
    n = _len(dur)
    out = [0.0] * n
    sin = math.sin
    for mult, amp in parts:
        f = freq * mult
        if f >= SR * 0.45:
            continue
        w = TAU * f / SR
        r = math.exp(-1 / (tau / mult ** tau_exp * SR))
        a = amp
        for i in range(n):
            out[i] += a * sin(w * i)
            a *= r
    return fade(out, attack, 0.03)


def fade(x: list, fade_in: float = 0.002, fade_out: float = 0.01) -> list:
    """Rampas curtas nas pontas pra não estalar."""
    n = len(x)
    a, r = min(n, max(1, int(fade_in * SR))), min(n, max(1, int(fade_out * SR)))
    for i in range(a):
        x[i] *= i / a
    for j in range(r):
        x[n - 1 - j] *= j / r
    return x


def loudness_db(x: list) -> float:
    """Volume aproximado: o trecho de 50 ms mais forte (graves abaixo de ~150 Hz contam pouco,
    já que caixinhas de som de notebook nem tocam)."""
    hp = svf(x, 150, 0.707, "high")
    w = _len(0.05)
    acc = [0.0]
    total = 0.0
    for v in hp:
        total += v * v
        acc.append(total)
    best = max((acc[min(i + w, len(hp))] - acc[i]) for i in range(0, max(1, len(hp) - w + 1), _len(0.005)))
    return 10 * math.log10(max(best / w, 1e-12))


def level(x: list, target_db: float, peak: float = 0.95) -> list:
    """Ajusta o volume pro alvo, sem deixar passar do pico (nunca estoura)."""
    gain = 10 ** ((target_db - loudness_db(x)) / 20)
    top = max(abs(v) for v in x) * gain
    if top > peak:
        gain *= peak / top
    return [v * gain for v in x]


# ---- os sons ----------------------------------------------------------------
def pop(rng) -> list:
    """Item aparecendo/sendo pego: blip curto que sobe."""
    dur = 0.12
    body = osc(dur, lambda u: 320 + 780 * (1 - (1 - min(1.0, u * 2.5)) ** 2))
    return mul(body, decay_env(dur, 0.002, 0.03))


def crunch(rng, center: float) -> list:
    """Mastigar: três estalos de ruído filtrado, com textura granulada."""
    out = [0.0] * _len(0.16)
    for start, amp, tau in ((0.0, 1.0, 0.018), (0.035 + rng.uniform(-0.006, 0.006), 0.65, 0.016),
                            (0.075 + rng.uniform(-0.008, 0.008), 0.4, 0.02)):
        burst = svf(noise(0.07, rng), center * rng.uniform(0.85, 1.15), 1.4, "band")
        burst = [v if rng.random() < 0.6 else v * 0.25 for v in burst]
        add_at(out, mul(burst, decay_env(0.07, 0.002, tau)), start, amp)
    return out


def gulp(rng, f0: float) -> list:
    """Gole: bolha (tom que sobe rápido) com uma batidinha grave."""
    dur = 0.18
    bubble = osc(dur, lambda u: f0 * (1 + 1.4 * min(1.0, u * 2.2) ** 0.7))
    out = mul(bubble, decay_env(dur, 0.006, 0.045))
    thump = mul(osc(0.08, lambda u: 140 - 60 * u), decay_env(0.08, 0.002, 0.02))
    return add_at(out, thump, 0.0, 0.6)


def burp(rng) -> list:
    """Arroto: pulsos graves e irregulares passando por duas 'vogais'."""
    dur = 0.6
    wobble = [rng.uniform(-1, 1) for _ in range(13)]

    def pitch(u):
        p = u * 11
        i = int(p)
        frac = p - i
        jitter = wobble[i] * (1 - frac) + wobble[i + 1] * frac
        return (92 - 22 * u) * (1 + 0.06 * jitter)

    src = osc(dur, pitch, "saw")
    rough = osc(dur, 31)
    src = [s * (0.75 + 0.25 * r) for s, r in zip(src, rough)]
    f1 = svf(src, lambda u: 520 + 120 * math.sin(math.pi * u), 4.0, "band")
    f2 = svf(src, 1050, 5.0, "band")
    low = svf(src, 300, 0.7, "low")
    out = [a + 0.55 * b + 0.5 * c for a, b, c in zip(f1, f2, low)]
    return mul(out, ar_env(dur, 0.035, 0.18))


def boop(rng, f_start: float, f_end: float) -> list:
    """Cutucão: 'bup' que cai de tom."""
    dur = 0.13
    ratio = f_end / f_start

    def pitch(u):
        return f_start * ratio ** min(1.0, u * 1.6)

    a = osc(dur, pitch)
    b = osc(dur, lambda u: 2 * pitch(u))
    return mul([x + 0.25 * y for x, y in zip(a, b)], decay_env(dur, 0.002, 0.04))


BELL = ((1, 1.0), (2, 0.3), (3, 0.1))
GLOCK = ((1, 1.0), (2.76, 0.25), (5.4, 0.08))


def stroke(rng) -> list:
    """Carinho: 'plim-plim' suave."""
    out = partials(1046.5, 0.5, 0.14, BELL)
    return add_at(out, partials(1568.0, 0.5, 0.16, BELL), 0.07, 0.8)


def hiss(rng) -> list:
    """Chiado do pavio. Pulsa junto com o pisca-pisca branco do creeper (pet._u_hiss)."""
    dur = 2.4
    n = _len(dur)
    src = noise(dur, rng)
    hi = svf(src, 2600, 0.6, "high")
    sizzle = svf(src, 5200, 2.0, "band")
    sin = math.sin
    out = [0.0] * n
    for i in range(n):
        u = i / n
        t = i / SR
        pulse = 0.65 + 0.35 * sin(t * (6 + 22 * u))   # mesma conta do flash
        out[i] = (0.8 * hi[i] + 0.5 * sizzle[i]) * (0.35 + 0.65 * u ** 0.8) * pulse
    for _ in range(70):   # estalinhos, mais frequentes perto do fim
        start = dur * (1 - rng.random() ** 1.6) * 0.98
        tick = svf(noise(0.004, rng), 3500, 0.7, "high")
        add_at(out, mul(tick, decay_env(0.004, 0.0005, 0.0012)), start, 0.6 * (0.3 + start / dur))
    return fade(out[:n], 0.04, 0.02)


def boom(rng) -> list:
    """Explosão: estouro brilhante que escurece, ronco grave, baque e estilhaços."""
    dur = 2.2
    n = _len(dur)
    body = svf(noise(dur, rng), lambda u: 180 + 3200 * math.exp(-u * dur / 0.09), 0.8, "low")
    body = svf(body, lambda u: 220 + 4000 * math.exp(-u * dur / 0.12), 0.6, "low")
    brown, b = [], 0.0
    for v in noise(dur, rng):
        b = b * 0.985 + v * 0.15
        brown.append(b)
    rumble = svf(brown, 160, 0.7, "low")
    sub = osc(0.6, lambda u: 75 - 40 * u)
    peak_body = max(abs(v) for v in body) or 1
    peak_rumble = max(abs(v) for v in rumble) or 1
    exp = math.exp
    out = [0.0] * n
    for i in range(n):
        t = i / SR
        e_body = min(1.0, t / 0.004) * exp(-t / 0.38)
        e_rumble = min(1.0, t / 0.01) * exp(-t / 0.75)
        v = body[i] / peak_body * e_body + 0.9 * rumble[i] / peak_rumble * e_rumble
        if i < len(sub):
            v += 0.7 * sub[i] * exp(-t / 0.16)
        out[i] = v
    for _ in range(40):
        start = 1.2 * rng.random() ** 2
        length = rng.uniform(0.006, 0.015)
        chip = svf(noise(length, rng), rng.uniform(1500, 4000), 1.5, "band")
        add_at(out, mul(chip, decay_env(length, 0.0005, length / 3)), start, 0.6 * math.exp(-start / 0.3))
    out = out[:n]
    top = max(abs(v) for v in out)
    sat = math.tanh(1.8)
    return fade([math.tanh(1.8 * v / top) / sat for v in out], 0.001, 0.1)


def thud(rng) -> list:
    """Pouso: baque grave com um 'tuc' de ruído (o grave nem toca em notebook)."""
    dur = 0.25
    body = mul(osc(dur, lambda u: 120 * (50 / 120) ** min(1.0, u * 2)), decay_env(dur, 0.002, 0.06))
    tuc = mul(svf(noise(dur, rng), 900, 0.7, "low"), decay_env(dur, 0.001, 0.025))
    return [a + b for a, b in zip(body, tuc)]


def boing(rng) -> list:
    """Pulo: mola."""
    dur = 0.3
    s = osc(dur, lambda u: 210 + 380 * u ** 0.6, "tri", vibrato=0.05, vib_rate=16)
    return mul(s, decay_env(dur, 0.004, 0.09))


HARP = tuple((k, 1 / k ** 1.4) for k in range(1, 7))
# Escala pentatônica de dó (C5 a E6): qualquer sequência soa bem.
NOTES = (523.25, 587.33, 659.26, 783.99, 880.0, 1046.5, 1174.66, 1318.51)


def pluck(rng, freq: float) -> list:
    """Nota dedilhada, tipo bloco musical."""
    out = partials(freq, 0.7, 0.35, HARP, tau_exp=0.7)
    tick = svf(noise(0.003, rng), 2500, 0.7, "high")
    return add_at(out, tick, 0.0, 0.15)


def meow(rng) -> list:
    """Miau: 'm-i-a-u' com o tom subindo e caindo."""
    dur = 0.8

    def pitch(u):
        if u < 0.35:
            return 520 + 300 * math.sin(u / 0.35 * math.pi / 2)
        return 820 - 360 * ((u - 0.35) / 0.65) ** 1.2

    def formant1(u):
        return 350 + 500 * math.sin(math.pi * min(1.0, u * 1.4)) ** 0.8

    def formant2(u):
        return 1400 + 8000 * u if u < 0.1 else 2200 - 1400 * (u - 0.1) / 0.9

    src = osc(dur, pitch, "saw", vibrato=0.015, vib_rate=5.5)
    a = svf(src, formant1, 6, "band")
    b = svf(src, formant2, 8, "band")
    return mul([x + 0.6 * y for x, y in zip(a, b)], ar_env(dur, 0.07, 0.2))


def sparkle(rng) -> list:
    """Brilho (maçã dourada, poção): arpejo de sininhos subindo."""
    out: list = []
    for i, f in enumerate((1046.5, 1318.5, 1568.0, 2093.0)):
        add_at(out, partials(f, 0.6, 0.18, GLOCK), i * 0.065, 1 - i * 0.1)
    return out


def dizzy(rng) -> list:
    """Tontura: 'uó-uó-uó' descendo."""
    dur = 1.0
    s = osc(dur, lambda u: 640 - 320 * u, "tri", vibrato=0.09, vib_rate=7)
    wobble = [0.7 + 0.3 * math.sin(TAU * 3.5 * i / SR) for i in range(len(s))]
    return mul(mul(s, wobble), ar_env(dur, 0.02, 0.25))


def chime(rng) -> list:
    """Lembrete (água, pausa, dormir): duas notas calmas."""
    out = partials(784.0, 0.9, 0.3, BELL)
    return add_at(out, partials(1046.5, 0.9, 0.35, BELL), 0.16)


# nome -> (gerador, volume alvo em dB). Nomes com sufixo _N são variações do mesmo som
# (o player sorteia entre elas), exceto as notas, que o creeper escolhe uma por uma.
SOUNDS = {
    "pop": (pop, -17),
    "mastigar_1": (lambda rng: crunch(rng, 1500), -21),
    "mastigar_2": (lambda rng: crunch(rng, 1900), -21),
    "mastigar_3": (lambda rng: crunch(rng, 2500), -21),
    "gole_1": (lambda rng: gulp(rng, 260), -19),
    "gole_2": (lambda rng: gulp(rng, 310), -19),
    "arroto": (burp, -16),
    "cutucao_1": (lambda rng: boop(rng, 700, 330), -18),
    "cutucao_2": (lambda rng: boop(rng, 620, 290), -18),
    "carinho": (stroke, -22),
    "chiado": (hiss, -18),
    "explosao": (boom, -10),
    "pouso": (thud, -16),
    "pulo": (boing, -21),
    **{f"nota_{i}": ((lambda rng, f=f: pluck(rng, f)), -19) for i, f in enumerate(NOTES)},
    "miau": (meow, -16),
    "brilho": (sparkle, -19),
    "tonto": (dizzy, -19),
    "lembrete": (chime, -19),
}


def samples(name: str) -> list:
    gen, target = SOUNDS[name]
    rng = random.Random(name)   # sempre o mesmo som pro mesmo nome
    return fade(level(gen(rng), target), 0.001, 0.005)


def to_wav(x: list) -> bytes:
    pcm = array("h", (int(round(max(-1.0, min(1.0, v)) * 32767)) for v in x))
    if sys.byteorder == "big":
        pcm.byteswap()
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(pcm.tobytes())
    return buf.getvalue()


def render(name: str) -> bytes:
    return to_wav(samples(name))
