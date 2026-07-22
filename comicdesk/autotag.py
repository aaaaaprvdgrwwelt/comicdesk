"""Automatisches Taggen: Kandidaten bewerten und ab Schwellwert schreiben."""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from comicapi.filenameparser import FileNameParser
from comicapi.genericmetadata import GenericMetadata
from PySide6.QtCore import QObject, QThread, Signal

from . import archive
from .i18n import _
from .providers.base import (
    ROLE_SUPPLEMENT, Candidate, MetadataProvider, SearchQuery, normalize_issue,
    series_similarity,
)

DEFAULT_THRESHOLD = 80

# Gewichte der Einzelsignale. Nicht verfuegbare Signale fallen samt Gewicht
# raus, damit ein Treffer ohne Cover nicht automatisch schlechter dasteht.
W_SERIES = 45
W_ISSUE = 20
W_YEAR = 25
W_TITLE = 35
W_PUBLISHER = 10
W_COVER = 40


@dataclass
class Result:
    path: Path
    status: str              # "getaggt" | "unsicher" | "kein Treffer" | "Fehler"
    score: int = 0
    source: str = ""
    summary: str = ""
    detail: str = ""


@dataclass
class AutoTagConfig:
    threshold: int = DEFAULT_THRESHOLD
    use_cover_match: bool = True
    overwrite_existing: bool = False
    #: Vorhandene Tags verwerfen statt die neuen darueberzulegen.
    replace_existing: bool = False
    providers: list[MetadataProvider] = field(default_factory=list)


# ---------------------------------------------------------------------------
def build_query(path: Path, md: GenericMetadata, cover: bytes | None) -> SearchQuery:
    """Was wir ueber das Heft wissen - Tags schlagen Dateinamen."""
    parser = FileNameParser()
    parser.parse_filename(path.name)
    nummer = (parser.issue or "").strip()
    reihe = (parser.series or "").strip()
    # Der Parser erfindet eine Heftnummer, wo keine steht:
    #   "3 Sekunden (2012).cbz" -> Nummer 2012 (die Jahreszahl)
    #   "24.cbz"                -> Nummer 24 (der Serienname selbst)
    # Danach zu suchen findet garantiert nichts, also lieber ohne Nummer
    # suchen und ueber Serienname und Jahr bewerten.
    if nummer and nummer in ((parser.year or "").strip(), reihe):
        nummer = ""
    return SearchQuery(
        series=(md.series or parser.series or "").strip(),
        issue=(md.issue or nummer).strip() or None,
        year=md.year or (int(parser.year) if str(parser.year).isdigit() else None),
        publisher=md.publisher,
        cover=cover,
    )


def cover_similarity(a: bytes | None, b: bytes | None) -> float | None:
    """0..1 anhand des perceptual hash. None, wenn nicht berechenbar."""
    if not a or not b:
        return None
    try:
        from comictaggerlib.imagehasher import ImageHasher

        hash_a = ImageHasher(data=a).average_hash()
        hash_b = ImageHasher(data=b).average_hash()
        distance = ImageHasher.hamming_distance(hash_a, hash_b)
    except Exception:  # noqa: BLE001
        return None
    # Zufaellige Bilder liegen bei ~32 von 64 Bit Abstand, darum dort die Null.
    return max(0.0, 1.0 - distance / 32.0)


def score_candidate(query: SearchQuery, candidate: Candidate,
                    cover_sim: float | None = None) -> int:
    parts: list[tuple[int, float]] = [
        (W_SERIES, series_similarity(query.series, candidate.series_name))
    ]
    if query.issue:
        match = normalize_issue(query.issue) == normalize_issue(candidate.issue_number)
        parts.append((W_ISSUE, 1.0 if match else 0.0))
        if not match:
            return 0  # falsche Heftnummer disqualifiziert sofort
    if query.year and candidate.year:
        delta = abs(query.year - candidate.year)
        parts.append((W_YEAR, 1.0 if delta == 0 else 0.6 if delta == 1 else 0.0))
    if query.title:
        # Wer einen Bandtitel angibt, meint ihn. Ausgaben ohne Titel duerfen
        # dann nicht mit voller Punktzahl davonkommen, sonst gewinnt weiter
        # die namensgleiche Reihe ohne den gesuchten Band.
        eigener = candidate.metadata.title or ""
        parts.append((W_TITLE, series_similarity(query.title, eigener)
                      if eigener else 0.0))
    if query.publisher and candidate.publisher:
        parts.append((W_PUBLISHER,
                      series_similarity(query.publisher, candidate.publisher)))
    if cover_sim is not None:
        parts.append((W_COVER, cover_sim))

    total_weight = sum(w for w, _ in parts)
    if not total_weight:
        return 0
    return round(100 * sum(w * v for w, v in parts) / total_weight)


