"""Toca os sons do creeper um por um (com o nome de cada), ou salva os WAV numa pasta.

Uso:  python tools/preview_sounds.py                 toca todos, em sequência
      python tools/preview_sounds.py pop miau        toca só esses (ou grupos: mastigar, nota)
      python tools/preview_sounds.py --salvar pasta  só salva os WAV
"""
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from creeper.sound import synth  # noqa: E402

GAP_MS = 500


def pick(args: list[str]) -> list[str]:
    if not args:
        return list(synth.SOUNDS)
    names = [n for n in synth.SOUNDS if n in args or n.rpartition("_")[0] in args]
    unknown = [a for a in args if not any(n == a or n.rpartition("_")[0] == a for n in synth.SOUNDS)]
    if unknown:
        sys.exit(f"Som desconhecido: {', '.join(unknown)}. Existem: {', '.join(synth.SOUNDS)}")
    return names


def save(folder: Path, names: list[str]) -> dict[str, float]:
    """Salva os WAV e devolve a duração de cada um (s)."""
    folder.mkdir(parents=True, exist_ok=True)
    durations = {}
    for name in names:
        x = synth.samples(name)
        (folder / f"{name}.wav").write_bytes(synth.to_wav(x))
        durations[name] = len(x) / synth.SR
    print(f"{len(names)} sons salvos em {folder}")
    return durations


def play(names: list[str]) -> None:
    from PySide6.QtCore import QCoreApplication, QTimer, QUrl
    from PySide6.QtMultimedia import QSoundEffect

    qapp = QCoreApplication(sys.argv)
    folder = Path(tempfile.mkdtemp(prefix="creeper-sons-"))
    durations = save(folder, names)
    effects = {}
    for name in names:
        effect = QSoundEffect()
        effect.setVolume(0.36)  # volume "médio" do app
        effect.setSource(QUrl.fromLocalFile(str(folder / f"{name}.wav")))
        effects[name] = effect
    queue = list(names)

    def next_sound():
        if not queue:
            qapp.quit()
            return
        name = queue.pop(0)
        print(f"  {name}")
        effects[name].play()
        QTimer.singleShot(int(durations[name] * 1000) + GAP_MS, next_sound)

    def wait_loaded():
        if any(e.status() == QSoundEffect.Status.Loading for e in effects.values()):
            QTimer.singleShot(50, wait_loaded)
        else:
            next_sound()

    wait_loaded()
    qapp.exec()


if __name__ == "__main__":
    args = sys.argv[1:]
    if args[:1] == ["--salvar"]:
        if len(args) < 2:
            sys.exit(__doc__)
        save(Path(args[1]), pick(args[2:]))
    else:
        play(pick(args))
