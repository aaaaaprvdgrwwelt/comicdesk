"""Intelligente Listen: gespeicherte Suchen statt gespeicherter Inhalte.

Wie die Smart Lists von ComicRack, nur ohne Regel-Editor mit Klickzeilen -
eine Liste ist genau die Abfrage, die auch in der Suchleiste steht. Wer
`serie:akim getaggt:nein` einmal getippt hat, speichert es unter einem Namen
und hat danach dauerhaft eine Arbeitsliste, die sich selbst pflegt.

Liegt als JSON neben den Favoriten - leicht zu sichern, weiterzugeben und
von Hand zu aendern.
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path

from .i18n import _
from .index import data_dir


@dataclass
class SmartList:
    name: str
    query: str
    #: Auf welche Sammlung begrenzt. Leer heisst: ueber alle.
    collection: str = ""

    @property
    def display(self) -> str:
        return self.name or self.query


#: Beim ersten Start angelegt - zeigen, wozu das gut ist, ohne zu ueberfrachten.
def _defaults() -> list[SmartList]:
    return [
        SmartList(_("Ohne Tags"), "getaggt:nein"),
        SmartList(_("Zuletzt indiziert"), "sortiert:neu"),
    ]


class SmartLists:
    """Geordnete Liste; Namen sind eindeutig."""

    def __init__(self, path: Path | None = None):
        self.path = path or (data_dir() / "smartlists.json")
        self.entries: list[SmartList] = []
        self.load()

    # ------------------------------------------------------------------
    def load(self) -> None:
        try:
            raw = json.loads(self.path.read_text("utf-8"))
        except FileNotFoundError:
            self.entries = _defaults()
            self.save()
            return
        except (OSError, json.JSONDecodeError):
            self.entries = []
            return
        self.entries = [
            SmartList(str(item.get("name", "")), str(item.get("query", "")),
                      str(item.get("collection", "")))
            for item in raw
            if isinstance(item, dict) and item.get("query")
        ]

    def save(self) -> None:
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.path.write_text(
                json.dumps([asdict(e) for e in self.entries], indent=2,
                           ensure_ascii=False),
                encoding="utf-8")
        except OSError:
            pass

    # ------------------------------------------------------------------
    def get(self, name: str) -> SmartList | None:
        gesucht = name.casefold()
        for eintrag in self.entries:
            if eintrag.name.casefold() == gesucht:
                return eintrag
        return None

    def add(self, name: str, query: str, collection: str = "") -> SmartList:
        """Anlegen oder eine gleichnamige Liste ueberschreiben."""
        vorhanden = self.get(name)
        if vorhanden is not None:
            vorhanden.query, vorhanden.collection = query, collection
            self.save()
            return vorhanden
        eintrag = SmartList(name, query, collection)
        self.entries.append(eintrag)
        self.save()
        return eintrag

    def remove(self, name: str) -> bool:
        eintrag = self.get(name)
        if eintrag is None:
            return False
        self.entries.remove(eintrag)
        self.save()
        return True

    def rename(self, old: str, new: str) -> bool:
        eintrag = self.get(old)
        if eintrag is None or (self.get(new) is not None
                               and old.casefold() != new.casefold()):
            return False
        eintrag.name = new
        self.save()
        return True

    def reorder(self, names: list[str]) -> None:
        """Reihenfolge aus der Anzeige uebernehmen."""
        nach_name = {e.name.casefold(): e for e in self.entries}
        neu = [nach_name.pop(n.casefold()) for n in names
               if n.casefold() in nach_name]
        self.entries = neu + list(nach_name.values())
        self.save()
