"""Toca os sons do creeper. Os WAV são gerados por synth.py na primeira vez e ficam em cache.

Se o Qt não tiver o módulo de áudio (ou não houver saída de som), tudo vira silêncio.
"""
import hashlib
import os
import random
import shutil
import threading
from pathlib import Path

from PySide6.QtCore import QObject, QTimer, QUrl

from ..config import data_dir
from . import synth

try:
    from PySide6.QtMultimedia import QMediaDevices, QSoundEffect
except Exception:  # PySide6 sem QtMultimedia, ou Linux sem libpulse
    QSoundEffect = None

POOL = 2  # cópias de cada som, pra um poder tocar por cima do outro (mastigar, notas)


def _cache_dir() -> Path:
    """Pasta dos WAV. Muda de nome quando synth.py muda, então os sons nunca ficam velhos."""
    try:
        key = hashlib.sha1(Path(synth.__file__).read_bytes()).hexdigest()[:10]
    except OSError:
        key = "padrao"
    root = data_dir() / "sons"
    for old in root.glob("*"):
        if old.name != key:
            shutil.rmtree(old, ignore_errors=True)
    path = root / key
    path.mkdir(parents=True, exist_ok=True)
    return path


class Sounds(QObject):
    def __init__(self, settings, parent=None):
        super().__init__(parent)
        self.settings = settings
        self.effects: dict[str, list] = {}
        self.groups: dict[str, list[str]] = {}
        for name in synth.SOUNDS:
            base, _, suffix = name.rpartition("_")
            if suffix.isdigit():
                self.groups.setdefault(base, []).append(name)
        self._turn: dict[str, int] = {}
        self._last: dict[str, str] = {}   # última variação tocada de cada grupo
        self._worker: threading.Thread | None = None
        self.folder: Path | None = None
        self.available = QSoundEffect is not None and not os.environ.get("CREEPER_SEM_SOM")

    def load(self) -> None:
        """Prepara os efeitos. O que faltar no cache é gerado numa thread (cerca de 1 s quando
        os sons mudam), pra animação não travar."""
        if not self.available or self.effects or self._worker:
            return
        try:
            self.folder = _cache_dir()
        except OSError:
            self.available = False
            return
        if all((self.folder / f"{name}.wav").exists() for name in synth.SOUNDS):
            self._create_effects()
            return
        self._worker = threading.Thread(target=self._render_missing, daemon=True)
        self._worker.start()
        self._waiting = QTimer(self)
        self._waiting.timeout.connect(self._when_rendered)
        self._waiting.start(100)

    def _render_missing(self) -> None:
        """Roda na thread: só Python puro e arquivos, nada de Qt."""
        try:
            for name in synth.SOUNDS:
                path = self.folder / f"{name}.wav"
                if not path.exists():
                    tmp = path.with_suffix(".tmp")
                    tmp.write_bytes(synth.render(name))
                    os.replace(tmp, path)
        except OSError:
            self.available = False

    def _when_rendered(self) -> None:
        if self._worker.is_alive():
            return
        self._waiting.stop()
        if self.available:
            self._create_effects()

    def _create_effects(self) -> None:
        device = QMediaDevices.defaultAudioOutput()
        for name in synth.SOUNDS:
            url = QUrl.fromLocalFile(str(self.folder / f"{name}.wav"))
            pool = []
            for _ in range(POOL):
                effect = QSoundEffect(device, self)
                effect.setSource(url)
                pool.append(effect)
            self.effects[name] = pool
        # Fone conectado/desconectado: troca a saída junto com o sistema.
        self._devices = QMediaDevices(self)
        self._devices.audioOutputsChanged.connect(self._follow_default_output)

    def _follow_default_output(self) -> None:
        device = QMediaDevices.defaultAudioOutput()
        for pool in self.effects.values():
            for effect in pool:
                effect.setAudioDevice(device)

    def play(self, name: str, volume: float = 1.0) -> None:
        if not self.settings.sound or not self.effects:
            return
        if name not in self.effects and name in self.groups:
            options = [n for n in self.groups[name] if n != self._last.get(name)]
            self._last[name] = name = random.choice(options)
        pool = self.effects.get(name)
        if not pool:
            return
        free = [e for e in pool if not e.isPlaying()]
        if free:
            effect = free[0]
        else:  # todas tocando: reaproveita a mais antiga
            turn = self._turn.get(name, 0)
            self._turn[name] = (turn + 1) % len(pool)
            effect = pool[turn]
            effect.stop()
        # volume percebido ~ quadrado da amplitude
        effect.setVolume(max(0.0, min(1.0, (self.settings.sound_volume / 100) ** 2 * volume)))
        effect.play()

    def stop(self, name: str) -> None:
        for effect in self.effects.get(name, ()):
            effect.stop()
