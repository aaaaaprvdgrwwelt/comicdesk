"""Reihen zusammenfassen und Luecken finden.

Zwei streng getrennte Aussagen:

* **Luecke** - zwischen zwei vorhandenen Heften fehlt eine Nummer. Das folgt
  allein aus dem eigenen Bestand und ist nicht bestreitbar.
* **Fehlt danach** - dass eine Reihe ueber das hoechste eigene Heft hinaus
  weiterging, weiss nur eine externe Quelle. Das ist eine Behauptung und wird
  immer mit Quellenangabe gefuehrt.

Ausserdem ist nicht jede Reihe fortlaufend nummeriert: Magazine wie Zack oder
Zorro nummerieren nach Datum (198303 = Maerz 1983). Wer das ignoriert, meldet
dort hunderttausende "fehlende" Hefte.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

SEQUENTIAL = "sequential"
DATE = "date"
MIXED = "mixed"

#: Alles darueber ist keine Heftnummer mehr, sondern ein Datum o.ae.
MAX_PLAIN_ISSUE = 2000
_date_re = re.compile(r"^(19|20)\d{2}(0[1-9]|1[0-2])$")


def is_date_number(value: int) -> bool:
    return bool(_date_re.match(str(value)))


def month_index(value: int) -> int:
    """198303 -> fortlaufender Monatsindex, damit Luecken zaehlbar werden."""
    return (value // 100) * 12 + (value % 100) - 1


def month_label(index: int) -> str:
    return f"{index // 12:04d}{index % 12 + 1:02d}"


@dataclass
class Series:
    """Eine Reihe im eigenen Bestand."""

    name: str
    publisher: str | None
    numbers: list[float] = field(default_factory=list)
    paths: list[str] = field(default_factory=list)
    scheme: str = SEQUENTIAL
    gaps: list[str] = field(default_factory=list)
    #: (Heftnummer, Quell-ID) - fuer die exakte Zuordnung zur Quell-Reihe.
    source: str | None = None
    samples: list[tuple[float, str]] = field(default_factory=list)
    #: Ergebnis einer Vollstaendigkeitspruefung, falls vorhanden.
    known_numbers: list[str] | None = None
    known_source: str | None = None
    #: Wie viele Reihen der Quelle diese lokale Reihe abdeckt.
    known_series_names: list[str] = field(default_factory=list)

    def probe_ids(self, count: int = 4) -> list[str]:
        """Quell-IDs quer ueber die Nummernspanne.

        Eine lokale Reihe deckt oft mehrere Reihen der Quelle ab (andere
        Auflage, anderer Verlag). Nur das erste Heft zu fragen, unterschlaegt
        den Rest - deshalb Proben vom Anfang, Ende und dazwischen.
        """
        if not self.samples:
            return []
        ordered = sorted(self.samples, key=lambda pair: pair[0])
        if len(ordered) <= count:
            picks = ordered
        else:
            step = (len(ordered) - 1) / (count - 1)
            picks = [ordered[round(i * step)] for i in range(count)]
        seen: list[str] = []
        for _number, ident in picks:
            if ident not in seen:
                seen.append(ident)
        return seen

    @property
    def key(self) -> tuple[str, str]:
        return (self.name, self.publisher or "")

    @property
    def count(self) -> int:
        return len(self.paths)

    @property
    def span(self) -> str:
        if not self.numbers:
            return "–"
        low, high = min(self.numbers), max(self.numbers)
        if self.scheme == DATE:
            return f"{_fmt(low)}–{_fmt(high)}"
        return f"#{_fmt(low)}–#{_fmt(high)}"

    @property
    def missing_after(self) -> list[str]:
        """Nummern, die laut Quelle nach dem hoechsten eigenen Heft kamen."""
        if not self.known_numbers or not self.numbers:
            return []
        have = {_fmt(n) for n in self.numbers}
        highest = max(self.numbers)
        return [n for n in self.known_numbers
                if n not in have and _as_number(n) is not None
                and _as_number(n) > highest]

    @property
    def missing_known(self) -> list[str]:
        """Alles, was die Quelle kennt und im Bestand fehlt."""
        if not self.known_numbers:
            return []
        have = {_fmt(n) for n in self.numbers}
        return [n for n in self.known_numbers if n not in have]


def _fmt(value: float) -> str:
    return str(int(value)) if float(value).is_integer() else str(value)


def _as_number(text: str) -> float | None:
    try:
        return float(str(text).strip().lstrip("#"))
    except ValueError:
        return None


# ---------------------------------------------------------------------------
def detect_scheme(numbers: list[float]) -> str:
    """Fortlaufend, nach Datum, oder uneinheitlich?"""
    whole = [int(n) for n in numbers if float(n).is_integer()]
    if not whole:
        return SEQUENTIAL if numbers else MIXED
    dates = sum(1 for n in whole if is_date_number(n))
    plain = sum(1 for n in whole if 0 < n <= MAX_PLAIN_ISSUE)
    total = len(whole)
    if dates and dates >= total * 0.8:
        return DATE
    if plain >= total * 0.8:
        return SEQUENTIAL
    return MIXED


def find_gaps(numbers: list[float], scheme: str) -> list[str]:
    """Fehlende Nummern zwischen der niedrigsten und der hoechsten vorhandenen.

    Bei uneinheitlicher Nummerierung wird bewusst nichts gemeldet - lieber
    keine Aussage als eine falsche.
    """
    if scheme == MIXED:
        return []
    whole = sorted({int(n) for n in numbers if float(n).is_integer()})
    if len(whole) < 2:
        return []
    if scheme == DATE:
        indexes = sorted({month_index(n) for n in whole if is_date_number(n)})
        if len(indexes) < 2:
            return []
        have = set(indexes)
        return [month_label(i) for i in range(indexes[0], indexes[-1] + 1)
                if i not in have]
    have = set(whole)
    return [str(n) for n in range(whole[0], whole[-1] + 1) if n not in have]


def build(rows) -> list[Series]:
    """Index-Zeilen zu Reihen buendeln. Erwartet Mapping-artige Zeilen."""
    grouped: dict[tuple[str, str], Series] = {}
    for row in rows:
        name = (row["series"] or "").strip()
        if not name:
            continue
        publisher = (row["publisher"] or "").strip() or None
        key = (name, publisher or "")
        entry = grouped.get(key)
        if entry is None:
            entry = grouped[key] = Series(name=name, publisher=publisher)
        entry.paths.append(row["path"])
        value = row["issue_sort"]
        if value is not None:
            entry.numbers.append(float(value))
        if row["source"] and entry.source is None:
            entry.source = row["source"]
        source_id = row["source_id"] if "source_id" in row.keys() else None
        if source_id and value is not None:
            entry.samples.append((float(value), str(source_id)))

    for entry in grouped.values():
        entry.scheme = detect_scheme(entry.numbers)
        entry.gaps = find_gaps(entry.numbers, entry.scheme)
    return sorted(grouped.values(), key=lambda s: s.name.casefold())
