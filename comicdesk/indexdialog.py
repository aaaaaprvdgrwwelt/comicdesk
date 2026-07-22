"""Dialog zum Aufbauen und Pflegen des Sammlungs-Index."""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QThread
from PySide6.QtWidgets import (
    QCheckBox, QDialog, QFileDialog, QHBoxLayout, QLabel, QListWidget,
    QMessageBox, QProgressBar, QPushButton, QVBoxLayout,
)

from .i18n import _
from .index import CollectionIndex, IndexScanner


class IndexDialog(QDialog):
    """Ordner auswaehlen, durchsuchen lassen, Fortschritt sehen."""

    def __init__(self, index: CollectionIndex, suggested: Path | None = None,
                 parent=None):
        super().__init__(parent)
        self.index = index
        self.thread: QThread | None = None
        self.scanner: IndexScanner | None = None

        self.setWindowTitle(_("Sammlung indizieren"))
        self.resize(680, 440)
        root = QVBoxLayout(self)

        root.addWidget(QLabel(_(
            "Diese Ordner werden rekursiv nach Comics durchsucht und ihre "
            "Tags in den Suchindex geschrieben.")))

        self.list = QListWidget()
        for entry in index.roots():
            self.list.addItem(entry)
        if self.list.count() == 0 and suggested:
            self.list.addItem(str(suggested))
        root.addWidget(self.list, 1)

        row = QHBoxLayout()
        add = QPushButton(_("Ordner hinzufuegen …"))
        add.clicked.connect(self._add)
        remove = QPushButton(_("Entfernen"))
        remove.clicked.connect(self._remove)
        row.addWidget(add)
        row.addWidget(remove)
        row.addStretch(1)
        root.addLayout(row)

        self.force = QCheckBox(_(
            "Alles neu einlesen (sonst nur geaenderte Dateien)"))
        root.addWidget(self.force)

        self.status = QLabel(self._stats_text())
        root.addWidget(self.status)
        self.bar = QProgressBar()
        root.addWidget(self.bar)

        buttons = QHBoxLayout()
        self.btn_start = QPushButton(_("Indizieren"))
        self.btn_start.clicked.connect(self.start)
        self.btn_stop = QPushButton(_("Abbrechen"))
        self.btn_stop.setEnabled(False)
        self.btn_stop.clicked.connect(self.stop)
        self.btn_close = QPushButton(_("Schliessen"))
        self.btn_close.clicked.connect(self.reject)
        buttons.addStretch(1)
        for b in (self.btn_start, self.btn_stop, self.btn_close):
            buttons.addWidget(b)
        root.addLayout(buttons)

    # ------------------------------------------------------------------
    def _stats_text(self) -> str:
        return _("{count} Comics im Index.").format(count=self.index.count())

    def _add(self) -> None:
        path = QFileDialog.getExistingDirectory(
            self, _("Ordner waehlen"), str(Path.home()))
        if path and not self.list.findItems(path, 0):
            self.list.addItem(path)

    def _remove(self) -> None:
        for item in self.list.selectedItems():
            self.list.takeItem(self.list.row(item))

    def roots(self) -> list[Path]:
        return [Path(self.list.item(i).text()) for i in range(self.list.count())]

    # ------------------------------------------------------------------
    def start(self) -> None:
        roots = [r for r in self.roots() if r.is_dir()]
        if not roots:
            QMessageBox.information(
                self, _("Kein Ordner"),
                _("Bitte mindestens einen Ordner hinzufuegen."))
            return
        self.btn_start.setEnabled(False)
        self.btn_stop.setEnabled(True)
        self.status.setText(_("Suche Dateien …"))

        self.thread = QThread()
        self.scanner = IndexScanner(roots, self.index, self.force.isChecked())
        self.scanner.moveToThread(self.thread)
        self.thread.started.connect(self.scanner.run)
        self.scanner.progress.connect(self._on_progress)
        self.scanner.finished.connect(self._on_finished)
        self.scanner.finished.connect(self.thread.quit)
        self.thread.start()

    def stop(self) -> None:
        if self.scanner:
            self.scanner.stop()
            self.status.setText(_("Wird beendet …"))

    def _on_progress(self, done: int, total: int, name: str) -> None:
        if self.bar.maximum() != total:
            self.bar.setRange(0, total)
        self.bar.setValue(done)
        self.status.setText(
            _("[{done}/{total}] {name}").format(done=done, total=total, name=name))

    def _on_finished(self, updated: int, skipped: int, removed: int) -> None:
        self.btn_start.setEnabled(True)
        self.btn_stop.setEnabled(False)
        self.status.setText(
            _("Fertig: {updated} eingelesen, {skipped} unveraendert, "
              "{removed} verschwundene entfernt. {stats}").format(
                updated=updated, skipped=skipped, removed=removed,
                stats=self._stats_text()))

    def closeEvent(self, event):  # noqa: N802
        self.stop()
        if self.thread:
            self.thread.quit()
            self.thread.wait(5000)
        super().closeEvent(event)
