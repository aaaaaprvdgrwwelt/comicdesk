"""AniList als Ergaenzungsquelle fuer Manga.

AniList kennt Serien, keine einzelnen Baende einer Ausgabe - Verlag, Erschei-
nungsjahr und Titel der deutschen Ausgabe stehen in der GCD. Deshalb ist das
hier eine Ergaenzungsquelle: sie bestimmt nie das Heft, sondern fuellt nur, was
sonst leer bliebe (Zeichner, Autor, Genre, Beschreibung).

Kein Schluessel noetig. Das Limit liegt bei 90 Anfragen pro Minute; hier wird
zusaetzlich gedrosselt und dauerhaft gecacht.
"""
from __future__ import annotations

import re
import threading
import time

import requests
from comicapi.genericmetadata import GenericMetadata

from ..i18n import _
from .base import ROLE_SUPPLEMENT, MetadataProvider, SearchQuery, series_similarity
from .cache import ResponseCache

API_URL = "https://graphql.anilist.co"
USER_AGENT = "ComicDesk/1.0"
MIN_INTERVAL = 0.7

QUERY = """
query ($search: String) {
  Media(search: $search, type: MANGA) {
    id
    title { romaji english native }
    synonyms
    status
    countryOfOrigin
    startDate { year }
    volumes
    chapters
    genres
    description(asHtml: false)
    siteUrl
    isAdult
    staff(perPage: 12) { edges { role node { name { full } } } }
  }
}
"""

#: AniList-Rollen sind Freitext - hier auf ComicInfo-Rollen abgebildet.
ROLE_RULES = [
    (re.compile(r"story\s*&\s*art|story and art", re.I), ("Writer", "Penciller")),
    (re.compile(r"original\s*creator|original\s*story", re.I), ("Writer",)),
    (re.compile(r"\bstory\b", re.I), ("Writer",)),
    (re.compile(r"\bart\b|illustrat", re.I), ("Penciller",)),
    (re.compile(r"assistant", re.I), ()),
    (re.compile(r"translator|letter", re.I), ()),
]

_tag_re = re.compile(r"<[^>]+>")
_break_re = re.compile(r"<br\s*/?>", re.I)


def _clean(text: str | None) -> str | None:
    if not text:
        return None
    import html

    text = _break_re.sub("\n", text)
    return html.unescape(_tag_re.sub("", text)).strip() or None


def _map_role(raw: str) -> tuple[str, ...]:
    for pattern, roles in ROLE_RULES:
        if pattern.search(raw):
            return roles
    return ()


class AniListProvider(MetadataProvider):
    name = "anilist"
    label = "AniList (Manga)"
    role = ROLE_SUPPLEMENT

    def __init__(self, enabled: bool = True):
        self.enabled = enabled
        self._session = requests.Session()
        self._session.headers.update({"User-Agent": USER_AGENT,
                                      "Accept": "application/json"})
        self._cache = ResponseCache("anilist.sqlite")
        self._lock = threading.Lock()
        self._last_call = 0.0

    def available(self) -> tuple[bool, str]:
        if not self.enabled:
            return False, _("AniList ist abgeschaltet.")
        return True, ""

    # ------------------------------------------------------------------
    def _query(self, search: str) -> dict | None:
        key = f"media:{search.casefold()}"
        cached = self._cache.get(key)
        if cached is not None:
            return cached or None

        with self._lock:
            wait = MIN_INTERVAL - (time.time() - self._last_call)
            if wait > 0:
                time.sleep(wait)
            self._last_call = time.time()

        response = self._session.post(
            API_URL, json={"query": QUERY, "variables": {"search": search}},
            timeout=30)
        if response.status_code == 404:
            self._cache.put(key, {})
            return None
        if response.status_code == 429:
            raise RuntimeError(_("AniList-Limit erreicht, bitte spaeter erneut."))
        response.raise_for_status()
        media = (response.json().get("data") or {}).get("Media")
        self._cache.put(key, media or {})
        return media

    # ------------------------------------------------------------------
    def series_info(self, query: SearchQuery) -> GenericMetadata | None:
        if not query.series:
            return None
        media = self._query(query.series)
        if not media:
            return None
        titles = media.get("title") or {}
        names = [titles.get("romaji"), titles.get("english")]
        names += list(media.get("synonyms") or [])
        best = max((series_similarity(query.series, n) for n in names if n),
                   default=0.0)
        # Bei Ergaenzungen ist eine Fehlzuordnung teuer, deshalb streng.
        if best < 0.75:
            return None

        md = GenericMetadata()
        md.genre = ", ".join(media.get("genres") or []) or None
        md.comments = _clean(media.get("description"))
        md.web_link = media.get("siteUrl")
        md.manga = "YesAndRightToLeft" if media.get("countryOfOrigin") == "JP" \
            else "Yes"
        md.volume_count = media.get("volumes")
        if media.get("isAdult"):
            md.maturity_rating = "Adults Only 18+"
        seen: set[tuple[str, str]] = set()
        for edge in (media.get("staff") or {}).get("edges") or []:
            person = ((edge.get("node") or {}).get("name") or {}).get("full")
            if not person:
                continue
            for role in _map_role(edge.get("role") or ""):
                if (person, role) not in seen:
                    seen.add((person, role))
                    md.add_credit(person, role)
        md.is_empty = False
        return md
