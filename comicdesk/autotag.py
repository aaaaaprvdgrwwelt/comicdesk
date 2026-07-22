"""Automatisches Taggen: Kandidaten bewerten und ab Schwellwert schreiben."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from comicapi.filenameparser import FileNameParser
from comicapi.genericmetadata import GenericMetadata
from PySide6.QtCore import QObject, QThread, Signal

from . import archive
from .i18n import _
from .providers.base import (
    Candidate, MetadataProvider, SearchQuery, normalize_issue, series_similarity,
)

DEFAULT_THRESHOLD = 80

# Gewichte der Einzelsignale. Nicht verfuegbare Signale fallen samt Gewicht
# raus, damit ein Treffer ohne Cover nicht automatisch schlechter dasteht.
W_SERIES = 45
W_ISSUE = 20
W_YEAR = 25
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
    providers: list[MetadataProvider] = field(default_factory=list)


# ---------------------------------------------------------------------------
def build_query(path: Path, md: GenericMetadata, cover: bytes | None) -> SearchQuery:
    """Was wir ueber das Heft wissen - Tags schlagen Dateinamen."""
    parser = FileNameParser()
    parser.parse_filename(path.name)
    return SearchQuery(
        series=(md.series or parser.series or "").strip(),
        issue=(md.issue or parser.issue or "").strip() or None,
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
    if query.publisher and candidate.publisher:
        parts.append((W_PUBLISHER,
                      series_similarity(query.publisher, candidate.publisher)))
    if cover_sim is not None:
        parts.append((W_COVER, cover_sim))

    total_weight = sum(w for w, _ in parts)
    if not total_weight:
        return 0
    return round(100 * sum(w * v for w, v in parts) / total_weight)


def identify(path: Path, config: AutoTagConfig) -> tuple[Candidate | None, str]:
    """Besten Kandidaten fuer eine Datei suchen. Gibt (Kandidat, Hinweis)."""
    comic = archive.open_comic(path)
    try:
        existing = comic.read_metadata()
        cover = comic.page_bytes(0) if comic.page_count else None
    finally:
        comic.close()

    query = build_query(path, existing, cover)
    if not query.series:
        return None, _("Serienname weder in Tags noch im Dateinamen erkennbar.")

    best: Candidate | None = None
    notes: list[str] = []
    for provider in config.providers:
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
            sim = None
            if config.use_cover_match and provider.has_covers and cover:
                sim = cover_similarity(cover, provider.fetch_cover(candidate))
            candidate.score = score_candidate(query, candidate, sim)
            if sim is not None:
                candidate.reasons.append(
                    _("Cover-Aehnlichkeit {value}").format(value=f"{sim:.0%}"))
            if best is None or candidate.score > best.score:
                best = candidate
    return best, "; ".join(notes)


def apply_candidate(path: Path, candidate: Candidate,
                    provider: MetadataProvider) -> None:
    """Kandidaten anreichern und in die Datei schreiben."""
    provider.enrich(candidate)
    comic = archive.open_comic(path)
    try:
        merged = comic.read_metadata()
        merged.overlay(candidate.metadata)
        comic.write_metadata(merged)
    finally:
        comic.close()


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
            candidate, notes = identify(path, self.config)
        except Exception as exc:  # noqa: BLE001
            return Result(path, "Fehler", detail=str(exc))

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
            apply_candidate(path, candidate, by_name[candidate.source])
        except Exception as exc:  # noqa: BLE001
            return Result(path, "Fehler", candidate.score, candidate.source,
                          summary, str(exc))
        return Result(path, "getaggt", candidate.score, candidate.source,
                      summary, "; ".join(candidate.reasons))


def run_in_thread(paths: list[Path], config: AutoTagConfig):
    """Gibt (thread, worker) zurueck - der Aufrufer verbindet die Signale."""
    thread = QThread()
    worker = AutoTagWorker(paths, config)
    worker.moveToThread(thread)
    thread.started.connect(worker.run)
    worker.finished.connect(thread.quit)
    return thread, worker
