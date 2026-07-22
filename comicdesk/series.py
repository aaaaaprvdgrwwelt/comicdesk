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
    #: Von Hand festgelegter Bestand der Reihe. Schlaegt jede Quelle.
    manual_numbers: list[str] | None = None
    manual_note: str = ""

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
    def is_manual(self) -> bool:
        return self.manual_numbers is not None

    @property
    def reference(self) -> list[str] | None:
        """Was die Reihe umfasst - von Hand festgelegt schlaegt die Quelle."""
        if self.manual_numbers is not None:
            return self.manual_numbers
        return self.known_numbers

    @property
    def effective_gaps(self) -> list[str]:
        """Fehlende Nummern. Bei manueller Festlegung zaehlt nur diese."""
        if self.manual_numbers is not None:
            have = {_fmt(n) for n in self.numbers}
            return [n for n in self.manual_numbers if n not in have]
        return self.gaps

    @property
    def unexpected(self) -> list[str]:
        """Eigene Hefte, die es laut Referenz gar nicht geben duerfte.

        Entweder stimmt die Festlegung nicht oder das Heft ist falsch getaggt -
        beides sollte man sehen statt es stillschweigend zu schlucken.
        """
        reference = self.reference
        if not reference:
            return []
        known = set(reference)
        return sorted({_fmt(n) for n in self.numbers} - known, key=_sort_key)

    @property
    def missing_after(self) -> list[str]:
        """Nummern, die laut Quelle nach dem hoechsten eigenen Heft kamen."""
        reference = self.reference
        if not reference or not self.numbers:
            return []
        have = {_fmt(n) for n in self.numbers}
        highest = max(self.numbers)
        return [n for n in reference
                if n not in have and _as_number(n) is not None
                and _as_number(n) > highest]

    @property
    def missing_known(self) -> list[str]:
        """Alles, was die Quelle kennt und im Bestand fehlt."""
        reference = self.reference
        if not reference:
            return []
        have = {_fmt(n) for n in self.numbers}
        return [n for n in reference if n not in have]


def _fmt(value: float) -> str:
    return str(int(value)) if float(value).is_integer() else str(value)


def _as_number(text: str) -> float | None:
    try:
        return float(str(text).strip().lstrip("#"))
    except ValueError:
        return None


# --- Bereichsschreibweise: "1-3, 12-20" ------------------------------------
def parse_ranges(text: str) -> list[str]:
    """`1-3, 12-20, 5a` -> ['1','2','3','12',…,'20','5a'].

    Nicht-numerische Angaben bleiben unveraendert stehen; Sonderbaende heissen
    nun einmal "0" oder "5a".
    """
    numbers: list[str] = []
    for part in re.split(r"[,;\n]", text or ""):
        part = part.strip()
        if not part:
            continue
        match = re.fullmatch(r"(\d+)\s*[-–]\s*(\d+)", part)
        if match:
            low, high = int(match.group(1)), int(match.group(2))
            if low > high:
                low, high = high, low
            if high - low > 5000:      # Tippfehler wie "1-99999" abfangen
                continue
            numbers += [str(n) for n in range(low, high + 1)]
        else:
            numbers.append(part.lstrip("#"))
    seen: list[str] = []
    for value in numbers:
        if value not in seen:
            seen.append(value)
    return sorted(seen, key=_sort_key)


def format_ranges(numbers: list[str]) -> str:
    """Umkehrung: ['1','2','3','12'] -> '1-3, 12'."""
    whole, other = [], []
    for value in numbers:
        try:
            number = int(value)
        except (TypeError, ValueError):
            other.append(str(value))
        else:
            whole.append(number)
    whole.sort()
    parts: list[str] = []
    start = previous = None
    for number in whole:
        if start is None:
            start = previous = number
        elif number == previous + 1:
            previous = number
        else:
            parts.append(str(start) if start == previous else f"{start}-{previous}")
            start = previous = number
    if start is not None:
        parts.append(str(start) if start == previous else f"{start}-{previous}")
    return ", ".join(parts + other)


def _sort_key(text: str):
    try:
        return (0, float(text), "")
    except ValueError:
        return (1, 0.0, str(text))


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