def read_query(path: Path) -> tuple[SearchQuery | None, bytes | None]:
    """Was ueber die Datei bekannt ist - Tags schlagen Dateinamen."""
    comic = archive.open_comic(path)
    try:
        existing = comic.read_metadata()
        cover = comic.page_bytes(0) if comic.page_count else None
    finally:
        comic.close()
    query = build_query(path, existing, cover)
    return (query if query.series else None), cover


def collect_candidates(query: SearchQuery, config: AutoTagConfig,
                       cover: bytes | None = None,
                       should_stop: Callable[[], bool] | None = None
                       ) -> tuple[list[Candidate], str]:
    """Alle bewerteten Kandidaten, bester zuerst.

    Getrennt von `identify`, damit die Auswahl von Hand dieselben Treffer
    sieht wie die Automatik - sonst waere unklar, warum ein Vorschlag fehlt.
    """
    stopped = should_stop or (lambda: False)
    gefunden: list[Candidate] = []
    notes: list[str] = []
    for provider in config.providers:
        if stopped():
            break
        if provider.role == ROLE_SUPPLEMENT:
            continue  # ergaenzt nur, bestimmt nie das Heft
        ok, why = provider.available()
        if not ok:
            notes.append(f"{_(provider.label)}: {why}")
            continue
        try:
            candidates = provider.search(query)
        except Exception as exc:  # noqa: BLE001
            notes.append(f"{_(provider.label)}: {exc}")
            continue
        for candidate in candidates:
            if stopped():
                break
            sim = None
            if config.use_cover_match and provider.has_covers and cover:
                sim = cover_similarity(cover, provider.fetch_cover(candidate))
            candidate.score = score_candidate(query, candidate, sim)
            if sim is not None:
                candidate.reasons.append(
                    _("Cover-Aehnlichkeit {value}").format(value=f"{sim:.0%}"))
            gefunden.append(candidate)
    gefunden.sort(key=lambda c: -c.score)
    return gefunden, "; ".join(notes)


def identify(path: Path, config: AutoTagConfig,
             should_stop: Callable[[], bool] | None = None
             ) -> tuple[Candidate | None, str, SearchQuery | None]:
    """Besten Kandidaten fuer eine Datei suchen."""
    query, cover = read_query(path)
    if query is None:
        return None, _("Serienname weder in Tags noch im Dateinamen erkennbar."), None
    gefunden, notes = collect_candidates(query, config, cover, should_stop)
    return (gefunden[0] if gefunden else None), notes, query




#: Felder, die eine Ergaenzungsquelle fuellen darf - aber nur wenn sie leer sind.
SUPPLEMENT_FIELDS = ("genre", "comments", "manga", "volume_count",
                     "maturity_rating")


def apply_supplements(md: GenericMetadata, query: SearchQuery,
                      providers: list[MetadataProvider]) -> list[str]:
    """Leerstellen von Ergaenzungsquellen fuellen. Nichts wird ueberschrieben."""
    used: list[str] = []
    for provider in providers:
        if provider.role != ROLE_SUPPLEMENT or not provider.available()[0]:
            continue
        try:
            extra = provider.series_info(query)
        except Exception:  # noqa: BLE001
            continue
        if extra is None:
            continue
        filled = False
        for field_name in SUPPLEMENT_FIELDS:
            value = getattr(extra, field_name, None)
            if value and not getattr(md, field_name, None):
                setattr(md, field_name, value)
                filled = True
        # Mitwirkende nur ergaenzen, vorhandene Rollen bleiben unangetastet.
        existing = {(c.get("person", ""), c.get("role", "")) for c in md.credits}
        have_roles = {c.get("role", "") for c in md.credits}
        for credit in extra.credits:
            role, person = credit.get("role", ""), credit.get("person", "")
            if role in have_roles or (person, role) in existing:
                continue
            md.add_credit(person, role)
            filled = True
        if filled:
            used.append(provider.label)
    return used


