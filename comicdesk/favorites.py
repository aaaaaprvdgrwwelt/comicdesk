"""Favoriten fuer Ordner und einzelne Comics.

Liegen als JSON neben dem Suchindex, damit sie sich leicht sichern und von
Hand bearbeiten lassen.
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path

from .index import data_dir


@dataclass
class Favorite:
    path: str
    label: str = ""

    @property
    def as_path(self) -> Path:
        return Path(self.path)

    @property
    def display(self) -> str:
        return self.label or self.as_path.name or self.path

    @property
    def is_dir(self) -> bool:
        return self.as_path.is_dir()

    @property
    def exists(self) -> bool:
        return self.as_path.exists()


class Favorites:
    """Geordnete Liste; Pfade sind eindeutig."""

    def __init__(self, path: Path | None = None):
        self.path = path or (data_dir() / "favorites.json")
        self.entries: list[Favorite] = []
        self.load()

    # ------------------------------------------------------------------
    def load(self) -> None:
        try:
            raw = json.loads(self.path.read_text("utf-8"))
        except (OSError, json.JSONDecodeError):
            self.entries = []
            return
        self.entries = [
            Favorite(str(item.get("path", "")), str(item.get("label", "")))
            for item in raw if isinstance(item, dict) and item.get("path")
        ]

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(
            json.dumps([asdict(e) for e in self.entries], indent=2,
                       ensure_ascii=False),
            "utf-8")

    # ------------------------------------------------------------------
    def contains(self, path: Path) -> bool:
        return any(e.path == str(path) for e in self.entries)

    def add(self, path: Path, label: str = "") -> bool:
        """False, wenn der Pfad schon drin ist."""
        if self.contains(path):
            return False
        self.entries.append(Favorite(str(path), label))
        self.save()
        return True

    def remove(self, path: Path) -> None:
        self.entries = [e for e in self.entries if e.path != str(path)]
        self.save()

    def toggle(self, path: Path, label: str = "") -> bool:
        """True, wenn danach ein Favorit ist."""
        if self.contains(path):
            self.remove(path)
            return False
        self.add(path, label)
        return True

    def rename(self, path: Path, label: str) -> None:
        for entry in self.entries:
            if entry.path == str(path):
                entry.label = label
                break
        self.save()

    def reorder(self, paths: list[str]) -> None:
        """Reihenfolge aus der Ansicht uebernehmen."""
        by_path = {e.path: e for e in self.entries}
        ordered = [by_path[p] for p in paths if p in by_path]
        # Nicht Genanntes hinten anhaengen, damit nichts verlorengeht.
        ordered += [e for e in self.entries if e.path not in set(paths)]
        self.entries = ordered
        self.save()

    def move_path(self, old: Path, new: Path) -> None:
        """Nach Umbenennen/Verschieben den Favoriten mitziehen."""
        changed = False
        for entry in self.entries:
            if entry.path == str(old):
                entry.path = str(new)
                changed = True
            elif entry.path.startswith(str(old) + "/"):
                entry.path = str(new) + entry.path[len(str(old)):]
                changed = True
        if changed:
            self.save()

    def prune_missing(self) -> int:
        gone = [e for e in self.entries if not e.exists]
        if gone:
            self.entries = [e for e in self.entries if e.exists]
            self.save()
        return len(gone)
