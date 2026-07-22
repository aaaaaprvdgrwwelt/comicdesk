"""Sammlungs-Index: SQLite mit Volltextsuche ueber alle getaggten Comics.

Der Index ist reiner Cache - er laesst sich jederzeit neu aufbauen. Quelle der
Wahrheit bleibt das ComicInfo.xml in der jeweiligen Datei.
"""
from __future__ import annotations

import os
import re
import sqlite3
import threading
import time
from dataclasses import dataclass
from pathlib import Path

from comicapi.genericmetadata import GenericMetadata
from PySide6.QtCore import QObject, Signal

from . import archive

SCHEMA_VERSION = 1

#: Suchpraefix -> Spalte. Deutsch und englisch, damit beides funktioniert.
FIELD_ALIASES = {
    "serie": "series", "series": "series",
    "nummer": "issue", "heft": "issue", "issue": "issue",
    "titel": "title", "title": "title",
    "jahr": "year", "year": "year",
    "verlag": "publisher", "publisher": "publisher",
    "imprint": "imprint",
    "genre": "genre",
    "sprache": "language", "language": "language",
    "figur": "characters", "charakter": "characters", "character": "characters",
    "team": "teams", "teams": "teams",
    "ort": "locations", "location": "locations",
    "arc": "story_arc", "story_arc": "story_arc",
    "tag": "tags", "tags": "tags",
    "autor": "credits", "zeichner": "credits", "person": "credits",
    "creator": "credits", "credits": "credits",
    "datei": "name", "name": "name", "file": "name",
}

TEXT_COLUMNS = [
    "series", "issue", "title", "publisher", "imprint", "genre", "language",
    "characters", "teams", "locations", "story_arc", "tags", "credits",
    "comments", "name",
]

_token_re = re.compile(r'"[^"]*"|\S+')


def data_dir() -> Path:
    base = os.environ.get("XDG_DATA_HOME") or (Path.home() / ".local" / "share")
    path = Path(base) / "comicdesk"
    path.mkdir(parents=True, exist_ok=True)
    return path


@dataclass
class Condition:
    column: str
    value: str


@dataclass
class ParsedQuery:
    fields: list[Condition]
    years: list[tuple[int, int]]
    free_text: list[str]

    @property
    def is_empty(self) -> bool:
        return not (self.fields or self.years or self.free_text)


def parse_query(text: str) -> ParsedQuery:
    """`serie:batman jahr:1990-1999 gotham` -> strukturierte Bedingungen."""
    fields: list[Condition] = []
    years: list[tuple[int, int]] = []
    free: list[str] = []
    for raw in _token_re.findall(text or ""):
        token = raw.strip()
        if not token:
            continue
        key, sep, value = token.partition(":")
        column = FIELD_ALIASES.get(key.strip().casefold()) if sep else None
        value = value.strip().strip('"')
        if column is None or not value:
            free.append(token.strip('"'))
            continue
        if column == "year":
            span = _year_span(value)
            if span:
                years.append(span)
            continue
        fields.append(Condition(column, value))
    return ParsedQuery(fields, years, free)


def _year_span(value: str) -> tuple[int, int] | None:
    match = re.fullmatch(r"(\d{4})\s*-\s*(\d{4})", value)
    if match:
        return int(match.group(1)), int(match.group(2))
    if value.isdigit() and len(value) == 4:
        return int(value), int(value)
    return None