def apply_candidate(path: Path, candidate: Candidate,
                    provider: MetadataProvider,
                    supplements: list[MetadataProvider] | None = None,
                    query: SearchQuery | None = None,
                    replace: bool = False) -> list[str]:
    """Kandidaten anreichern, ergaenzen und in die Datei schreiben.

    `replace` verwirft die vorhandenen Tags samt eigener freier Tags, statt
    die neuen darueberzulegen - gedacht fuer Dateien, deren Tags aus einer
    falschen Zuordnung stammen.
    """
    provider.enrich(candidate)
    used: list[str] = []
    if supplements and query is not None:
        used = apply_supplements(candidate.metadata, query, supplements)
    comic = archive.open_comic(path)
    try:
        if replace:
            merged = candidate.metadata
        else:
            merged = comic.read_metadata()
            merged.overlay(candidate.metadata)
        comic.write_metadata(merged)
    finally:
        comic.close()
    return used


# ---------------------------------------------------------------------------
class AutoTagWorker(QObject):
    """Laeuft in einem eigenen Thread und meldet pro Datei ein Ergebnis."""

    progress = Signal(int, int, str)   # erledigt, gesamt, Dateiname
    result = Signal(object)            # Result
    finished = Signal()

    def __init__(self, paths: list[Path], config: AutoTagConfig):
        super().__init__()
        self.paths = paths
        self.config = config
        self._stop = False

    def stop(self) -> None:
        self._stop = True

    @property
    def stopped(self) -> bool:
        return self._stop

    def run(self) -> None:
        by_name = {p.name: p for p in self.config.providers}
        for i, path in enumerate(self.paths, 1):
            if self._stop:
                break
            self.progress.emit(i, len(self.paths), path.name)
            self.result.emit(self._one(path, by_name))
        self.finished.emit()

    def _one(self, path: Path, by_name: dict[str, MetadataProvider]) -> Result:
        try:
            comic = archive.open_comic(path)
            writable = comic.writable
            had_tags = not comic.read_metadata().is_empty
            comic.close()
        except Exception as exc:  # noqa: BLE001
            return Result(path, "Fehler", detail=str(exc))

        if not writable:
            return Result(path, "Fehler",
                          detail=_("Format nicht beschreibbar - erst nach CBZ "
                                   "konvertieren."))
        if had_tags and not self.config.overwrite_existing:
            return Result(path, "uebersprungen", detail=_("Hat bereits Tags."))

        try:
            candidate, notes, query = identify(path, self.config,
                                               lambda: self._stop)
        except Exception as exc:  # noqa: BLE001
            return Result(path, "Fehler", detail=str(exc))

        if self._stop:
            return Result(path, "abgebrochen")
        if candidate is None:
            return Result(path, "kein Treffer", detail=notes)

        summary = (f"{candidate.series_name} #{candidate.issue_number}"
                   + (f" ({candidate.year})" if candidate.year else ""))
        if candidate.score < self.config.threshold:
            return Result(
                path, "unsicher", candidate.score, candidate.source, summary,
                _("unter Schwellwert {threshold}. {notes}").format(
                    threshold=self.config.threshold, notes=notes))
        try:
            used = apply_candidate(path, candidate, by_name[candidate.source],
                                   self.config.providers, query,
                                   replace=self.config.replace_existing)
        except Exception as exc:  # noqa: BLE001
            return Result(path, "Fehler", candidate.score, candidate.source,
                          summary, str(exc))
        reasons = list(candidate.reasons)
        if used:
            reasons.append(_("ergaenzt durch {sources}").format(
                sources=", ".join(used)))
        return Result(path, "getaggt", candidate.score, candidate.source,
                      summary, "; ".join(reasons))


def run_in_thread(paths: list[Path], config: AutoTagConfig):
    """Gibt (thread, worker) zurueck - der Aufrufer verbindet die Signale."""
    thread = QThread()
    worker = AutoTagWorker(paths, config)
    worker.moveToThread(thread)
    thread.started.connect(worker.run)
    worker.finished.connect(thread.quit)
    return thread, worker
