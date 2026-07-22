"""Grand Comics Database als lokale Quelle.

Die GCD hat keine oeffentliche API, stellt aber alle zwei Wochen SQLite-Dumps
bereit: https://www.comics.org/download/ (Account noetig, Daten unter CC-BY).
Das Schema hier ist gegen den `gcd-talker` (ComicTagger-Plugin) verifiziert.

Staerke gegenueber ComicVine: europaeische und deutsche Verlage sind gut
erfasst. Schwaeche: der Dump enthaelt keine Cover-URLs, es gibt also keine
Bild-Verifikation.
"""
from __future__ import annotations

import sqlite3
import threading
from pathlib import Path

from comicapi.genericmetadata import GenericMetadata

from ..i18n import _
from .base import (
    Candidate, MetadataProvider, SearchQuery, normalize_issue,
)

# gcd_story.type_id 19 == "cover"-freie Hauptgeschichte laut GCD-Schema
STORY_TYPE_MAIN = 19

CREDIT_MAP = {
    "script": "Writer",
    "pencils": "Penciller",
    "inks": "Inker",
    "colors": "Colorist",
    "letters": "Letterer",
    "editing": "Editor",
    "painting": "Penciller",
}


class GcdProvider(MetadataProvider):
    name = "gcd"
    label = "GCD (lokal)"
    has_covers = False

    def __init__(self, db_path: str | Path | None, language: str | None = None):
        self.db_path = Path(db_path).expanduser() if db_path else None
        #: Optionaler ISO-Code, um z.B. nur deutsche Ausgaben zu liefern.
        self.language = (language or "").strip().lower() or None
        self._local = threading.local()

    # ------------------------------------------------------------------
    def available(self) -> tuple[bool, str]:
        if not self.db_path:
            return False, _("Kein Pfad zum GCD-Dump hinterlegt.")
        if not self.db_path.is_file():
            return False, _("GCD-Dump nicht gefunden: {path}").format(
                path=self.db_path)
        try:
            con = self._connect()
            con.execute("SELECT id FROM gcd_series LIMIT 1").fetchone()
        except sqlite3.Error as exc:
            return False, _("GCD-Dump nicht lesbar: {error}").format(error=exc)
        return True, ""

    def _connect(self) -> sqlite3.Connection:
        con = getattr(self._local, "con", None)
        if con is None:
            con = sqlite3.connect(f"file:{self.db_path}?mode=ro", uri=True)
            con.row_factory = sqlite3.Row
            con.text_factory = str
            self._local.con = con
        return con

    def ensure_indexes(self) -> None:
        """Beschleunigt die Suche massiv - der Dump kommt fast ohne Indizes."""
        con = sqlite3.connect(str(self.db_path))
        try:
            con.execute("CREATE INDEX IF NOT EXISTS cd_story_issue "
                        "ON gcd_story (issue_id, type_id)")
            con.execute("CREATE INDEX IF NOT EXISTS cd_issue_series "
                        "ON gcd_issue (series_id, number)")
            con.execute("CREATE INDEX IF NOT EXISTS cd_series_name "
                        "ON gcd_series (name)")
            con.commit()
        finally:
            con.close()

    # ------------------------------------------------------------------
    def search(self, query: SearchQuery, limit: int = 20) -> list[Candidate]:
        if not query.series:
            return []
        con = self._connect()
        sql = (
            "SELECT s.id, s.name AS series_name, s.year_began, s.issue_count, "
            "       p.name AS publisher, l.code AS language_iso "
            "FROM gcd_series s "
            "LEFT JOIN gcd_publisher p ON s.publisher_id = p.id "
            "LEFT JOIN stddata_language l ON s.language_id = l.id "
            "WHERE s.name LIKE ? "
        )
        params: list = [f"%{query.series}%"]
        if self.language:
            sql += "AND l.code = ? "
            params.append(self.language)
        sql += "LIMIT 60"
        series_rows = con.execute(sql, params).fetchall()

        candidates: list[Candidate] = []
        wanted = normalize_issue(query.issue) if query.issue else None
        for series in series_rows:
            for issue in self._issues(con, series["id"], wanted):
                candidates.append(self._to_candidate(series, issue))
                if len(candidates) >= limit:
                    return candidates
        return candidates

    def _issues(self, con, series_id: int, wanted: str | None) -> list[sqlite3.Row]:
        rows = con.execute(
            "SELECT id, number, key_date, title, volume, rating "
            "FROM gcd_issue "
            "WHERE series_id = ? AND variant_of_id IS NULL",
            (series_id,),
        ).fetchall()
        if wanted is None:
            return rows[:20]
        return [r for r in rows if normalize_issue(r["number"]) == wanted]

    def _to_candidate(self, series: sqlite3.Row, issue: sqlite3.Row) -> Candidate:
        md = GenericMetadata()
        md.series = series["series_name"]
        md.issue = (issue["number"] or "").strip() or None
        md.title = (issue["title"] or "").strip() or None
        md.publisher = series["publisher"]
        md.issue_count = series["issue_count"]
        md.language = series["language_iso"]
        md.volume = issue["volume"] if isinstance(issue["volume"], int) else None
        md.maturity_rating = (issue["rating"] or "").strip() or None
        year, month, day = _split_key_date(issue["key_date"])
        md.year, md.month, md.day = year, month, day
        md.web_link = f"https://www.comics.org/issue/{issue['id']}/"
        md.notes = f"GCD issue id {issue['id']}"
        md.is_empty = False
        return Candidate(
            source=self.name,
            metadata=md,
            series_name=series["series_name"] or "",
            issue_number=str(issue["number"] or ""),
            year=year,
            publisher=series["publisher"],
        )

    # ------------------------------------------------------------------
    def enrich(self, candidate: Candidate) -> Candidate:
        issue_id = _issue_id_from_notes(candidate.metadata.notes)
        if issue_id is None:
            return candidate
        con = self._connect()
        md = candidate.metadata

        stories = con.execute(
            "SELECT id, title, sequence_number, genre, synopsis, characters "
            "FROM gcd_story WHERE issue_id = ? AND type_id = ? "
            "ORDER BY sequence_number",
            (issue_id, STORY_TYPE_MAIN),
        ).fetchall()

        titles = [s["title"].strip() for s in stories if (s["title"] or "").strip()]
        if titles and not md.title:
            md.title = "; ".join(titles[:3])
        genres = {g.strip().capitalize()
                  for s in stories for g in (s["genre"] or "").split(";") if g.strip()}
        if genres:
            md.genre = ", ".join(sorted(genres))
        synopses = [s["synopsis"].strip() for s in stories if (s["synopsis"] or "").strip()]
        if synopses:
            md.comments = "\n\n".join(synopses)
        characters = {c.strip()
                      for s in stories for c in (s["characters"] or "").split(";")
                      if c.strip()}
        if characters:
            md.characters = ", ".join(sorted(characters))

        for person, role in self._credits(con, issue_id, [s["id"] for s in stories]):
            md.add_credit(person, role)
        return candidate

    def _credits(self, con, issue_id: int, story_ids: list[int]):
        seen: set[tuple[str, str]] = set()
        rows = con.execute(
            "SELECT c.credit_name AS role, n.name AS person "
            "FROM gcd_issue_credit c "
            "JOIN gcd_creator_name_detail n ON c.creator_id = n.id "
            "WHERE c.issue_id = ?",
            (issue_id,),
        ).fetchall()
        if story_ids:
            placeholders = ",".join("?" * len(story_ids))
            rows += con.execute(
                f"SELECT t.name AS role, n.name AS person "  # noqa: S608
                f"FROM gcd_story_credit sc "
                f"JOIN gcd_credit_type t ON t.id = sc.credit_type_id "
                f"JOIN gcd_creator_name_detail n ON n.id = sc.creator_id "
                f"WHERE sc.story_id IN ({placeholders})",
                story_ids,
            ).fetchall()
        for row in rows:
            role = CREDIT_MAP.get((row["role"] or "").strip().casefold())
            person = (row["person"] or "").strip()
            if role and person and (person, role) not in seen:
                seen.add((person, role))
                yield person, role


def _split_key_date(key_date: str | None):
    """GCD key_date ist 'YYYY-MM-DD' mit '00' fuer Unbekanntes."""
    if not key_date:
        return None, None, None
    parts = str(key_date).split("-")
    out = []
    for part in (parts + ["", "", ""])[:3]:
        try:
            value = int(part)
        except ValueError:
            value = 0
        out.append(value or None)
    return out[0], out[1], out[2]


def _issue_id_from_notes(notes: str | None) -> int | None:
    import re

    match = re.search(r"GCD issue id (\d+)", notes or "")
    return int(match.group(1)) if match else None