# ---------------------------------------------------------------------------
class CollectionIndex:
    """Thread-sicher ueber getrennte Verbindungen pro Thread."""

    def __init__(self, path: Path | None = None):
        self.path = path or (data_dir() / "index.sqlite")
        self._local = threading.local()
        self._ensure_schema()

    def _con(self) -> sqlite3.Connection:
        con = getattr(self._local, "con", None)
        if con is None:
            con = sqlite3.connect(str(self.path))
            con.row_factory = sqlite3.Row
            con.execute("PRAGMA journal_mode=WAL")
            self._local.con = con
        return con

    def _ensure_schema(self) -> None:
        con = self._con()
        con.executescript(
            """
            CREATE TABLE IF NOT EXISTS comics (
                path TEXT PRIMARY KEY,
                parent TEXT, name TEXT,
                mtime REAL, size INTEGER,
                series TEXT, issue TEXT, issue_sort REAL, title TEXT,
                year INTEGER, publisher TEXT, imprint TEXT, genre TEXT,
                language TEXT, characters TEXT, teams TEXT, locations TEXT,
                story_arc TEXT, tags TEXT, credits TEXT, comments TEXT,
                page_count INTEGER, has_tags INTEGER, indexed_at REAL
            );
            CREATE INDEX IF NOT EXISTS comics_parent ON comics(parent);
            CREATE INDEX IF NOT EXISTS comics_series ON comics(series);
            CREATE INDEX IF NOT EXISTS comics_year ON comics(year);
            CREATE VIRTUAL TABLE IF NOT EXISTS comics_fts
                USING fts5(path UNINDEXED, body, tokenize='unicode61');
            CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT);
            """
        )
        con.execute("INSERT OR REPLACE INTO meta VALUES ('schema', ?)",
                    (str(SCHEMA_VERSION),))
        con.commit()

    # --- Schreiben ----------------------------------------------------
    def needs_update(self, path: Path) -> bool:
        try:
            stat = path.stat()
        except OSError:
            return False
        row = self._con().execute(
            "SELECT mtime, size FROM comics WHERE path=?", (str(path),)
        ).fetchone()
        return not row or row["mtime"] != stat.st_mtime or row["size"] != stat.st_size

    def upsert(self, path: Path, md: GenericMetadata, page_count: int) -> None:
        stat = path.stat()
        credits = ", ".join(
            f"{c.get('person', '')}" for c in (md.credits or []) if c.get("person")
        )
        tags = ", ".join(sorted(md.tags or []))
        values = {
            "path": str(path),
            "parent": str(path.parent),
            "name": path.name,
            "mtime": stat.st_mtime,
            "size": stat.st_size,
            "series": md.series,
            "issue": md.issue,
            "issue_sort": _issue_sort(md.issue),
            "title": md.title,
            "year": md.year,
            "publisher": md.publisher,
            "imprint": md.imprint,
            "genre": md.genre,
            "language": md.language,
            "characters": md.characters,
            "teams": md.teams,
            "locations": md.locations,
            "story_arc": md.story_arc,
            "tags": tags,
            "credits": credits,
            "comments": md.comments,
            "page_count": page_count,
            "has_tags": 0 if md.is_empty else 1,
            "indexed_at": time.time(),
        }
        columns = ", ".join(values)
        placeholders = ", ".join(f":{k}" for k in values)
        con = self._con()
        con.execute(
            f"INSERT OR REPLACE INTO comics ({columns}) VALUES ({placeholders})",  # noqa: S608
            values,
        )
        body = " ".join(str(values[c]) for c in TEXT_COLUMNS if values.get(c))
        con.execute("DELETE FROM comics_fts WHERE path=?", (str(path),))
        con.execute("INSERT INTO comics_fts (path, body) VALUES (?, ?)",
                    (str(path), body))
        con.commit()

    def remove(self, path: Path) -> None:
        con = self._con()
        con.execute("DELETE FROM comics WHERE path=?", (str(path),))
        con.execute("DELETE FROM comics_fts WHERE path=?", (str(path),))
        con.commit()

    def prune_missing(self, roots: list[Path] | None = None) -> int:
        """Eintraege wegwerfen, deren Datei es nicht mehr gibt."""
        con = self._con()
        rows = con.execute("SELECT path FROM comics").fetchall()
        gone = []
        for row in rows:
            path = Path(row["path"])
            if roots and not any(_is_within(path, r) for r in roots):
                continue
            if not path.exists():
                gone.append(row["path"])
        for path in gone:
            con.execute("DELETE FROM comics WHERE path=?", (path,))
            con.execute("DELETE FROM comics_fts WHERE path=?", (path,))
        con.commit()
        return len(gone)

    # --- Lesen --------------------------------------------------------
    def count(self) -> int:
        return self._con().execute("SELECT COUNT(*) FROM comics").fetchone()[0]

    def roots(self) -> list[str]:
        rows = self._con().execute(
            "SELECT value FROM meta WHERE key='roots'").fetchone()
        return [r for r in (rows["value"].split("\n") if rows else []) if r]

    def set_roots(self, roots: list[str]) -> None:
        con = self._con()
        con.execute("INSERT OR REPLACE INTO meta VALUES ('roots', ?)",
                    ("\n".join(roots),))
        con.commit()

    def search(self, text: str, limit: int = 2000) -> list[Path]:
        query = parse_query(text)
        if query.is_empty:
            return []
        where: list[str] = []
        params: list = []

        for cond in query.fields:
            where.append(f"c.{cond.column} LIKE ? ESCAPE '\\'")  # noqa: S608
            params.append(f"%{_escape_like(cond.value)}%")
        for start, end in query.years:
            where.append("c.year BETWEEN ? AND ?")
            params.extend([start, end])

        sql = "SELECT c.path FROM comics c"
        if query.free_text:
            sql += " JOIN comics_fts f ON f.path = c.path"
            where.append("comics_fts MATCH ?")
            params.append(" AND ".join(_fts_term(t) for t in query.free_text))
        if where:
            sql += " WHERE " + " AND ".join(where)
        sql += " ORDER BY c.series, c.issue_sort, c.name LIMIT ?"
        params.append(limit)

        rows = self._con().execute(sql, params).fetchall()
        return [Path(r["path"]) for r in rows]

    def distinct(self, column: str, limit: int = 500) -> list[str]:
        """Fuer Vorschlaege - z.B. alle vorkommenden Verlage."""
        if column not in TEXT_COLUMNS:
            return []
        rows = self._con().execute(
            f"SELECT DISTINCT {column} AS v FROM comics "  # noqa: S608
            f"WHERE {column} IS NOT NULL AND {column} != '' "
            f"ORDER BY v LIMIT ?", (limit,),
        ).fetchall()
        return [r["v"] for r in rows]

    def all_tags(self) -> list[str]:
        seen: set[str] = set()
        for row in self._con().execute(
            "SELECT tags FROM comics WHERE tags IS NOT NULL AND tags != ''"
        ):
            seen.update(t.strip() for t in row["tags"].split(",") if t.strip())
        return sorted(seen)


