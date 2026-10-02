"""Caminhos, configurações do usuário e salvamento em disco."""
import json
import os
import sys
import time
from dataclasses import asdict, dataclass, fields
from pathlib import Path

from . import __version__

APP_NAME = "CreeperCompanion"


def resource_dir() -> Path:
    """Pasta raiz do projeto (ou a pasta temporária do PyInstaller)."""
    if getattr(sys, "frozen", False):
        return Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
    return Path(__file__).resolve().parent.parent


def data_dir() -> Path:
    if sys.platform == "win32":
        base = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming"))
        path = base / APP_NAME
    else:
        base = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
        path = base / "creeper-companion"
    path.mkdir(parents=True, exist_ok=True)
    return path


SAVE_FILE = "save.json"


@dataclass
class Settings:
    name: str = "Creepinho"
    scale: int = 3                 # tamanho do pixel: 2 = P, 3 = M, 4 = G
    chattiness: str = "normal"     # pouco | normal | muito
    needs_speed: float = 1.0       # multiplicador da queda das necessidades
    remind_water: bool = True
    water_minutes: int = 60
    remind_break: bool = True
    break_minutes: int = 50
    remind_sleep: bool = True
    hide_fullscreen: bool = True
    notifications: bool = True
    sound: bool = True
    sound_volume: int = 60         # 30 = baixo, 60 = médio, 100 = alto
    # guarda-roupa (ids de cosmetics.py; "" = nada)
    hat: str = ""
    skin: str = ""
    trail: str = ""
    charged: bool = False
    # comportamentos (só valem depois de desbloqueados)
    solo_play: bool = True         # brinca sozinho quando está feliz
    climb: bool = True             # sobe nas janelas abertas
    # versão nova
    check_updates: bool | None = None   # procura sozinho? None = ainda não perguntou (só procura se deixarem)
    skip_version: str = ""         # "pular esta versão": não oferece essa de novo sozinho

    @classmethod
    def from_dict(cls, data: dict) -> "Settings":
        known = {f.name for f in fields(cls)}
        return cls(**{k: v for k, v in (data or {}).items() if k in known})


def load_save() -> dict:
    path = data_dir() / SAVE_FILE
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def write_save(settings: Settings, pet: dict, window: dict) -> None:
    payload = {
        "version": 1,
        "app_version": __version__,
        "saved_at": time.time(),
        "settings": asdict(settings),
        "pet": pet,
        "window": window,
    }
    path = data_dir() / SAVE_FILE
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, path)
