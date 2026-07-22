"""Gemeinsame Schnittstelle fuer Metadaten-Quellen."""
from __future__ import annotations

import difflib
import re
from dataclasses import dataclass, field

from comicapi.genericmetadata import GenericMetadata

_ARTICLES = {"the", "a", "an", "der", "die", "das", "les", "la", "le", "el"}
_punct_re = re.compile(r"[^\w\s]", re.UNICODE)
_space_re = re.compile(r"\s+")


def normalize_series(name: str) -> str:
    """Serientitel auf eine vergleichbare Form bringen."""
    name = _punct_re.sub(" ", (name or "").casefold())
    words = [w for w in _space_re.split(name) if w and w not in _ARTICLES]
    return " ".join(words)


def normalize_issue(number: str | None) -> str:
    """'001', '#1', '1.0' -> '1'; alles andere bleibt normalisierter Text."""
    if number is None:
        return ""
    text = str(number).strip().lstrip("#").strip()
    try:
        value = float(text)
    except ValueError:
        return text.casefold().lstrip("0") or text.casefold()
    return str(int(value)) if value.is_integer() else str(value)


def series_similarity(a: str, b: str) -> float:
    na, nb = normalize_series(a), normalize_series(b)
    if not na or not nb:
        return 0.0
    if na == nb:
        return 1.0
    return difflib.SequenceMatcher(None, na, nb).ratio()


@dataclass
class SearchQuery:
    """Was wir aus Dateiname und vorhandenen Tags ueber das Heft wissen."""

    series: str
    issue: str | None = None
    year: int | None = None
    publisher: str | None = None
    cover: bytes | None = None


@dataclass
class Candidate:
    """Ein Treffer einer Quelle, noch ohne endgueltige Bewertung."""

    source: str
    metadata: GenericMetadata
    series_name: str = ""
    issue_number: str = ""
    year: int | None = None
    publisher: str | None = None
    cover_url: str | None = None
    score: int = 0
    reasons: list[str] = field(default_factory=list)


#: Quellen, die ein einzelnes Heft bestimmen koennen.
ROLE_PRIMARY = "primary"
#: Quellen, die nur die Serie kennen (Zeichner, Genre, Beschreibung). Sie
#: gewinnen nie allein, sondern fuellen nur, was sonst leer bliebe.
ROLE_SUPPLEMENT = "supplement"


class MetadataProvider:
    """Basisklasse. `search` liefert Kandidaten, Bewertung macht `autotag`."""

    name = "base"
    label = "Basis"
    #: Ob diese Quelle Cover-URLs liefert und damit Bild-Verifikation erlaubt.
    has_covers = False
    role = ROLE_PRIMARY

    def available(self) -> tuple[bool, str]:
        """(nutzbar, Begruendung falls nicht)."""
        return False, "nicht konfiguriert"

    def search(self, query: SearchQuery, limit: int = 20) -> list[Candidate]:
        raise NotImplementedError

    def fetch_cover(self, candidate: Candidate) -> bytes | None:
        return None

    def enrich(self, candidate: Candidate) -> Candidate:
        """Vollstaendige Metadaten nachladen - erst fuer den Gewinner noetig."""
        return candidate

    def series_issues(self, source_id: str) -> tuple[str, list[str]] | None:
        """Alle Heftnummern der Reihe, zu der dieses Heft gehoert.

        `source_id` ist die Heft-ID dieser Quelle - damit entfaellt jedes
        Raten ueber Serientitel. Gibt (Reihenname, Nummern) oder None.
        """
        return None

    def series_info(self, query: SearchQuery) -> GenericMetadata | None:
        """Nur fuer Ergaenzungsquellen: was ueber die Serie bekannt ist."""
        return None
