"""Vollstaendigkeit von Reihen gegen die Quellen pruefen.

Die Zuordnung laeuft ueber die in den Tags gespeicherte Heft-ID, nicht ueber
den Serientitel - Namenssuche greift bei Reihen wie "Die Raecher" regelmaessig
die falsche Auflage.
"""
from __future__ import annotations

from PySide6.QtCore import QObject, Signal

from .i18n import _
from .index import CollectionIndex
from .providers.base import MetadataProvider
from .series import Series

#: Erst Anfang und Ende fragen. Nur wenn die auf verschiedene Reihen der
#: Quelle zeigen, lohnen weitere Proben - jede kostet Kontingent.
FIRST_PROBES = 2
EXTRA_PROBES = 4


def check_series(entry: Series, providers: dict[str, MetadataProvider]
                 ) -> tuple[list[str], list[str]] | None:
    """(Nummern, Namen der Quell-Reihen) oder None, wenn nichts ermittelbar."""
    provider = providers.get(entry.source or "")
    if provider is None or not provider.available()[0]:
        return None

    numbers: set[str] = set()
    names: list[str] = []
    probes = entry.probe_ids(FIRST_PROBES)
    seen_ids: set[str] = set()

    def run(ids: list[str]) -> None:
        for ident in ids:
            if ident in seen_ids:
                continue
            seen_ids.add(ident)
            result = provider.series_issues(ident)
            if not result:
                continue
            name, found = result
            if name and name not in names:
                names.append(name)
            numbers.update(found)

    run(probes)
    if len(names) > 1:
        # Die lokale Reihe deckt mehrere Reihen der Quelle ab - genauer
        # hinsehen, sonst fehlt ein ganzer Abschnitt.
        run(entry.probe_ids(EXTRA_PROBES))
    if not numbers:
        return None
    return sorted(numbers, key=_sort_key), names


def _sort_key(text: str):
    try:
        return (0, float(text))
    except ValueError:
        return (1, text)


class SeriesChecker(QObject):
    """Prueft Reihen der Reihe nach und schreibt die Ergebnisse in den Index."""

    progress = Signal(int, int, str)
    checked = Signal(object)          # Series
    finished = Signal(int, int, str)  # geprueft, ohne Ergebnis, Fehlermeldung

    def __init__(self, entries: list[Series], providers: list[MetadataProvider],
                 index: CollectionIndex):
        super().__init__()
        self.entries = entries
        self.providers = {p.name: p for p in providers}
        self.index = index
        self._stop = False

    def stop(self) -> None:
        self._stop = True

    def run(self) -> None:
        done = empty = 0
        error = ""
        for i, entry in enumerate(self.entries, 1):
            if self._stop:
                break
            self.progress.emit(i, len(self.entries), entry.name)
            try:
                result = check_series(entry, self.providers)
            except Exception as exc:  # noqa: BLE001
                error = str(exc)
                break
            if result is None:
                empty += 1
                continue
            numbers, names = result
            entry.known_numbers = numbers
            entry.known_source = entry.source
            entry.known_series_names = names
            self.index.save_known(entry.name, entry.publisher or "",
                                  entry.source or "", numbers, " / ".join(names))
            done += 1
            self.checked.emit(entry)
        self.finished.emit(done, empty, error)


def summarize(entry: Series) -> str:
    """Kurzfassung fuer die Tabelle."""
    if entry.reference is None:
        return ""
    missing = entry.missing_known
    prefix = _("von Hand") + " · " if entry.is_manual else ""
    if not missing:
        return prefix + _("vollständig")
    return prefix + _("{count} fehlen").format(count=len(missing))