def _escape_like(value: str) -> str:
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def _fts_term(term: str) -> str:
    cleaned = re.sub(r'["*]', " ", term).strip()
    return f'"{cleaned}"*' if cleaned else '""'


def _issue_sort(issue: str | None) -> float | None:
    if not issue:
        return None
    match = re.search(r"\d+(?:\.\d+)?", str(issue))
    return float(match.group(0)) if match else None


def _is_within(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
    except ValueError:
        return False
    return True


# ---------------------------------------------------------------------------
class IndexScanner(QObject):
    """Durchsucht Ordner rekursiv und aktualisiert den Index."""

    progress = Signal(int, int, str)   # erledigt, gefunden, Dateiname
    finished = Signal(int, int, int)   # neu/aktualisiert, uebersprungen, entfernt

    def __init__(self, roots: list[Path], index: CollectionIndex,
                 force: bool = False):
        super().__init__()
        self.roots = roots
        self.index = index
        self.force = force
        self._stop = False

    def stop(self) -> None:
        self._stop = True

    def run(self) -> None:
        files: list[Path] = []
        for root in self.roots:
            for dirpath, dirnames, filenames in os.walk(root):
                dirnames[:] = [d for d in dirnames if not d.startswith(".")]
                for name in filenames:
                    path = Path(dirpath) / name
                    if archive.is_comic(path):
                        files.append(path)
        updated = skipped = 0
        for i, path in enumerate(files, 1):
            if self._stop:
                break
            self.progress.emit(i, len(files), path.name)
            if not self.force and not self.index.needs_update(path):
                skipped += 1
                continue
            try:
                comic = archive.open_comic(path)
                try:
                    md = comic.read_metadata()
                    pages = comic.page_count
                finally:
                    comic.close()
                self.index.upsert(path, md, pages)
                updated += 1
            except Exception:  # noqa: BLE001
                skipped += 1
        removed = self.index.prune_missing(self.roots)
        self.index.set_roots([str(r) for r in self.roots])
        self.finished.emit(updated, skipped, removed)
