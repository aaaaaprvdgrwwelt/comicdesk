"""Reihen-Ansicht: was fehlt, und wie sicher das ist."""
from __future__ import annotations


from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QAbstractItemView, QCheckBox, QDialog, QHBoxLayout, QHeaderView, QLabel,
    QLineEdit, QProgressBar, QPushButton, QSplitter, QTableWidget,
    QTableWidgetItem, QTextEdit, QVBoxLayout, QWidget,
)

from . import series as series_mod
from .background import stop_and_detach
from .config import TaggerSettings
from .i18n import _
from .index import CollectionIndex
from .seriescheck import SeriesChecker, summarize

PATH_ROLE = Qt.UserRole + 1


class ManualSeriesDialog(QDialog):
    """Bestand einer Reihe von Hand festlegen."""

    def __init__(self, entry, parent=None):
        super().__init__(parent)
        self.entry = entry
        self.result_numbers: list[str] | None = None
        self.cleared = False

        self.setWindowTitle(_("Reihe von Hand festlegen"))
        self.setMinimumWidth(520)
        root = QVBoxLayout(self)
        root.addWidget(QLabel(
            f"<b>{entry.name}</b>" + (f" · {entry.publisher}" if entry.publisher else "")))
        hint = QLabel(_(
            "Welche Nummern gibt es in dieser Reihe wirklich? Bereiche mit "
            "Bindestrich, mehrere durch Komma getrennt – etwa "
            "„1-3, 12-20“. Diese Angabe schlägt jede Quelle: Nummern, die hier "
            "nicht stehen, gelten nicht mehr als Lücke."))
        hint.setWordWrap(True)
        hint.setStyleSheet("color:gray;")
        root.addWidget(hint)

        self.edit = QLineEdit()
        vorhanden = series_mod.format_ranges(
            [series_mod._fmt(n) for n in sorted(entry.numbers)])
        if entry.manual_numbers is not None:
            self.edit.setText(series_mod.format_ranges(entry.manual_numbers))
        elif entry.known_numbers:
            self.edit.setText(series_mod.format_ranges(entry.known_numbers))
        else:
            self.edit.setText(vorhanden)
        self.edit.textChanged.connect(self._preview)
        root.addWidget(self.edit)

        self.preview = QLabel()
        self.preview.setWordWrap(True)
        root.addWidget(self.preview)

        buttons = QHBoxLayout()
        self.btn_owned = QPushButton(_("Auf vorhandene Hefte setzen"))
        self.btn_owned.clicked.connect(lambda: self.edit.setText(vorhanden))
        self.btn_clear = QPushButton(_("Festlegung aufheben"))
        self.btn_clear.clicked.connect(self._clear)
        self.btn_clear.setEnabled(entry.manual_numbers is not None)
        ok = QPushButton(_("Übernehmen"))
        ok.setDefault(True)
        ok.clicked.connect(self._accept)
        cancel = QPushButton(_("Abbrechen"))
        cancel.clicked.connect(self.reject)
        buttons.addWidget(self.btn_owned)
        buttons.addWidget(self.btn_clear)
        buttons.addStretch(1)
        buttons.addWidget(ok)
        buttons.addWidget(cancel)
        root.addLayout(buttons)
        self._preview()

    def _preview(self) -> None:
        numbers = series_mod.parse_ranges(self.edit.text())
        have = {series_mod._fmt(n) for n in self.entry.numbers}
        missing = [n for n in numbers if n not in have]
        self.preview.setText(_(
            "{total} Hefte in der Reihe · {owned} davon vorhanden · "
            "{missing} fehlen").format(
                total=len(numbers), owned=len(numbers) - len(missing),
                missing=len(missing)))

    def _clear(self) -> None:
        self.cleared = True
        self.accept()

    def _accept(self) -> None:
        self.result_numbers = series_mod.parse_ranges(self.edit.text())
        self.accept()



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
        self.btn_manual = QPushButton(_("Reihe von Hand festlegen …"))
        self.btn_manual.clicked.connect(self._edit_manual)
        right_layout.addWidget(self.btn_manual)
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
        manual = self.index.load_manual()
        for entry in self.entries:
            saved = known.get(entry.key)
            if saved:
                entry.known_source, entry.known_numbers, name = saved
                entry.known_series_names = [name] if name else []
            eigen = manual.get(entry.key)
            if eigen:
                entry.manual_numbers, entry.manual_note = eigen
        self._fill_table()

    def _visible(self) -> list[series_mod.Series]:
        entries = self.entries
        if self.hide_single.isChecked():
            entries = [e for e in entries if e.count > 1]
        if self.only_gaps.isChecked():
            entries = [e for e in entries if e.effective_gaps]
        return entries

    def _fill_table(self) -> None:
        entries = self._visible()
        self.table.setSortingEnabled(False)
        self.table.setRowCount(0)
        for entry in entries:
            row = self.table.rowCount()
            self.table.insertRow(row)
            fehlend = entry.effective_gaps
            gaps = (_("uneinheitlich")
                    if entry.scheme == series_mod.MIXED and not entry.is_manual
                    else str(len(fehlend)) if fehlend else "–")
            values = [entry.name, entry.publisher or "–", str(entry.count),
                      entry.span, gaps, summarize(entry)]
            for column, value in enumerate(values):
                item = QTableWidgetItem(value)
                if column == 2:
                    item.setData(Qt.DisplayRole, entry.count)
                if column == 4 and fehlend:
                    item.setForeground(QColor(200, 120, 40))
                if column == 5 and entry.reference is not None:
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
        if entry.is_manual:
            parts += [_("Von Hand festgelegt: {ranges}").format(
                ranges=series_mod.format_ranges(entry.manual_numbers)), ""]
            fehlend = entry.effective_gaps
            if fehlend:
                parts += [_("Davon fehlen dir ({count}):").format(
                    count=len(fehlend)), _wrap(fehlend), ""]
            else:
                parts += [_("Du hast alle festgelegten Nummern."), ""]
            if entry.unexpected:
                parts += [_("Vorhanden, aber nicht festgelegt ({count}): "
                            "{numbers}").format(count=len(entry.unexpected),
                                                numbers=_wrap(entry.unexpected)),
                          _("Entweder fehlt das in der Festlegung, oder das "
                            "Heft ist falsch getaggt."), ""]
            parts += [_("Diese Angabe schlägt jede Quelle.")]
            self.detail.setPlainText("\n".join(parts))
            self.btn_check_one.setEnabled(bool(entry.samples))
            self.btn_manual.setText(_("Festlegung ändern …"))
            return
        self.btn_manual.setText(_("Reihe von Hand festlegen …"))
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
            if entry.unexpected:
                parts += ["", _("Vorhanden, aber der Quelle unbekannt "
                                "({count}): {numbers}").format(
                    count=len(entry.unexpected),
                    numbers=_wrap(entry.unexpected))]
            parts += ["", _("Das ist eine Angabe der Quelle, keine "
                            "Gewissheit.")]
        self.detail.setPlainText("\n".join(parts))
        self.btn_check_one.setEnabled(bool(entry.samples))

    def _edit_manual(self) -> None:
        entry = self._selected()
        if entry is None:
            return
        dialog = ManualSeriesDialog(entry, self)
        if not dialog.exec():
            return
        if dialog.cleared:
            self.index.forget_manual(entry.name, entry.publisher or "")
            entry.manual_numbers, entry.manual_note = None, ""
        else:
            entry.manual_numbers = dialog.result_numbers
            self.index.save_manual(entry.name, entry.publisher or "",
                                   dialog.result_numbers)
        self._fill_table()
        self._reselect(entry)

    def _reselect(self, entry) -> None:
        for row in range(self.table.rowCount()):
            if tuple(self.table.item(row, 0).data(PATH_ROLE)) == entry.key:
                self.table.selectRow(row)
                return
        self._show_details()

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
        stop_and_detach(self, self.thread, self.checker)
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
