"""Treffer von Hand auswaehlen, wenn die Automatik unsicher ist.

Zeigt alle Kandidaten samt Bewertung und Cover neben dem eigenen Heft. Die
Suchbegriffe sind aenderbar: bei einem unsicheren Treffer liegt es meist am
Dateinamen, aus dem sie stammen.
"""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QObject, QSize, Qt, QThread, Signal
from PySide6.QtGui import QColor, QPixmap
from PySide6.QtWidgets import (
    QAbstractItemView, QDialog, QFormLayout, QHBoxLayout, QHeaderView, QLabel,
    QLineEdit, QMessageBox, QPushButton, QTableWidget, QTableWidgetItem,
    QTextEdit, QVBoxLayout, QWidget,
)

from . import archive
from .autotag import apply_candidate, collect_candidates, read_query
from .background import stop_and_detach
from .config import TaggerSettings
from .i18n import _
from .providers.base import SearchQuery

COVER = 130
#: Zeilenhoehe - hoch genug fuers Cover, niedrig genug fuer mehrere Zeilen.
ROW = 74


class _SearchWorker(QObject):
    """Sucht im Hintergrund - ComicVine drosselt, das dauert."""

    done = Signal(object, str, str)   # Kandidaten, Hinweise, Fehler

    def __init__(self, query: SearchQuery, config, cover: bytes | None):
        super().__init__()
        self.query, self.config, self.cover = query, config, cover
        self._stop = False

    def stop(self) -> None:
        self._stop = True

    def run(self) -> None:
        try:
            gefunden, notes = collect_candidates(
                self.query, self.config, self.cover, lambda: self._stop)
        except Exception as exc:  # noqa: BLE001
            self.done.emit([], "", str(exc))
            return
        if not self._stop:
            self.done.emit(gefunden, notes, "")


class _CoverWorker(QObject):
    """Laedt die Cover der Kandidaten nach."""

    loaded = Signal(int, bytes)
    finished = Signal()

    def __init__(self, jobs: list[tuple[int, object, object]]):
        super().__init__()
        self.jobs = jobs
        self._stop = False

    def stop(self) -> None:
        self._stop = True

    def run(self) -> None:
        for row, provider, candidate in self.jobs:
            if self._stop:
                break
            try:
                data = provider.fetch_cover(candidate)
            except Exception:  # noqa: BLE001
                data = None
            if data and not self._stop:
                self.loaded.emit(row, data)
        self.finished.emit()


