"""Woher stammen die Tags eines Comics?

ComicInfo.xml kennt kein eigenes Feld dafuer. Ueblich ist, es im Notes-Feld zu
vermerken - das macht ComicTagger so, und ComicDesk schreibt beim automatischen
Taggen ebenfalls dorthin. Hier wird das wieder ausgelesen, ohne etwas zu
veraendern; auch Dateien, die andere Programme getaggt haben, werden erkannt.
"""
from __future__ import annotations

import re

from comicapi.genericmetadata import GenericMetadata

from .i18n import _

COMICVINE = "comicvine"
GCD = "gcd"
MANUAL = "manual"

#: Reihenfolge zaehlt - die eigenen Marker sind eindeutiger als die Heuristik.
_PATTERNS = [
    (COMICVINE, re.compile(r"ComicVine issue id (\d+)")),
    (GCD, re.compile(r"GCD issue id (\d+)")),
    (COMICVINE, re.compile(r"comic\s*vine", re.IGNORECASE)),
    (GCD, re.compile(r"grand comics database|comics\.org", re.IGNORECASE)),
]

_LINK_HINTS = [
    (COMICVINE, "comicvine.gamespot.com"),
    (GCD, "comics.org"),
]


def label(source: str | None) -> str:
    """Anzeigename der Quelle."""
    return {
        COMICVINE: "ComicVine",
        GCD: _("Grand Comics Database"),
        MANUAL: _("Von Hand"),
    }.get(source or "", _("Nicht getaggt"))


def detect(md: GenericMetadata) -> tuple[str | None, str | None]:
    """(Quelle, Detail) - Quelle ist None, wenn die Datei keine Tags hat."""
    if md is None or md.is_empty:
        return None, None
    notes = md.notes or ""
    for source, pattern in _PATTERNS:
        match = pattern.search(notes)
        if match:
            detail = match.group(1) if match.groups() else None
            return source, detail
    link = (md.web_link or "").lower()
    for source, needle in _LINK_HINTS:
        if needle in link:
            return source, None
    return MANUAL, None


def describe(md: GenericMetadata) -> str:
    """Ein Satz fuer die Anzeige im Metadaten-Panel."""
    source, detail = detect(md)
    if source is None:
        return _("Nicht getaggt")
    if detail:
        return _("Quelle: {source} (Heft-ID {id})").format(
            source=label(source), id=detail)
    return _("Quelle: {source}").format(source=label(source))
