"""ComicVine als Metadaten-Quelle.

Eigener, schlanker REST-Client statt comictaggerlib.ComicVineTalker: der ist an
das ComicTagger-GUI und dessen Settings-Objekt gebunden. Die API selbst ist
einfach genug.

Limits laut ComicVine: 200 Anfragen pro Stunde und Ressource, max. 1 pro
Sekunde. Deshalb Drosselung und ein Cache auf der Platte.
"""
from __future__ import annotations

import html
import json
import re
import sqlite3
import threading
import time
from pathlib import Path

import requests
from comicapi.genericmetadata import GenericMetadata

from ..i18n import _
from .base import (
    Candidate, MetadataProvider, SearchQuery, series_similarity,
)

API_BASE = "https://comicvine.gamespot.com/api"
USER_AGENT = "ComicDesk/1.0"
MIN_INTERVAL = 1.05  # Sekunden zwischen zwei Anfragen

ROLE_MAP = {
    "writer": "Writer",
    "penciler": "Penciller",
    "penciller": "Penciller",
    "artist": "Penciller",
    "inker": "Inker",
    "colorist": "Colorist",
    "colourist": "Colorist",
    "letterer": "Letterer",
    "cover": "CoverArtist",
    "editor": "Editor",
}

_tag_re = re.compile(r"<[^>]+>")


def strip_html(text: str | None) -> str | None:
    if not text:
        return None
    return html.unescape(_tag_re.sub("", text)).strip() or None


class RateLimitError(RuntimeError):
    pass


class _Cache:
    """Antworten dauerhaft zwischenspeichern - spart das knappe Kontingent."""

    def __init__(self, path: Path, ttl_days: int = 30):
        self.ttl = ttl_days * 86400
        path.parent.mkdir(parents=True, exist_ok=True)
        self._con = sqlite3.connect(str(path), check_same_thread=False)
        self._lock = threading.Lock()
        with self._lock:
            self._con.execute(
                "CREATE TABLE IF NOT EXISTS cache "
                "(key TEXT PRIMARY KEY, ts REAL, body TEXT)"
            )
            self._con.commit()

    def get(self, key: str):
        with self._lock:
            row = self._con.execute(
                "SELECT ts, body FROM cache WHERE key=?", (key,)
            ).fetchone()
        if not row or time.time() - row[0] > self.ttl:
            return None
        try:
            return json.loads(row[1])
        except json.JSONDecodeError:
            return None

    def put(self, key: str, value) -> None:
        with self._lock:
            self._con.execute(
                "INSERT OR REPLACE INTO cache VALUES (?,?,?)",
                (key, time.time(), json.dumps(value)),
            )
            self._con.commit()


