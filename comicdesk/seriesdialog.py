"""Reihen-Ansicht: was fehlt, und wie sicher das ist."""
from __future__ import annotations


from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QAbstractItemView, QCheckBox, QDialog, QHBoxLayout, QHeaderView, QLabel,
    QProgressBar, QPushButton, QSplitter, QTableWidget, QTableWidgetItem,
    QTextEdit, QVBoxLayout, QWidget,
)

from . import series as series_mod
from .config import TaggerSettings
from .i18n import _
from .index import CollectionIndex
from .seriescheck import SeriesChecker, summarize

PATH_ROLE = Qt.UserRole + 1


class SeriesDialog(QDialog):
    """Links die Reihen, rechts die Einzelheiten zur gewaehlten Reihe."""

    open_series = Signal(str)

    COLUMNS = ["Reihe", "Verlag", "Hefte", "Spanne", "Lücken", "Laut Quelle"]

    def __init__(self, index: CollectionIndex, settings, collection=None,
                 parent=None):
        super().__init__(parent)
        self.index = index
        self.settings = settings
        self.collection = collection
        self.entries: list[series_mod.Series] = []
        self.thread: QThread | None = None
        self.checker: SeriesChecker | None = None

        self.setWindowTitle(_("Reihen"))
        self.resize(1120, 700)
        root = QVBoxLayout(self)

        self.only_gaps = QCheckBox(_("Nur Reihen mit Lücken"))
        self.only_gaps.toggled.connect(self._fill_table)
        self.hide_single = QCheckBox(_("Reihen mit nur einem Heft ausblenden"))
        self.hide_single.setChecked(True)
        self.hide_single.toggled.connect(self._fill_table)
        top = QHBoxLayout()
        top.addWidget(self.only_gaps)
        top.addWidget(self.hide_single)
        top.addStretch(1)
        root.addLayout(top)

        split = QSplitter()
        self.table = QTableWidget(0, len(self.COLUMNS))
        self.table.setHorizontalHeaderLabels([_(c) for c in self.COLUMNS])
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.setSortingEnabled(True)
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.Stretch)
        self.table.itemSelectionChanged.connect(self._show_details)
        split.addWidget(self.table)

        right = QWidget()
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(8, 0, 0, 0)
        self.detail_title = QLabel()
        self.detail_title.setStyleSheet("font-weight:600;")
        self.detail_title.setWordWrap(True)
        right_layout.addWidget(self.detail_title)
        self.detail = QTextEdit()
        self.detail.setReadOnly(True)
        right_layout.addWidget(self.detail, 1)
        self.btn_check_one = QPushButton(_("Diese Reihe prüfen"))
        self.btn_check_one.clicked.connect(self._check_selected)
        right_layout.addWidget(self.btn_check_one)
        split.addWidget(right)
        split.setSizes([680, 420])
        root.addWidget(split, 1)

        self.status = QLabel()
        root.addWidget(self.status)
        self.bar = QProgressBar()
        self.bar.setVisible(False)
        root.addWidget(self.bar)

        buttons = QHBoxLayout()
        self.btn_check_all = QPushButton(_("Alle ungeprüften prüfen"))
        self.btn_check_all.clicked.connect(self._check_all)
        self.btn_stop = QPushButton(_("Abbrechen"))
        self.btn_stop.setEnabled(False)
        self.btn_stop.clicked.connect(self._stop)
        self.btn_close = QPushButton(_("Schliessen"))
        self.btn_close.clicked.connect(self.reject)
        buttons.addWidget(self.btn_check_all)
        buttons.addStretch(1)
        buttons.addWidget(self.btn_stop)
        buttons.addWidget(self.btn_close)
        root.addLayout(buttons)

        self.reload()

    # ------------------------------------------------------------------
    def reload(self) -> None:
        rows = self.index.series_rows(self.collection)
        self.entries = series_mod.build(rows)
        known = self.index.load_known()
        for entry in self.entries:
            saved = known.get(entry.key)
            if saved:
                entry.known_source, entry.known_numbers, name = saved
                entry.known_series_names = [name] if name else []
        self._fill_table()

    def _visible(self) -> list[series_mod.Series]:
        entries = self.entries
        if self.hide_single.isChecked():
            entries = [e for e in entries if e.count > 1]
        if self.only_gaps.isChecked():
            entries = [e for e in entries if e.gaps or e.missing_known]
        return entries

    def _fill_table(self) -> None:
        entries = self._visible()
        self.table.setSortingEnabled(False)
        self.table.setRowCount(0)
        for entry in entries:
            row = self.table.rowCount()
            self.table.insertRow(row)
            gaps = (_("uneinheitlich") if entry.scheme == series_mod.MIXED
                    else str(len(entry.gaps)) if entry.gaps else "–")
            values = [entry.name, entry.publisher or "–", str(entry.count),
                      entry.span, gaps, summarize(entry)]
            for column, value in enumerate(values):
                item = QTableWidgetItem(value)
                if column == 2:
                    item.setData(Qt.DisplayRole, entry.count)
                if column == 4 and entry.gaps:
                    item.setForeground(QColor(200, 120, 40))
                if column == 5 and entry.known_numbers is not None:
                    item.setForeground(QColor(70, 150, 95)
                                       if not entry.missing_known
                                       else QColor(200, 120, 40))
                self.table.setItem(row, column, item)
            self.table.item(row, 0).setData(PATH_ROLE, entry.key)
        self.table.setSortingEnabled(True)
        geprueft = sum(1 for e in self.entries if e.known_numbers is not None)
        self.status.setText(
            _("{shown} von {total} Reihen angezeigt · {checked} gegen eine "
              "Quelle geprüft").format(shown=len(entries),
                                       total=len(self.entries),
                                       checked=geprueft))

    def _selected(self) -> series_mod.Series | None:
        rows = self.table.selectionModel().selectedRows()
        if not rows:
            return None
        key = self.table.item(rows[0].row(), 0).data(PATH_ROLE)
        for entry in self.entries:
            if entry.key == tuple(key):
                return entry
        return None

    def _show_details(self) -> None:
        entry = self._selected()
        if entry is None:
            self.detail_title.clear()
            self.detail.clear()
            return
        self.detail_title.setText(
            f"{entry.name}" + (f" · {entry.publisher}" if entry.publisher else ""))
        parts = [_("{count} Hefte, {span}").format(count=entry.count,
                                                   span=entry.span), ""]
        if entry.scheme == series_mod.MIXED:
            parts += [_("Die Heftnummern dieser Reihe sind uneinheitlich "
                        "(etwa fortlaufend und nach Datum gemischt). Deshalb "
                        "wird hier keine Lücke behauptet."), ""]
        elif entry.gaps:
            parts += [_("Lücken im eigenen Bestand ({count}):").format(
                count=len(entry.gaps)), _wrap(entry.gaps), "",
                _("Das folgt allein aus den vorhandenen Heften und braucht "
                  "keine Quelle."), ""]
        else:
            parts += [_("Keine Lücken zwischen dem niedrigsten und dem "
                        "höchsten vorhandenen Heft."), ""]

        if not entry.samples:
            parts += [_("Keine Quell-Kennung in den Tags – diese Reihe lässt "
                        "sich nicht sicher zuordnen. Falls die Hefte getaggt "
                        "sind, hilft ein neuer Indexlauf.")]
        elif entry.known_numbers is None:
            parts += [_("Noch nicht gegen eine Quelle geprüft – ob die Reihe "
                        "über dein höchstes Heft hinaus weiterging, ist damit "
                        "offen.")]
        else:
            quelle = {"comicvine": "ComicVine",
                      "gcd": _("Grand Comics Database")}.get(
                entry.known_source or "", entry.known_source or "?")
            namen = " / ".join(entry.known_series_names)
            parts += [_("Laut {source}: {count} Hefte{names}").format(
                source=quelle, count=len(entry.known_numbers),
                names=f" ({namen})" if namen else "")]
            danach = entry.missing_after
            fehlend = entry.missing_known
            if fehlend:
                parts += ["", _("Dort verzeichnet, bei dir nicht vorhanden "
                                "({count}):").format(count=len(fehlend)),
                          _wrap(fehlend)]
                if danach:
                    parts += ["", _("Davon nach deinem höchsten Heft: "
                                    "{numbers}").format(numbers=_wrap(danach))]
            else:
                parts += ["", _("Deine Sammlung enthält alles, was die Quelle "
                                "kennt.")]
            parts += ["", _("Das ist eine Angabe der Quelle, keine "
                            "Gewissheit.")]
        self.detail.setPlainText("\n".join(parts))
        self.btn_check_one.setEnabled(bool(entry.samples))

    # --- Pruefen ------------------------------------------------------
    def _providers(self):
        return TaggerSettings.load(self.settings).build_providers()

    def _check_selected(self) -> None:
        entry = self._selected()
        if entry is not None:
            self._start([entry])

    def _check_all(self) -> None:
        offen = [e for e in self._visible()
                 if e.known_numbers is None and e.samples]
        if not offen:
            self.status.setText(_("Nichts zu prüfen – alles bereits geprüft "
                                  "oder ohne Quell-Kennung."))
            return
        self._start(offen)

    def _start(self, entries: list[series_mod.Series]) -> None:
        providers = self._providers()
        if not providers:
            self.status.setText(_("Keine Quelle konfiguriert."))
            return
        self.bar.setRange(0, len(entries))
        self.bar.setValue(0)
        self.bar.setVisible(True)
        self.btn_check_all.setEnabled(False)
        self.btn_check_one.setEnabled(False)
        self.btn_stop.setEnabled(True)
        self.btn_close.setVisible(False)

        self.thread = QThread()
        self.checker = SeriesChecker(entries, providers, self.index)
        self.checker.moveToThread(self.thread)
        self.thread.started.connect(self.checker.run)
        self.checker.progress.connect(self._on_progress)
        self.checker.finished.connect(self._on_finished)
        self.thread.start()

    def _on_progress(self, done: int, total: int, name: str) -> None:
        self.bar.setValue(done - 1)
        self.status.setText(
            _("[{done}/{total}] {name}").format(done=done, total=total, name=name))

    def _on_finished(self, done: int, empty: int, error: str) -> None:
        if self.thread:
            self.thread.quit()
            self.thread.wait(3000)
        self.thread = self.checker = None
        self.bar.setVisible(False)
        self.btn_check_all.setEnabled(True)
        self.btn_stop.setEnabled(False)
        self.btn_close.setVisible(True)
        self._fill_table()
        message = _("Fertig: {done} geprüft, {empty} ohne Ergebnis.").format(
            done=done, empty=empty)
        if error:
            message += "  " + error
        self.status.setText(message)

    def _stop(self) -> None:
        if self.checker:
            self.checker.stop()
            self.btn_stop.setEnabled(False)
            self.status.setText(_("Wird abgebrochen …"))

    # ------------------------------------------------------------------
    def _detach(self) -> None:
        if self.thread is None or not self.thread.isRunning():
            return
        if self.checker:
            self.checker.stop()
        thread, checker = self.thread, self.checker
        thread.quit()
        if not thread.wait(400):
            parent = self.parent()
            if parent is not None:
                pending = getattr(parent, "_pending_threads", None)
                if pending is None:
                    pending = parent._pending_threads = []
                pending.append((thread, checker))
        self.thread = self.checker = None

    def reject(self) -> None:
        self._detach()
        super().reject()

    def closeEvent(self, event):  # noqa: N802
        self._detach()
        super().closeEvent(event)


def _wrap(numbers: list[str], per_line: int = 12) -> str:
    lines = [", ".join(numbers[i:i + per_line])
             for i in range(0, len(numbers), per_line)]
    return "\n".join(lines)
