"""Grand Comics Database als lokale Quelle.

Die GCD hat keine oeffentliche API, stellt aber alle zwei Wochen SQLite-Dumps
bereit: https://www.comics.org/download/ (Account noetig, Daten unter CC-BY).
Das Schema hier ist gegen den `gcd-talker` (ComicTagger-Plugin) verifiziert.

Staerke gegenueber ComicVine: europaeische und deutsche Verlage sind gut
erfasst. Schwaeche: der Dump enthaelt keine Cover-URLs, es gibt also keine
Bild-Verifikation.
"""
from __future__ import annotations

import hashlib
import re
import sqlite3
import threading
from collections.abc import Callable
from pathlib import Path

from comicapi.genericmetadata import GenericMetadata

from ..i18n import _
from .base import (
    Candidate, MetadataProvider, SearchQuery, normalize_issue,
)

# gcd_story.type_id 19 == "cover"-freie Hauptgeschichte laut GCD-Schema
STORY_TYPE_MAIN = 19

#: GCD kennzeichnet nummernlose Ausgaben so - Einzelalben, Sonderbaende.
#: Ortsueblich tragen die lokal die Nummer 1, danach wird also auch gesucht.
NO_NUMBER = "[nn]"

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
        self._fts_checked = False
        self._fts_ready = False

    # ------------------------------------------------------------------
    @property
    def on_network(self) -> bool:
        """Liegt der Dump auf einem Netzlaufwerk? Dann ist er zaeh."""
        if not self.db_path:
            return False
        try:
            with open("/proc/mounts", encoding="utf-8") as handle:
                mounts = [line.split() for line in handle]
        except OSError:
            return False
        network = {"cifs", "smbfs", "nfs", "nfs4", "sshfs", "fuse.sshfs", "afpfs"}
        best, kind = "", ""
        target = str(self.db_path.resolve())
        for parts in mounts:
            if len(parts) < 3:
                continue
            point, fstype = parts[1], parts[2]
            if target.startswith(point) and len(point) > len(best):
                best, kind = point, fstype
        return kind in network

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
            # immutable=1 statt mode=ro: der Dump aendert sich nicht, und
            # SQLite-Sperren funktionieren auf Netzlaufwerken (CIFS/NFS) nicht
            # zuverlaessig - ohne das gibt es "database is locked".
            con = sqlite3.connect(f"file:{self.db_path}?immutable=1", uri=True)
            con.row_factory = sqlite3.Row
            con.text_factory = str
            self._local.con = con
        return con

    # --- Volltextsuche ueber die Serientitel ---------------------------
    # Der Dump bringt zwar Indizes mit, aber `LIKE '%...%'` kann keinen davon
    # nutzen: SQLite scannt alle ~231.000 Serien, ueber ein Netzlaufwerk sind
    # das ~16 Sekunden pro Suche. Eine FTS5-Tabelle macht daraus 0,2 ms.
    # Sie liegt in einer eigenen kleinen Datei - der Dump bleibt unangetastet.
    @property
    def fts_path(self) -> Path | None:
        if not self.db_path:
            return None
        from ..index import data_dir

        try:
            stat = self.db_path.stat()
            key = f"{self.db_path.resolve()}|{stat.st_size}|{stat.st_mtime_ns}"
        except OSError:
            return None
        digest = hashlib.sha1(key.encode()).hexdigest()[:16]
        return data_dir() / f"gcd-fts-{digest}.sqlite"

    @property
    def fts_ready(self) -> bool:
        """Liegt zum aktuellen Dump ein brauchbarer Volltextindex vor?"""
        if self._fts_checked:
            return self._fts_ready
        self._fts_checked = True
        path = self.fts_path
        self._fts_ready = False
        if path and path.is_file():
            try:
                con = sqlite3.connect(f"file:{path}?immutable=1", uri=True)
                con.execute("SELECT rowid FROM series_fts LIMIT 1").fetchone()
                con.close()
                self._fts_ready = True
            except sqlite3.Error:
                self._fts_ready = False
        return self._fts_ready

    def build_fts(self, progress: Callable[[str, int], None] | None = None,
                  should_stop: Callable[[], bool] | None = None) -> bool:
        """Volltextindex aufbauen. Gibt False zurueck, wenn abgebrochen wurde."""
        target = self.fts_path
        if target is None:
            return False

        def report(text: str, percent: int) -> None:
            if progress:
                progress(text, percent)

        report(_("Serientitel werden gelesen …"), 5)
        rows = self._connect().execute("SELECT id, name FROM gcd_series").fetchall()
        if should_stop and should_stop():
            return False

        report(_("Volltextindex wird aufgebaut …"), 60)
        tmp = target.with_suffix(".tmp")
        tmp.unlink(missing_ok=True)
        try:
            con = sqlite3.connect(str(tmp))
            con.execute(
                "CREATE VIRTUAL TABLE series_fts USING fts5("
                "name, content='', tokenize='unicode61 remove_diacritics 2')")
            con.executemany("INSERT INTO series_fts(rowid, name) VALUES (?,?)",
                            ((r["id"], r["name"] or "") for r in rows))
            con.commit()
            con.close()
            if should_stop and should_stop():
                tmp.unlink(missing_ok=True)
                return False
            tmp.replace(target)
        except Exception:
            tmp.unlink(missing_ok=True)
            raise
        # Alte Indizes zu frueheren Dumps wegraeumen.
        for old in target.parent.glob("gcd-fts-*.sqlite"):
            if old != target:
                old.unlink(missing_ok=True)
        self._fts_checked = False
        report(_("Fertig: {count} Serien durchsuchbar.").format(count=len(rows)), 100)
        return True

    def _fts_series_ids(self, term: str, limit: int = 400) -> list[int] | None:
        """Serien-IDs zum Suchbegriff, oder None wenn kein Index da ist."""
        if not self.fts_ready:
            return None
        path = self.fts_path
        con = getattr(self._local, "fts", None)
        if con is None:
            con = sqlite3.connect(f"file:{path}?immutable=1", uri=True)
            self._local.fts = con
        cleaned = re.sub(r'[^\w\s]', " ", term).strip()
        if not cleaned:
            return []
        query = " ".join(f'"{w}"' for w in cleaned.split())
        try:
            return [r[0] for r in con.execute(
                "SELECT rowid FROM series_fts WHERE series_fts MATCH ? LIMIT ?",
                (query, limit))]
        except sqlite3.Error:
            return None

    # ------------------------------------------------------------------
    def search(self, query: SearchQuery, limit: int = 20) -> list[Candidate]:
        if not query.series:
            return []
        con = self._connect()
        base = (
            "SELECT s.id, s.name AS series_name, s.year_began, s.issue_count, "
            "       p.name AS publisher, l.code AS language_iso "
            "FROM gcd_series s "
            "LEFT JOIN gcd_publisher p ON s.publisher_id = p.id "
            "LEFT JOIN stddata_language l ON s.language_id = l.id "
        )
        params: list = []
        ids = self._fts_series_ids(query.series)
        if ids is not None:
            if not ids:
                return []
            placeholders = ",".join("?" * len(ids))
            sql = base + f"WHERE s.id IN ({placeholders}) "  # noqa: S608
            params.extend(ids)
        else:
            # Ohne Volltextindex bleibt nur der langsame Weg.
            sql = base + "WHERE s.name LIKE ? "
            params.append(f"%{query.series}%")
        if self.language:
            sql += "AND l.code = ? "
            params.append(self.language)
        sql += "LIMIT 60"
        series_rows = con.execute(sql, params).fetchall()

        if query.title:
            # Reihen mit passendem Bandtitel nach vorn. Ohne das faellt die
            # richtige Reihe durch die Ergebnisgrenze, sobald es den
            # Serienname mehrfach gibt - genau dann hilft der Titel aber.
            treffer = self._series_with_title(con, [r["id"] for r in series_rows],
                                              query.title)
            if treffer:
                series_rows.sort(key=lambda r: r["id"] not in treffer)
        candidates: list[Candidate] = []
        wanted = normalize_issue(query.issue) if query.issue else None
        for series in series_rows:
            for issue in self._issues(con, series["id"], wanted, query.title):
                candidates.append(self._to_candidate(series, issue))
                if len(candidates) >= limit:
                    return candidates
        return candidates

    def _series_with_title(self, con, series_ids: list[int],
                           title: str) -> set[int]:
        if not series_ids:
            return set()
        platzhalter = ",".join("?" * len(series_ids))
        muster = f"%{title}%"
        rows = con.execute(
            "SELECT DISTINCT i.series_id FROM gcd_issue i "  # noqa: S608
            "LEFT JOIN gcd_story st ON st.issue_id = i.id "
            f"WHERE i.series_id IN ({platzhalter}) "
            "AND (i.title LIKE ? OR st.title LIKE ?)",
            [*series_ids, muster, muster]).fetchall()
        return {r[0] for r in rows}

    def _issues(self, con, series_id: int, wanted: str | None,
                title: str | None = None) -> list[sqlite3.Row]:
        columns = "i.id, i.number, i.key_date, i.title, i.volume, i.rating"
        if title:
            # Nach Bandtitel suchen - bei mehreren gleichnamigen Reihen ist das
            # oft das Einzige, was die richtige Ausgabe verraet. Der Titel steht
            # meist nicht am Heft, sondern an der Hauptgeschichte.
            rows = con.execute(
                f"SELECT DISTINCT {columns}, st.title AS story_title "  # noqa: S608
                "FROM gcd_issue i LEFT JOIN gcd_story st ON st.issue_id = i.id "
                "WHERE i.series_id = ? AND i.variant_of_id IS NULL "
                "AND (i.title LIKE ? OR st.title LIKE ?) LIMIT 20",
                (series_id, f"%{title}%", f"%{title}%")).fetchall()
            if rows:
                return rows
        if wanted is None:
            return con.execute(
                f"SELECT {columns} FROM gcd_issue i "  # noqa: S608
                "WHERE i.series_id = ? AND i.variant_of_id IS NULL LIMIT 20",
                (series_id,)).fetchall()
        # Grob in SQL vorfiltern (Serien koennen tausende Hefte haben), dann
        # exakt vergleichen - "007", "#7" und "7" sollen dasselbe treffen.
        # [nn] muss mit durch, sonst faellt jedes Einzelalbum heraus.
        rows = con.execute(
            f"SELECT {columns} FROM gcd_issue i "  # noqa: S608
            "WHERE i.series_id = ? AND i.variant_of_id IS NULL "
            "AND (i.number = ? OR i.number LIKE ? OR i.number = ?) LIMIT 40",
            (series_id, wanted, f"%{wanted}%", NO_NUMBER)).fetchall()
        return [r for r in rows if _issue_matches(r["number"], wanted)]

    def _to_candidate(self, series: sqlite3.Row, issue: sqlite3.Row) -> Candidate:
        md = GenericMetadata()
        md.series = series["series_name"]
        nummer = (issue["number"] or "").strip()
        if nummer == NO_NUMBER:
            nummer = "1"   # nummernloses Album - lokal heisst das ueblich 1
        md.issue = nummer or None
        titel = (issue["title"] or "").strip()
        if not titel and "story_title" in issue.keys():
            # Ueber den Bandtitel gefunden - der steht an der Geschichte.
            titel = (issue["story_title"] or "").strip()
        md.title = titel or None
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
            issue_number=nummer,
            year=year,
            publisher=series["publisher"],
        )

    def series_issues(self, source_id: str) -> tuple[str, list[str]] | None:
        try:
            issue_id = int(source_id)
        except (TypeError, ValueError):
            return None
        con = self._connect()
        row = con.execute(
            "SELECT s.id, s.name FROM gcd_issue i "
            "JOIN gcd_series s ON s.id = i.series_id WHERE i.id = ?",
            (issue_id,)).fetchone()
        if row is None:
            return None
        numbers = [str(r[0]).strip() for r in con.execute(
            "SELECT number FROM gcd_issue "
            "WHERE series_id = ? AND variant_of_id IS NULL", (row["id"],))
            if r[0] and str(r[0]).strip()]
        return row["name"], sorted(set(numbers), key=_sort_key)

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


def _issue_matches(number, wanted: str) -> bool:
    """Nummer aus der GCD mit der gesuchten vergleichen."""
    roh = (number or "").strip()
    if roh == NO_NUMBER:
        return wanted in ("1", "0")
    return normalize_issue(roh) == wanted


def _sort_key(text: str):
    try:
        return (0, float(text))
    except ValueError:
        return (1, text)


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