class ComicVineProvider(MetadataProvider):
    name = "comicvine"
    label = "ComicVine"
    has_covers = True

    def __init__(self, api_key: str, cache_path: Path | None = None):
        self.api_key = (api_key or "").strip()
        self._session = requests.Session()
        self._session.headers["User-Agent"] = USER_AGENT
        self._last_call = 0.0
        self._lock = threading.Lock()
        if cache_path is None:
            cache_path = Path.home() / ".cache" / "comicdesk" / "comicvine.sqlite"
        self._cache = _Cache(cache_path)

    def available(self) -> tuple[bool, str]:
        if not self.api_key:
            return False, _("Kein ComicVine-API-Key hinterlegt.")
        return True, ""

    # --- HTTP ---------------------------------------------------------
    def _get(self, endpoint: str, params: dict) -> dict:
        params = {**params, "api_key": self.api_key, "format": "json"}
        key = endpoint + "?" + "&".join(
            f"{k}={v}" for k, v in sorted(params.items()) if k != "api_key"
        )
        cached = self._cache.get(key)
        if cached is not None:
            return cached

        with self._lock:
            wait = MIN_INTERVAL - (time.time() - self._last_call)
            if wait > 0:
                time.sleep(wait)
            self._last_call = time.time()

        resp = self._session.get(f"{API_BASE}/{endpoint}/", params=params, timeout=30)
        if resp.status_code == 420:
            raise RateLimitError(_(
                "ComicVine-Kontingent erschoepft (200 Anfragen/Stunde). "
                "Spaeter weitermachen - bereits geholte Daten sind gecacht."
            ))
        resp.raise_for_status()
        data = resp.json()
        status = data.get("status_code")
        if status == 107:
            raise RateLimitError(data.get("error", "Rate limit"))
        if status != 1:
            raise RuntimeError(f"ComicVine: {data.get('error', 'unbekannter Fehler')}")
        self._cache.put(key, data)
        return data

    # --- Suche --------------------------------------------------------
    def search(self, query: SearchQuery, limit: int = 20) -> list[Candidate]:
        if not query.series:
            return []
        volumes = self._search_volumes(query.series)
        volumes.sort(
            key=lambda v: series_similarity(query.series, v.get("name") or ""),
            reverse=True,
        )
        candidates: list[Candidate] = []
        for volume in volumes[:5]:
            if series_similarity(query.series, volume.get("name") or "") < 0.6:
                continue
            for issue in self._issues_for(volume["id"], query.issue):
                candidates.append(self._to_candidate(issue, volume))
                if len(candidates) >= limit:
                    return candidates
        return candidates

    def _search_volumes(self, series: str) -> list[dict]:
        data = self._get("search", {
            "query": series,
            "resources": "volume",
            "limit": 30,
            "field_list": "id,name,start_year,publisher,count_of_issues,image",
        })
        return [v for v in data.get("results", []) if v.get("id")]

    def _issues_for(self, volume_id: int, issue: str | None) -> list[dict]:
        flt = f"volume:{volume_id}"
        if issue:
            flt += f",issue_number:{issue}"
        data = self._get("issues", {
            "filter": flt,
            "limit": 50,
            "field_list": "id,name,issue_number,cover_date,store_date,image,volume",
        })
        return data.get("results", [])

    def _to_candidate(self, issue: dict, volume: dict) -> Candidate:
        md = GenericMetadata()
        md.series = volume.get("name")
        md.issue = str(issue.get("issue_number") or "").strip() or None
        md.title = issue.get("name") or None
        md.issue_count = volume.get("count_of_issues")
        publisher = (volume.get("publisher") or {}).get("name")
        md.publisher = publisher
        year = month = day = None
        date = issue.get("cover_date") or issue.get("store_date")
        if date:
            parts = date.split("-")
            year = int(parts[0]) if parts[0].isdigit() else None
            month = int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else None
            day = int(parts[2]) if len(parts) > 2 and parts[2].isdigit() else None
        md.year, md.month, md.day = year, month, day
        md.web_link = issue.get("site_detail_url")
        md.notes = f"ComicVine issue id {issue.get('id')}"
        md.is_empty = False

        image = issue.get("image") or {}
        return Candidate(
            source=self.name,
            metadata=md,
            series_name=volume.get("name") or "",
            issue_number=str(issue.get("issue_number") or ""),
            year=year,
            publisher=publisher,
            cover_url=image.get("super_url") or image.get("original_url"),
        )

    # --- Details ------------------------------------------------------
    def enrich(self, candidate: Candidate) -> Candidate:
        issue_id = _issue_id_from_notes(candidate.metadata.notes)
        if issue_id is None:
            return candidate
        data = self._get(f"issue/4000-{issue_id}", {
            "field_list": "description,person_credits,character_credits,"
                          "team_credits,location_credits,story_arc_credits,"
                          "site_detail_url",
        })
        result = data.get("results") or {}
        md = candidate.metadata
        md.comments = strip_html(result.get("description"))
        md.web_link = result.get("site_detail_url") or md.web_link
        md.characters = _join_names(result.get("character_credits"))
        md.teams = _join_names(result.get("team_credits"))
        md.locations = _join_names(result.get("location_credits"))
        arcs = _join_names(result.get("story_arc_credits"))
        if arcs:
            md.story_arc = arcs.split(", ")[0]
        for person in result.get("person_credits") or []:
            for raw_role in (person.get("role") or "").split(","):
                role = ROLE_MAP.get(raw_role.strip().casefold())
                if role and person.get("name"):
                    md.add_credit(person["name"], role)
        return candidate

    def fetch_cover(self, candidate: Candidate) -> bytes | None:
        if not candidate.cover_url:
            return None
        try:
            resp = self._session.get(candidate.cover_url, timeout=30)
            resp.raise_for_status()
            return resp.content
        except requests.RequestException:
            return None


def _join_names(items) -> str | None:
    names = [i.get("name") for i in (items or []) if i.get("name")]
    return ", ".join(names) if names else None


def _issue_id_from_notes(notes: str | None) -> int | None:
    match = re.search(r"ComicVine issue id (\d+)", notes or "")
    return int(match.group(1)) if match else None
