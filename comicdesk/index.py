"""Sammlungs-Index: SQLite mit Volltextsuche ueber alle getaggten Comics.

Der Index ist reiner Cache - er laesst sich jederzeit neu aufbauen. Quelle der
Wahrheit bleibt das ComicInfo.xml in der jeweiligen Datei.
"""
from __future__ import annotations

import json
import os
import re
import sqlite3
import threading
import time
from dataclasses import dataclass
from pathlib import Path

from comicapi.genericmetadata import GenericMetadata
from PySide6.QtCore import QObject, Signal

from . import archive, provenance

SCHEMA_VERSION = 3

#: Name der Sammlung, die bei der Migration alter Indizes entsteht.
DEFAULT_COLLECTION = "Meine Comics"

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
    "quelle": "source", "source": "source",
}

#: Sonderfelder, die keine Textsuche sind.
BOOL_ALIASES = {"getaggt", "tagged"}
TRUE_WORDS = {"ja", "yes", "true", "1"}

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
class Collection:
    """Eine benannte Sammlung: ein Name und die Ordner, die dazugehoeren."""

    name: str
    roots: list[str]

    @property
    def paths(self) -> list[Path]:
        return [Path(r) for r in self.roots]


@dataclass
class Condition:
    column: str
    value: str


@dataclass
class ParsedQuery:
    fields: list[Condition]
    years: list[tuple[int, int]]
    free_text: list[str]
    tagged: bool | None = None

    @property
    def is_empty(self) -> bool:
        return not (self.fields or self.years or self.free_text
                    or self.tagged is not None)


