"""Sammlungen anlegen, ihnen Ordner zuweisen und sie indizieren."""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, QThread
from PySide6.QtWidgets import (
    QAbstractItemView, QCheckBox, QDialog, QFileDialog, QHBoxLayout, QLabel,
    QListWidget, QMessageBox, QProgressBar, QPushButton, QSplitter,
    QVBoxLayout, QWidget,
)

from .background import stop_and_detach
from .i18n import _
from .index import Collection, CollectionIndex, IndexScanner


class CollectionsDialog(QDialog):
    """Links die Sammlungen, rechts die Ordner der gewaehlten Sammlung."""

    def __init__(self, index: CollectionIndex, suggested: Path | None = None,
                 parent=None):
        super().__init__(parent)
        self.index = index
        self.suggested = suggested
        self.thread: QThread | None = None
        self.scanner: IndexScanner | None = None
        self._queue: list[Collection] = []

        self.setWindowTitle(_("Sammlungen"))
        self.resize(860, 560)
        root = QVBoxLayout(self)
        root.addWidget(QLabel(_(
            "Jede Sammlung hat eigene Ordner. Beim Indizieren werden sie "
            "rekursiv nach Comics durchsucht.")))

        split = QSplitter()
        root.addWidget(split, 1)

        # --- links: Sammlungen ---------------------------------------
        left = QWidget()
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(0, 0, 6, 0)
        left_layout.addWidget(QLabel(_("Sammlungen")))
        self.collection_list = QListWidget()
        self.collection_list.currentRowChanged.connect(self._on_collection_changed)
        left_layout.addWidget(self.collection_list, 1)
        row = QHBoxLayout()
        for label, slot in ((_("Neu …"), self.new_collection),
                            (_("Umbenennen …"), self.rename_collection),
                            (_("Loeschen"), self.delete_collection)):
            button = QPushButton(label)
            button.clicked.connect(slot)
            row.addWidget(button)
        left_layout.addLayout(row)
        split.addWidget(left)

        # --- rechts: Ordner ------------------------------------------
        right = QWidget()
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(6, 0, 0, 0)
        self.folder_label = QLabel(_("Ordner der Sammlung"))
        right_layout.addWidget(self.folder_label)
        self.folder_list = QListWidget()
        self.folder_list.setSelectionMode(QAbstractItemView.ExtendedSelection)
        right_layout.addWidget(self.folder_list, 1)
        row = QHBoxLayout()
        self.btn_add_folder = QPushButton(_("Ordner hinzufuegen …"))
        self.btn_add_folder.clicked.connect(self.add_folder)
        self.btn_remove_folder = QPushButton(_("Entfernen"))
        self.btn_remove_folder.clicked.connect(self.remove_folder)
        row.addWidget(self.btn_add_folder)
        row.addWidget(self.btn_remove_folder)
        row.addStretch(1)
        right_layout.addLayout(row)
        split.addWidget(right)
        split.setSizes([300, 560])

        self.force = QCheckBox(_("Alles neu einlesen (sonst nur geaenderte Dateien)"))
        root.addWidget(self.force)
        self.status = QLabel()
        root.addWidget(self.status)
        self.bar = QProgressBar()
        root.addWidget(self.bar)

        buttons = QHBoxLayout()
        self.btn_index = QPushButton(_("Diese Sammlung indizieren"))
        self.btn_index.clicked.connect(self.index_current)
        self.btn_index_all = QPushButton(_("Alle indizieren"))
        self.btn_index_all.clicked.connect(self.index_all)
        self.btn_stop = QPushButton(_("Abbrechen"))
        self.btn_stop.setEnabled(False)
        self.btn_stop.clicked.connect(self.stop)
        self.btn_close = QPushButton(_("Schliessen"))
        self.btn_close.clicked.connect(self.reject)
        buttons.addWidget(self.btn_index)
        buttons.addWidget(self.btn_index_all)
        buttons.addStretch(1)
        buttons.addWidget(self.btn_stop)
        buttons.addWidget(self.btn_close)
        root.addLayout(buttons)

        self._reload()

    # ------------------------------------------------------------------
    def _reload(self, select: str | None = None) -> None:
        current = select or self.current_name()
        self.collection_list.blockSignals(True)
        self.collection_list.clear()
        for entry in self.index.collections():
            self.collection_list.addItem(entry.name)
        self.collection_list.blockSignals(False)
        if self.collection_list.count():
            items = self.collection_list.findItems(current or "", Qt.MatchExactly)
            self.collection_list.setCurrentRow(
                self.collection_list.row(items[0]) if items else 0)
        else:
            self._on_collection_changed(-1)

    def current_name(self) -> str | None:
        item = self.collection_list.currentItem()
        return item.text() if item else None

    def _on_collection_changed(self, _row: int) -> None:
        name = self.current_name()
        self.folder_list.clear()
        entry = self.index.collection(name) if name else None
        if entry:
            for folder in entry.roots:
                self.folder_list.addItem(folder)
        has = entry is not None
        for widget in (self.folder_list, self.btn_add_folder,
                       self.btn_remove_folder, self.btn_index):
            widget.setEnabled(has)
        self.folder_label.setText(
            _("Ordner in „{name}“").format(name=name) if has
            else _("Ordner der Sammlung"))
        self._show_counts()

    def _show_counts(self) -> None:
        name = self.current_name()
        total = self.index.count()
        if name:
            self.status.setText(_("„{name}“: {count} Comics · insgesamt {total}")
                                .format(name=name, count=self.index.count(name),
                                        total=total))
        else:
            self.status.setText(_("Noch keine Sammlung angelegt."))

    # --- Sammlungen ---------------------------------------------------
    def _ask_name(self, title: str, preset: str = "") -> str | None:
        from PySide6.QtWidgets import QInputDialog, QLineEdit

        name, ok = QInputDialog.getText(self, title, _("Name der Sammlung:"),
                                        QLineEdit.Normal, preset)
        name = name.strip()
        if not ok or not name:
            return None
        return name

    def new_collection(self) -> None:
        name = self._ask_name(_("Neue Sammlung"))
        if name is None:
            return
        roots = [str(self.suggested)] if self.suggested and not \
            self.index.collections() else []
        if not self.index.add_collection(name, roots):
            QMessageBox.warning(self, _("Neue Sammlung"),
                                _("„{name}“ gibt es schon.").format(name=name))
            return
        self._reload(name)

    def rename_collection(self) -> None:
        old = self.current_name()
        if not old:
            return
        new = self._ask_name(_("Sammlung umbenennen"), old)
        if new is None or new == old:
            return
        self.index.rename_collection(old, new)
        self._reload(new)

    def delete_collection(self) -> None:
        name = self.current_name()
        if not name:
            return
        if QMessageBox.question(
            self, _("Sammlung loeschen"),
            _("Sammlung „{name}“ mit {count} indizierten Comics loeschen?\n\n"
              "Die Comic-Dateien selbst bleiben unangetastet.").format(
                name=name, count=self.index.count(name)),
        ) != QMessageBox.Yes:
            return
        self.index.delete_collection(name)
        self._reload()

    # --- Ordner -------------------------------------------------------
    def _save_folders(self) -> None:
        name = self.current_name()
        if not name:
            return
        roots = [self.folder_list.item(i).text()
                 for i in range(self.folder_list.count())]
        collections = self.index.collections()
        for entry in collections:
            if entry.name == name:
                entry.roots = roots
        self.index.set_collections(collections)

    def add_folder(self) -> None:
        start = str(self.suggested or Path.home())
        path = QFileDialog.getExistingDirectory(self, _("Ordner waehlen"), start)
        if path and not self.folder_list.findItems(path, Qt.MatchExactly):
            self.folder_list.addItem(path)
            self._save_folders()

    def remove_folder(self) -> None:
        for item in self.folder_list.selectedItems():
            self.folder_list.takeItem(self.folder_list.row(item))
        self._save_folders()

    # --- Indizieren ---------------------------------------------------
    def index_current(self) -> None:
        entry = self.index.collection(self.current_name() or "")
        if entry is None:
            return
        self._start([entry])

    def index_all(self) -> None:
        collections = self.index.collections()
        if not collections:
            QMessageBox.information(self, _("Sammlungen"),
                                    _("Noch keine Sammlung angelegt."))
            return
        self._start(collections)

    def _start(self, collections: list[Collection]) -> None:
        usable = [c for c in collections if any(Path(r).is_dir() for r in c.roots)]
        if not usable:
            QMessageBox.information(
                self, _("Kein Ordner"),
                _("Bitte mindestens einen Ordner hinzufuegen."))
            return
        self._queue = usable
        self._set_running(True)
        self._next_in_queue()

    def _next_in_queue(self) -> None:
        if not self._queue:
            self._set_running(False)
            self._reload()
            return
        entry = self._queue.pop(0)
        roots = [Path(r) for r in entry.roots if Path(r).is_dir()]
        self.status.setText(_("„{name}“ wird durchsucht …").format(name=entry.name))
        self.thread = QThread()
        self.scanner = IndexScanner(roots, self.index, self.force.isChecked(),
                                    entry.name)
        self.scanner.moveToThread(self.thread)
        self.thread.started.connect(self.scanner.run)
        self.scanner.progress.connect(self._on_progress)
        self.scanner.finished.connect(self._on_finished)
        self.scanner.finished.connect(self.thread.quit)
        self.thread.start()

    def _set_running(self, running: bool) -> None:
        # Schliessen bleibt bewusst bedienbar - es bricht den Lauf ab.
        for widget in (self.btn_index, self.btn_index_all, self.collection_list):
            widget.setEnabled(not running)
        self.btn_stop.setEnabled(running)
        if not running:
            self._on_collection_changed(-1)

    def stop(self) -> None:
        self._queue.clear()
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
        self.status.setText(
            _("Fertig: {updated} eingelesen, {skipped} unveraendert, "
              "{removed} verschwundene entfernt. {stats}").format(
                updated=updated, skipped=skipped, removed=removed, stats=""))
        if self.thread:
            self.thread.quit()
            self.thread.wait(3000)
            self.thread = None
        self._next_in_queue()

    def reject(self) -> None:
        self._detach()
        super().reject()

    def closeEvent(self, event):  # noqa: N802
        self._detach()
        super().closeEvent(event)

    def _detach(self) -> None:
        self._queue.clear()
        stop_and_detach(self, self.thread, self.scanner)
        self.thread = self.scanner = None


#: Frueherer Name.
IndexDialog = CollectionsDialog
