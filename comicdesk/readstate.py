"""Lesestand und Lesezeichen je Comic.

Wie die Favoriten als JSON neben dem Suchindex - der Suchindex wird beim
Neuaufbau geleert, der Lesestand soll das ueberleben.
"""
from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from pathlib import Path

from .index import data_dir

#: Mehr Eintraege bringen nichts - wer 5000 Hefte angelesen hat, braucht
#: den aeltesten Stand nicht mehr.
MAX_ENTRIES = 5000
#: Ab wieviel Prozent gilt ein Heft als durchgelesen.
FINISHED_AT = 0.95


@dataclass
class ReadEntry:
    page: int = 0
    total: int = 0
    updated: float = 0.0
    bookmarks: list[int] = field(default_factory=list)

    @property
    def finished(self) -> bool:
        return bool(self.total) and self.page + 1 >= self.total * FINISHED_AT

    @property
    def percent(self) -> int:
        if not self.total:
            return 0
        return min(100, round((self.page + 1) * 100 / self.total))


class ReadingState:
    """Lesestaende aller Comics, mit gebremstem Schreiben."""

    #: Beim Blaettern nicht jedesmal die Datei anfassen.
    SAVE_EVERY = 5.0

    def __init__(self, path: Path | None = None):
        self.path = path or (data_dir() / "reading.json")
        self.entries: dict[str, ReadEntry] = {}
        self._dirty = False
        self._last_save = 0.0
        self.load()

    # ------------------------------------------------------------------
    def load(self) -> None:
        try:
            raw = json.loads(self.path.read_text("utf-8"))
        except (OSError, json.JSONDecodeError):
            self.entries = {}
            return
        if not isinstance(raw, dict):
            self.entries = {}
            return
        for key, item in raw.items():
            if not isinstance(item, dict):
                continue
            marken = [int(b) for b in item.get("bookmarks", [])
                      if isinstance(b, (int, float))]
            self.entries[str(key)] = ReadEntry(
                page=int(item.get("page", 0)),
                total=int(item.get("total", 0)),
                updated=float(item.get("updated", 0.0)),
                bookmarks=sorted(set(marken)),
            )

    def save(self, force: bool = False) -> None:
        if not self._dirty:
            return
        now = time.time()
        if not force and now - self._last_save < self.SAVE_EVERY:
            return
        self._prune()
        daten = {key: {"page": e.page, "total": e.total,
                       "updated": round(e.updated, 1),
                       "bookmarks": e.bookmarks}
                 for key, e in self.entries.items()}
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.path.write_text(json.dumps(daten, indent=1, sort_keys=True),
                                 encoding="utf-8")
        except OSError:
            return          # kein Grund, deshalb das Lesen abzubrechen
        self._dirty = False
        self._last_save = now

    def _prune(self) -> None:
        if len(self.entries) <= MAX_ENTRIES:
            return
        nach_alter = sorted(self.entries.items(), key=lambda kv: kv[1].updated)
        for key, _entry in nach_alter[:len(self.entries) - MAX_ENTRIES]:
            del self.entries[key]

    # ------------------------------------------------------------------
    def get(self, path: Path) -> ReadEntry:
        return self.entries.get(str(path), ReadEntry())

    def _entry(self, path: Path) -> ReadEntry:
        key = str(path)
        entry = self.entries.get(key)
        if entry is None:
            entry = self.entries[key] = ReadEntry()
        return entry

    def set_page(self, path: Path, page: int, total: int) -> None:
        entry = self._entry(path)
        if entry.page == page and entry.total == total:
            return
        entry.page, entry.total, entry.updated = page, total, time.time()
        self._dirty = True
        self.save()

    def toggle_bookmark(self, path: Path, page: int) -> bool:
        """True, wenn danach ein Lesezeichen auf der Seite liegt."""
        entry = self._entry(path)
        if page in entry.bookmarks:
            entry.bookmarks.remove(page)
            gesetzt = False
        else:
            entry.bookmarks = sorted(set(entry.bookmarks) | {page})
            gesetzt = True
        entry.updated = time.time()
        self._dirty = True
        self.save(force=True)
        return gesetzt

    def forget(self, path: Path) -> None:
        if self.entries.pop(str(path), None) is not None:
            self._dirty = True
            self.save(force=True)

    def rename(self, old: Path, new: Path) -> None:
        entry = self.entries.pop(str(old), None)
        if entry is not None:
            self.entries[str(new)] = entry
            self._dirty = True
            self.save(force=True)


_state: ReadingState | None = None


def reading_state() -> ReadingState:
    """Gemeinsamer Stand - mehrere Reader-Fenster teilen sich eine Datei."""
    global _state
    if _state is None:
        _state = ReadingState()
    return _state