class MatchDialog(QDialog):
    """Kandidaten ansehen, Suche nachschaerfen, einen uebernehmen."""

    applied = Signal(str)

    COLUMNS = ["", "Score", "Quelle", "Reihe", "Nr.", "Jahr", "Verlag"]

    def __init__(self, path: Path, settings, parent=None):
        super().__init__(parent)
        self.path = Path(path)
        self.settings = settings
        self.candidates: list = []
        self.thread: QThread | None = None
        self.worker = None
        self.cover_thread: QThread | None = None
        self.cover_worker: _CoverWorker | None = None

        self.setWindowTitle(_("Treffer wählen – {name}").format(name=self.path.name))
        self.resize(1000, 700)
        root = QVBoxLayout(self)

        kopf = QHBoxLayout()
        self.cover_label = QLabel()
        self.cover_label.setFixedSize(COVER, COVER + 30)
        self.cover_label.setAlignment(Qt.AlignCenter)
        kopf.addWidget(self.cover_label)

        form_box = QWidget()
        form = QFormLayout(form_box)
        form.setContentsMargins(12, 0, 0, 0)
        self.series = QLineEdit()
        self.issue = QLineEdit()
        self.year = QLineEdit()
        for label, widget in ((_("Serie"), self.series), (_("Nummer"), self.issue),
                              (_("Jahr"), self.year)):
            widget.returnPressed.connect(self.search)
            form.addRow(label, widget)
        hinweis = QLabel(_(
            "Die Begriffe stammen aus den Tags oder dem Dateinamen. Passt der "
            "Treffer nicht, liegt es meist daran – korrigieren und erneut "
            "suchen."))
        hinweis.setWordWrap(True)
        hinweis.setStyleSheet("color:gray;")
        form.addRow(hinweis)
        kopf.addWidget(form_box, 1)
        root.addLayout(kopf)

        self.table = QTableWidget(0, len(self.COLUMNS))
        self.table.setHorizontalHeaderLabels([_(c) for c in self.COLUMNS])
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.setIconSize(QSize(46, ROW - 8))
        self.table.verticalHeader().setDefaultSectionSize(ROW)
        self.table.verticalHeader().setVisible(False)
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(3, QHeaderView.Stretch)
        self.table.itemSelectionChanged.connect(self._show_details)
        self.table.doubleClicked.connect(lambda _i: self.apply())
        root.addWidget(self.table, 1)

        self.details = QTextEdit()
        self.details.setReadOnly(True)
        self.details.setMaximumHeight(64)
        root.addWidget(self.details)

        self.status = QLabel()
        root.addWidget(self.status)

        knoepfe = QHBoxLayout()
        self.btn_search = QPushButton(_("Erneut suchen"))
        self.btn_search.clicked.connect(self.search)
        self.btn_apply = QPushButton(_("Übernehmen"))
        self.btn_apply.setDefault(True)
        self.btn_apply.setEnabled(False)
        self.btn_apply.clicked.connect(self.apply)
        self.btn_close = QPushButton(_("Schliessen"))
        self.btn_close.clicked.connect(self.reject)
        knoepfe.addWidget(self.btn_search)
        knoepfe.addStretch(1)
        knoepfe.addWidget(self.btn_apply)
        knoepfe.addWidget(self.btn_close)
        root.addLayout(knoepfe)

        self._load_file()
        self.search()

    # ------------------------------------------------------------------
    def _load_file(self) -> None:
        self.cover_data = None
        query, cover = None, None
        try:
            query, cover = read_query(self.path)
        except Exception as exc:  # noqa: BLE001
            self.status.setText(str(exc))
        self.cover_data = cover
        if cover:
            pixmap = QPixmap()
            if pixmap.loadFromData(cover):
                self.cover_label.setPixmap(pixmap.scaled(
                    COVER, COVER + 30, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        if query:
            self.series.setText(query.series or "")
            self.issue.setText(query.issue or "")
            self.year.setText(str(query.year) if query.year else "")

    def _query(self) -> SearchQuery:
        jahr = self.year.text().strip()
        return SearchQuery(
            series=self.series.text().strip(),
            issue=self.issue.text().strip() or None,
            year=int(jahr) if jahr.isdigit() else None,
            publisher=None,
            cover=self.cover_data,
        )

    # --- Suche --------------------------------------------------------
    def search(self) -> None:
        query = self._query()
        if not query.series:
            self.status.setText(_("Bitte einen Seriennamen eingeben."))
            return
        config = TaggerSettings.load(self.settings).build_config()
        if not config.providers:
            self.status.setText(_("Keine Quelle konfiguriert."))
            return
        self._stop_all()
        self.table.setRowCount(0)
        self.btn_search.setEnabled(False)
        self.status.setText(_("Wird gesucht …"))

        self.thread = QThread()
        self.worker = _SearchWorker(query, config, self.cover_data)
        self._providers = {p.name: p for p in config.providers}
        self.worker.moveToThread(self.thread)
        self.thread.started.connect(self.worker.run)
        self.worker.done.connect(self._on_results)
        self.thread.start()

    def _on_results(self, candidates, notes: str, error: str) -> None:
        if self.thread:
            self.thread.quit()
            self.thread.wait(2000)
        self.thread = self.worker = None
        self.btn_search.setEnabled(True)
        if error:
            self.status.setText(error)
            return
        self.candidates = candidates
        self._fill(candidates)
        teile = [_("{count} Vorschläge").format(count=len(candidates))]
        if notes:
            teile.append(notes)
        self.status.setText(" · ".join(teile))
        self._load_covers()

    def _fill(self, candidates) -> None:
        self.table.setRowCount(0)
        for candidate in candidates:
            row = self.table.rowCount()
            self.table.insertRow(row)
            werte = ["", str(candidate.score),
                     _(self._providers[candidate.source].label)
                     if candidate.source in self._providers else candidate.source,
                     candidate.series_name, candidate.issue_number,
                     str(candidate.year or "–"), candidate.publisher or "–"]
            for spalte, wert in enumerate(werte):
                item = QTableWidgetItem(wert)
                if spalte == 1:
                    item.setData(Qt.DisplayRole, candidate.score)
                    item.setForeground(QColor(70, 150, 95) if candidate.score >= 90
                                       else QColor(200, 120, 40)
                                       if candidate.score >= 70
                                       else QColor(150, 150, 150))
                self.table.setItem(row, spalte, item)
        if candidates:
            self.table.selectRow(0)

    def _load_covers(self) -> None:
        jobs = [(row, self._providers.get(c.source), c)
                for row, c in enumerate(self.candidates[:25])
                if c.cover_url and self._providers.get(c.source)]
        if not jobs:
            return
        self.cover_thread = QThread()
        self.cover_worker = _CoverWorker(jobs)
        self.cover_worker.moveToThread(self.cover_thread)
        self.cover_thread.started.connect(self.cover_worker.run)
        self.cover_worker.loaded.connect(self._on_cover)
        self.cover_worker.finished.connect(self.cover_thread.quit)
        self.cover_thread.start()

    def _on_cover(self, row: int, data: bytes) -> None:
        if row >= self.table.rowCount():
            return
        pixmap = QPixmap()
        if not pixmap.loadFromData(data):
            return
        item = self.table.item(row, 0)
        if item is not None:
            item.setData(Qt.DecorationRole,
                         pixmap.scaled(46, ROW - 8, Qt.KeepAspectRatio,
                                       Qt.SmoothTransformation))

    # --- Auswahl ------------------------------------------------------
    def _selected(self):
        rows = self.table.selectionModel().selectedRows()
        if not rows:
            return None
        index = rows[0].row()
        return self.candidates[index] if index < len(self.candidates) else None

    def _show_details(self) -> None:
        candidate = self._selected()
        self.btn_apply.setEnabled(candidate is not None)
        if candidate is None:
            self.details.clear()
            return
        md = candidate.metadata
        zeilen = [f"{candidate.series_name} #{candidate.issue_number}"
                  + (f" ({candidate.year})" if candidate.year else "")]
        if md.title:
            zeilen.append(md.title)
        if candidate.reasons:
            zeilen.append(" · ".join(candidate.reasons))
        if md.web_link:
            zeilen.append(md.web_link)
        self.details.setPlainText("\n".join(zeilen))

    def apply(self) -> None:
        candidate = self._selected()
        if candidate is None:
            return
        provider = self._providers.get(candidate.source)
        if provider is None:
            return
        self.status.setText(_("Wird übernommen …"))
        try:
            comic = archive.open_comic(self.path)
            writable = comic.writable
            comic.close()
            if not writable:
                raise archive.ComicError(
                    _("Format nicht beschreibbar - erst nach CBZ konvertieren."))
            config = TaggerSettings.load(self.settings).build_config()
            apply_candidate(self.path, candidate, provider,
                            config.providers, self._query())
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(self, _("Tags speichern"),
                                 _("Fehlgeschlagen:\n{error}").format(error=exc))
            self.status.setText("")
            return
        self.applied.emit(str(self.path))
        self.accept()

    # ------------------------------------------------------------------
    def _stop_all(self) -> None:
        stop_and_detach(self, self.thread, self.worker)
        stop_and_detach(self, self.cover_thread, self.cover_worker)
        self.thread = self.worker = None
        self.cover_thread = self.cover_worker = None

    def reject(self) -> None:
        self._stop_all()
        super().reject()

    def closeEvent(self, event):  # noqa: N802
        self._stop_all()
        super().closeEvent(event)
