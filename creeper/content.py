"""Carrega itens e falas dos arquivos YAML da pasta content/."""
import random
from collections import deque

import yaml

from .config import resource_dir

CATEGORIES = ("comidas", "bebidas", "atividades")


class Items:
    def __init__(self, data: dict):
        self.by_category = {cat: list(data.get(cat) or []) for cat in CATEGORIES}
        self.by_id = {}
        for cat, items in self.by_category.items():
            for item in items:
                item.setdefault("efeitos", {})
                item["categoria"] = cat
                self.by_id[item["id"]] = item

    def get(self, item_id: str) -> dict:
        return self.by_id[item_id]


class Lines:
    """Sorteia falas por situação, evitando repetir as mais recentes."""

    def __init__(self, data: dict):
        self.data = {k: list(v or []) for k, v in (data or {}).items()}
        self.recent = {}

    def has(self, key: str) -> bool:
        return bool(self.data.get(key))

    def pick(self, key: str, **fmt) -> str | None:
        options = self.data.get(key)
        if not options:
            return None
        recent = self.recent.setdefault(key, deque(maxlen=max(1, len(options) // 2)))
        fresh = [line for line in options if line not in recent] or options
        line = random.choice(fresh)
        recent.append(line)
        try:
            return line.format(**fmt)
        except (KeyError, IndexError):
            return line


def _load_yaml(name: str) -> dict:
    path = resource_dir() / "content" / name
    with open(path, encoding="utf-8") as fh:
        return yaml.safe_load(fh) or {}


def load_content() -> tuple[Items, Lines]:
    return Items(_load_yaml("itens.yaml")), Lines(_load_yaml("falas.yaml"))