def parse_query(text: str) -> ParsedQuery:
    """`serie:batman jahr:1990-1999 gotham` -> strukturierte Bedingungen."""
    fields: list[Condition] = []
    years: list[tuple[int, int]] = []
    free: list[str] = []
    tagged: bool | None = None
    for raw in _token_re.findall(text or ""):
        token = raw.strip()
        if not token:
            continue
        key, sep, value = token.partition(":")
        key_norm = key.strip().casefold()
        value = value.strip().strip('"')
        if sep and key_norm in BOOL_ALIASES and value:
            tagged = value.casefold() in TRUE_WORDS
            continue
        column = FIELD_ALIASES.get(key_norm) if sep else None
        if column is None or not value:
            free.append(token.strip('"'))
            continue
        if column == "year":
            span = _year_span(value)
            if span:
                years.append(span)
            continue
        fields.append(Condition(column, value))
    return ParsedQuery(fields, years, free, tagged)


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
                page_count INTEGER, has_tags INTEGER, source TEXT,
                indexed_at REAL
            );
            CREATE INDEX IF NOT EXISTS comics_parent ON comics(parent);
            CREATE INDEX IF NOT EXISTS comics_series ON comics(series);
            CREATE INDEX IF NOT EXISTS comics_year ON comics(year);
            CREATE VIRTUAL TABLE IF NOT EXISTS comics_fts
                USING fts5(path UNINDEXED, body, tokenize='unicode61');
            CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT);
            CREATE TABLE IF NOT EXISTS series_known (
                series TEXT, publisher TEXT, source TEXT,
                numbers TEXT, series_name TEXT, checked_at REAL,
                PRIMARY KEY (series, publisher)
            );
            """
        )
        self._migrate(con)
        con.execute("INSERT OR REPLACE INTO meta VALUES ('schema', ?)",
                    (str(SCHEMA_VERSION),))
        con.commit()

    def _migrate(self, con: sqlite3.Connection) -> None:
        """Alte Indizes ohne Sammlungsbegriff nachruesten."""
        columns = {row[1] for row in con.execute("PRAGMA table_info(comics)")}
        if "source" not in columns:
            con.execute("ALTER TABLE comics ADD COLUMN source TEXT")
        if "source_id" not in columns:
            con.execute("ALTER TABLE comics ADD COLUMN source_id TEXT")
            con.execute("ALTER TABLE comics ADD COLUMN issue_count INTEGER")
            con.execute("ALTER TABLE comics ADD COLUMN web_link TEXT")
            # Vorhandene Zeilen kennen die neuen Felder nicht; mtime
            # zurueckstellen, damit der naechste Lauf sie neu einliest.
            con.execute("UPDATE comics SET mtime = -1")
        if "collection" not in columns:
            con.execute("ALTER TABLE comics ADD COLUMN collection TEXT")
            con.execute("CREATE INDEX IF NOT EXISTS comics_collection "
                        "ON comics(collection)")
        row = con.execute("SELECT value FROM meta WHERE key='collections'").fetchone()
        if row:
            return
        # Frueher gab es genau eine Ordnerliste unter 'roots'.
        old = con.execute("SELECT value FROM meta WHERE key='roots'").fetchone()
        roots = [r for r in (old["value"].split("\n") if old else []) if r]
        collections = [{"name": DEFAULT_COLLECTION, "roots": roots}] if roots else []
        con.execute("INSERT OR REPLACE INTO meta VALUES ('collections', ?)",
                    (json.dumps(collections, ensure_ascii=False),))
        if roots:
            con.execute("UPDATE comics SET collection=? WHERE collection IS NULL",
                        (DEFAULT_COLLECTION,))

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

    def upsert(self, path: Path, md: GenericMetadata, page_count: int,
               collection: str | None = None) -> None:
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
            "collection": collection,
            "has_tags": 0 if md.is_empty else 1,
            "source": provenance.detect(md)[0],
            "source_id": provenance.source_id(md),
            "issue_count": md.issue_count,
            "web_link": md.web_link,
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

    def prune_missing(self, roots: list[Path] | None = None,
                      collection: str | None = None) -> int:
        """Eintraege wegwerfen, deren Datei es nicht mehr gibt."""
        con = self._con()
        if collection is None:
            rows = con.execute("SELECT path FROM comics").fetchall()
        else:
            rows = con.execute("SELECT path FROM comics WHERE collection=?",
                               (collection,)).fetchall()
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
    # --- Sammlungen ---------------------------------------------------
    def collections(self) -> list[Collection]:
        row = self._con().execute(
            "SELECT value FROM meta WHERE key='collections'").fetchone()
        if not row:
            return []
        try:
            raw = json.loads(row["value"])
        except json.JSONDecodeError:
            return []
        return [Collection(str(c.get("name", "")), list(c.get("roots", [])))
                for c in raw if c.get("name")]

    def set_collections(self, collections: list[Collection]) -> None:
        con = self._con()
        con.execute(
            "INSERT OR REPLACE INTO meta VALUES ('collections', ?)",
            (json.dumps([{"name": c.name, "roots": c.roots} for c in collections],
                        ensure_ascii=False),))
        con.commit()

    def collection(self, name: str) -> Collection | None:
        for entry in self.collections():
            if entry.name == name:
                return entry
        return None

    def add_collection(self, name: str, roots: list[str] | None = None) -> bool:
        existing = self.collections()
        if any(c.name == name for c in existing):
            return False
        existing.append(Collection(name, roots or []))
        self.set_collections(existing)
        return True

    def rename_collection(self, old: str, new: str) -> None:
        collections = self.collections()
        if any(c.name == new for c in collections):
            return
        for entry in collections:
            if entry.name == old:
                entry.name = new
        self.set_collections(collections)
        con = self._con()
        con.execute("UPDATE comics SET collection=? WHERE collection=?", (new, old))
        con.commit()

    def delete_collection(self, name: str) -> None:
        self.set_collections([c for c in self.collections() if c.name != name])
        con = self._con()
        con.execute(
            "DELETE FROM comics_fts WHERE path IN "
            "(SELECT path FROM comics WHERE collection=?)", (name,))
        con.execute("DELETE FROM comics WHERE collection=?", (name,))
        con.commit()

    def count(self, collection: str | None = None) -> int:
        if collection is None:
            return self._con().execute("SELECT COUNT(*) FROM comics").fetchone()[0]
        return self._con().execute(
            "SELECT COUNT(*) FROM comics WHERE collection=?",
            (collection,)).fetchone()[0]

    def collection_for(self, path: Path) -> str | None:
        """Zu welcher Sammlung gehoert dieser Pfad?"""
        for entry in self.collections():
            if any(_is_within(path, root) for root in entry.paths):
                return entry.name
        return None

    def search(self, text: str, limit: int = 2000,
               collection: str | None = None) -> list[Path]:
        query = parse_query(text)
        if query.is_empty:
            return []
        where: list[str] = []
        params: list = []
        if collection is not None:
            where.append("c.collection = ?")
            params.append(collection)

        for cond in query.fields:
            where.append(f"c.{cond.column} LIKE ? ESCAPE '\\'")  # noqa: S608
            params.append(f"%{_escape_like(cond.value)}%")
        for start, end in query.years:
            where.append("c.year BETWEEN ? AND ?")
            params.extend([start, end])
        if query.tagged is not None:
            where.append("COALESCE(c.has_tags, 0) = ?")
            params.append(1 if query.tagged else 0)

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

    def status_for(self, paths: list[Path]) -> dict[str, tuple[bool, str | None]]:
        """Pfad -> (hat Tags, Quelle). Fuer die Markierung in der Kachelansicht."""
        if not paths:
            return {}
        out: dict[str, tuple[bool, str | None]] = {}
        con = self._con()
        chunk = 400
        keys = [str(p) for p in paths]
        for start in range(0, len(keys), chunk):
            part = keys[start:start + chunk]
            placeholders = ",".join("?" * len(part))
            rows = con.execute(
                f"SELECT path, has_tags, source FROM comics "  # noqa: S608
                f"WHERE path IN ({placeholders})", part).fetchall()
            for row in rows:
                out[row["path"]] = (bool(row["has_tags"]), row["source"])
        return out

    # --- Vollstaendigkeit je Reihe ------------------------------------
    def series_rows(self, collection: str | None = None):
        sql = ("SELECT path, series, publisher, issue, issue_sort, source, "
               "source_id, issue_count FROM comics "
               "WHERE series IS NOT NULL AND series != ''")
        params: list = []
        if collection is not None:
            sql += " AND collection = ?"
            params.append(collection)
        return self._con().execute(sql, params).fetchall()

    def save_known(self, series: str, publisher: str, source: str,
                   numbers: list[str], series_name: str = "") -> None:
        con = self._con()
        con.execute(
            "INSERT OR REPLACE INTO series_known VALUES (?,?,?,?,?,?)",
            (series, publisher or "", source, "\n".join(numbers),
             series_name, time.time()))
        con.commit()

    def load_known(self) -> dict[tuple[str, str], tuple[str, list[str], str]]:
        out: dict[tuple[str, str], tuple[str, list[str], str]] = {}
        for row in self._con().execute(
            "SELECT series, publisher, source, numbers, series_name "
            "FROM series_known"
        ):
            numbers = [n for n in (row["numbers"] or "").split("\n") if n]
            out[(row["series"], row["publisher"])] = (
                row["source"], numbers, row["series_name"] or "")
        return out

    def forget_known(self, series: str, publisher: str) -> None:
        con = self._con()
        con.execute("DELETE FROM series_known WHERE series=? AND publisher=?",
                    (series, publisher or ""))
        con.commit()

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
                 force: bool = False, collection: str | None = None):
        super().__init__()
        self.roots = roots
        self.index = index
        self.force = force
        self.collection = collection
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
                self.index.upsert(path, md, pages, self.collection)
                updated += 1
            except Exception:  # noqa: BLE001
                skipped += 1
        removed = self.index.prune_missing(self.roots, self.collection)
        self.finished.emit(updated, skipped, removed)
