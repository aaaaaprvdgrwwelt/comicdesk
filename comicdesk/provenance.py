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
#: Getaggt, aber ohne jeden Hinweis worauf - ehrlicher als "von Hand" zu raten.
UNKNOWN = "unknown"

#: Wird beim Speichern im Tag-Editor gesetzt, damit spaetere Laeufe wissen,
#: dass hier ein Mensch am Werk war.
MANUAL_MARKER = "[ComicDesk: von Hand]"

#: Reihenfolge zaehlt - die eigenen Marker sind eindeutiger als die Heuristik.
_PATTERNS = [
    (MANUAL, re.compile(re.escape(MANUAL_MARKER))),
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
        UNKNOWN: _("Quelle unbekannt"),
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
    # Tags sind da, aber nichts verraet woher - nicht als "von Hand" ausgeben.
    return UNKNOWN, None


_ID_PATTERNS = [
    re.compile(r"ComicVine issue id (\d+)"),
    re.compile(r"\[?Issue ID[: ]*(\d+)\]?", re.IGNORECASE),
    re.compile(r"comicvine\.gamespot\.com/[^/]+/4000-(\d+)"),
    re.compile(r"GCD issue id (\d+)"),
    re.compile(r"comics\.org/issue/(\d+)"),
]


def source_id(md: GenericMetadata) -> str | None:
    """Heft-ID der Quelle - erlaubt die exakte Zuordnung zur Reihe.

    ComicTagger schreibt sie je nach Version in die Notizen oder nur in den
    Web-Link; beides wird hier ausgewertet.
    """
    if md is None or md.is_empty:
        return None
    haystack = f"{md.notes or ''} {md.web_link or ''}"
    for pattern in _ID_PATTERNS:
        match = pattern.search(haystack)
        if match:
            return match.group(1)
    return None


def stamp_manual(md: GenericMetadata) -> None:
    """Beim Speichern von Hand einen Marker setzen, ohne Vorhandenes zu loeschen."""
    if detect(md)[0] not in (None, UNKNOWN):
        return
    notes = (md.notes or "").strip()
    if MANUAL_MARKER in notes:
        return
    md.notes = f"{notes} {MANUAL_MARKER}".strip()


def describe(md: GenericMetadata) -> str:
    """Ein Satz fuer die Anzeige im Metadaten-Panel."""
    source, detail = detect(md)
    if source is None:
        return _("Nicht getaggt")
    if detail:
        return _("Quelle: {source} (Heft-ID {id})").format(
            source=label(source), id=detail)
    return _("Quelle: {source}").format(source=label(source))
