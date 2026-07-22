"""Dialoge fuer Quellen-Einstellungen und den Auto-Tag-Lauf."""
from __future__ import annotations

import time
from pathlib import Path

from PySide6.QtCore import (
    QObject, Qt, QSettings, QThread, QTimer, Signal,
)
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QDialog, QDialogButtonBox, QFileDialog, QFormLayout,
    QGroupBox, QHBoxLayout, QHeaderView, QLabel, QLineEdit, QMessageBox,
    QProgressBar, QPushButton, QSlider, QTableWidget, QTableWidgetItem,
    QTabWidget, QVBoxLayout, QWidget,
)

from .autotag import Result, run_in_thread
from .config import TaggerSettings
from .i18n import LANGUAGES, _

STATUS_COLORS = {
    "getaggt": QColor(38, 132, 66),
    "unsicher": QColor(190, 130, 20),
    "kein Treffer": QColor(130, 130, 130),
    "uebersprungen": QColor(110, 110, 110),
    "Fehler": QColor(180, 50, 50),
    "abgebrochen": QColor(140, 120, 90),
}

GCD_LANGUAGES = [("Alle Sprachen", ""), ("Deutsch", "de"), ("Englisch", "en"),
                 ("Franzoesisch", "fr"), ("Italienisch", "it"),
                 ("Spanisch", "es"), ("Niederlaendisch", "nl")]


class _FtsWorker(QObject):
    """Baut den GCD-Volltextindex im Hintergrund - der Dump kann riesig sein."""

    progress = Signal(str, int)
    finished = Signal(bool, str)

    def __init__(self, db_path: str):
        super().__init__()
        self.db_path = db_path
        self._stop = False

    def stop(self) -> None:
        self._stop = True

    def run(self) -> None:
        from .providers.gcd import GcdProvider

        try:
            provider = GcdProvider(self.db_path)
            done = provider.build_fts(
                progress=lambda text, pct: self.progress.emit(text, pct),
                should_stop=lambda: self._stop)
            self.finished.emit(done, "")
        except Exception as exc:  # noqa: BLE001
            self.finished.emit(False, str(exc))


class SettingsDialog(QDialog):
    """Alle Einstellungen: Metadaten-Quellen, Automatik, Sprache."""

    def __init__(self, settings: QSettings, parent=None, start_tab: int = 0):
        super().__init__(parent)
        self.settings = settings
        self.config = TaggerSettings.load(settings)
        self.language_changed = False
        self._initial_language = settings.value("language", "auto")
        self.setWindowTitle(_("Einstellungen"))
        self.setMinimumWidth(640)

        outer = QVBoxLayout(self)
        self.tabs = QTabWidget()
        outer.addWidget(self.tabs, 1)
        sources_tab = QWidget()
        root = QVBoxLayout(sources_tab)
        self.tabs.addTab(sources_tab, _("Metadaten-Quellen"))

        cv_box = QGroupBox(_("ComicVine"))
        cv_form = QFormLayout(cv_box)
        self.cv_enabled = QCheckBox(_("ComicVine benutzen"))
        self.cv_enabled.setChecked(self.config.use_comicvine)
        self.cv_key = QLineEdit(self.config.comicvine_key)
        self.cv_key.setEchoMode(QLineEdit.PasswordEchoOnEdit)
        self.cv_key.setPlaceholderText(_("API-Key von comicvine.gamespot.com/api"))
        cv_form.addRow(self.cv_enabled)
        cv_form.addRow(_("API-Key"), self.cv_key)
        cv_hint = QLabel(_(
            "Kostenlos nach Registrierung. Limit 200 Anfragen/Stunde, deshalb "
            "wird gedrosselt und dauerhaft gecacht. Liefert Cover, damit ist "
            "die Bild-Verifikation moeglich."
        ))
        cv_hint.setWordWrap(True)
        cv_hint.setStyleSheet("color:gray;")
        cv_form.addRow(cv_hint)
        root.addWidget(cv_box)

        gcd_box = QGroupBox(_("Grand Comics Database (lokaler Dump)"))
        gcd_form = QFormLayout(gcd_box)
        self.gcd_enabled = QCheckBox(_("GCD benutzen"))
        self.gcd_enabled.setChecked(self.config.use_gcd)
        path_row = QHBoxLayout()
        self.gcd_path = QLineEdit(self.config.gcd_path)
        self.gcd_path.setPlaceholderText(_("Pfad zur SQLite-Datei aus dem GCD-Dump"))
        browse = QPushButton(_("Waehlen …"))
        browse.clicked.connect(self._pick_db)
        self.fts_btn = QPushButton(_("Suche vorbereiten"))
        self.fts_btn.setToolTip(_(
            "Baut einen Volltextindex ueber die Serientitel. Einmalig noetig, "
            "dauert etwa zehn Sekunden - ohne ihn dauert jede Suche im Dump "
            "mehrere Sekunden. Der Dump selbst wird nicht veraendert."))
        self.fts_btn.clicked.connect(self._build_fts)
        path_row.addWidget(self.gcd_path, 1)
        path_row.addWidget(browse)
        path_row.addWidget(self.fts_btn)
        self.gcd_lang = QComboBox()
        for label, code in GCD_LANGUAGES:
            self.gcd_lang.addItem(_(label), code)
        idx = self.gcd_lang.findData(self.config.gcd_language)
        self.gcd_lang.setCurrentIndex(max(0, idx))
        gcd_form.addRow(self.gcd_enabled)
        gcd_form.addRow(_("Datenbank"), path_row)
        gcd_form.addRow(_("Nur Sprache"), self.gcd_lang)
        gcd_hint = QLabel(_(
            "SQLite3-Dump von comics.org/download (Account noetig, Daten "
            "CC-BY). Offline und ohne Limit, stark bei europaeischen "
            "Verlagen. Enthaelt keine Cover, daher kein Bildabgleich."
        ))
        gcd_hint.setWordWrap(True)
        gcd_hint.setStyleSheet("color:gray;")
        gcd_form.addRow(gcd_hint)
        self.fts_status = QLabel()
        self.fts_status.setWordWrap(True)
        gcd_form.addRow(self.fts_status)
        self.fts_bar = QProgressBar()
        self.fts_bar.setVisible(False)
        gcd_form.addRow(self.fts_bar)
        self.gcd_path.textChanged.connect(lambda _t: self._refresh_fts_status())
        self._fts_thread = None
        self._fts_worker = None
        self._refresh_fts_status()
        root.addWidget(gcd_box)

        manga_box = QGroupBox(_("AniList (Manga)"))
        manga_form = QFormLayout(manga_box)
        self.anilist_enabled = QCheckBox(_("AniList als Ergaenzung benutzen"))
        self.anilist_enabled.setChecked(self.config.use_anilist)
        manga_form.addRow(self.anilist_enabled)
        manga_hint = QLabel(_(
            "Kennt Manga-Serien, aber keine einzelnen Baende einer deutschen "
            "Ausgabe. Bestimmt deshalb nie das Heft, sondern fuellt nur Luecken: "
            "Zeichner, Autor, Genre, Beschreibung, Leserichtung. Vorhandene "
            "Angaben bleiben unangetastet. Kein Schluessel noetig."))
        manga_hint.setWordWrap(True)
        manga_hint.setStyleSheet("color:gray;")
        manga_form.addRow(manga_hint)
        root.addWidget(manga_box)

        rule_box = QGroupBox(_("Automatik"))
        rule_form = QFormLayout(rule_box)
        slider_row = QHBoxLayout()
        self.threshold = QSlider(Qt.Horizontal)
        self.threshold.setRange(50, 100)
        self.threshold.setValue(self.config.threshold)
        self.threshold_label = QLabel(f"{self.config.threshold}")
        self.threshold.valueChanged.connect(
            lambda v: self.threshold_label.setText(str(v)))
        slider_row.addWidget(self.threshold, 1)
        slider_row.addWidget(self.threshold_label)
        self.cover_match = QCheckBox(_(
            "Treffer per Cover-Bildvergleich absichern (nur ComicVine, "
            "langsamer)"))
        self.cover_match.setChecked(self.config.use_cover_match)
        self.overwrite = QCheckBox(_("Auch Dateien anfassen, die schon Tags haben"))
        self.overwrite.setChecked(self.config.overwrite_existing)
        rule_form.addRow(_("Schwellwert"), slider_row)
        rule_form.addRow(self.cover_match)
        rule_form.addRow(self.overwrite)
        rule_hint = QLabel(_(
            "Nur Treffer ab diesem Wert werden geschrieben. Alles darunter "
            "landet als „unsicher“ im Protokoll, ohne die Datei zu aendern."
        ))
        rule_hint.setWordWrap(True)
        rule_hint.setStyleSheet("color:gray;")
        rule_form.addRow(rule_hint)
        root.addWidget(rule_box)

        root.addStretch(1)

        general = QWidget()
        gform = QFormLayout(general)
        self.language = QComboBox()
        for code, label in LANGUAGES.items():
            self.language.addItem(_(label), code)
        idx = self.language.findData(self._initial_language)
        self.language.setCurrentIndex(max(0, idx))
        gform.addRow(_("Sprache"), self.language)
        lang_hint = QLabel(_(
            "„Automatisch“ folgt der Systemsprache. Die Umstellung greift "
            "sofort, das Fenster wird dabei neu aufgebaut."))
        lang_hint.setWordWrap(True)
        lang_hint.setStyleSheet("color:gray;")
        gform.addRow(lang_hint)
        self.tabs.addTab(general, _("Allgemein"))
        self.tabs.setCurrentIndex(start_tab)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        outer.addWidget(buttons)

    def _pick_db(self) -> None:
        path, _selected_filter = QFileDialog.getOpenFileName(
            self, _("GCD-SQLite-Dump waehlen"),
            self.gcd_path.text() or str(Path.home()),
            _("SQLite-Datenbank (*.db *.sqlite *.sqlite3 *.gcd);;"
              "Alle Dateien (*)"))
        if path:
            self.gcd_path.setText(path)

    def _refresh_fts_status(self) -> None:
        from .providers.gcd import GcdProvider

        path = self.gcd_path.text().strip()
        if not path:
            self.fts_status.clear()
            self.fts_btn.setEnabled(False)
            return
        provider = GcdProvider(path)
        ok, why = provider.available()
        self.fts_btn.setEnabled(ok)
        if not ok:
            self.fts_status.setText(why)
            self.fts_status.setStyleSheet("color:#c07000;")
            return
        if provider.on_network:
            self.fts_status.setText(_(
                "Die Datenbank liegt auf einem Netzlaufwerk – Abfragen dauern "
                "dadurch ein Vielfaches. Eine lokale Kopie ist deutlich "
                "schneller."))
            self.fts_status.setStyleSheet("color:#c07000;")
            return
        if provider.fts_ready:
            self.fts_status.setText(_("Suche ist vorbereitet."))
            self.fts_status.setStyleSheet("color:#2a7a44;")
        else:
            self.fts_status.setText(_(
                "Suche noch nicht vorbereitet – jede Abfrage dauert sonst "
                "mehrere Sekunden."))
            self.fts_status.setStyleSheet("color:#c07000;")

    def _build_fts(self) -> None:
        if self._fts_thread is not None:
            self._fts_worker.stop()
            return
        self._fts_thread = QThread()
        self._fts_worker = _FtsWorker(self.gcd_path.text().strip())
        self._fts_worker.moveToThread(self._fts_thread)
        self._fts_thread.started.connect(self._fts_worker.run)
        self._fts_worker.progress.connect(self._on_fts_progress)
        self._fts_worker.finished.connect(self._on_fts_finished)
        self.fts_bar.setRange(0, 100)
        self.fts_bar.setValue(0)
        self.fts_bar.setVisible(True)
        self.fts_btn.setText(_("Abbrechen"))
        self._fts_thread.start()

    def _on_fts_progress(self, text: str, percent: int) -> None:
        self.fts_status.setText(text)
        self.fts_status.setStyleSheet("color:gray;")
        self.fts_bar.setValue(percent)

    def _on_fts_finished(self, done: bool, error: str) -> None:
        if self._fts_thread:
            self._fts_thread.quit()
            self._fts_thread.wait(5000)
        self._fts_thread = None
        self._fts_worker = None
        self.fts_bar.setVisible(False)
        self.fts_btn.setText(_("Suche vorbereiten"))
        if error:
            QMessageBox.critical(
                self, _("GCD"),
                _("Vorbereiten fehlgeschlagen:\n{error}").format(error=error))
        self._refresh_fts_status()

    def closeEvent(self, event):  # noqa: N802
        if self._fts_worker:
            self._fts_worker.stop()
        if self._fts_thread:
            self._fts_thread.quit()
            self._fts_thread.wait(5000)
        super().closeEvent(event)

    def accept(self) -> None:
        self.config.use_comicvine = self.cv_enabled.isChecked()
        self.config.comicvine_key = self.cv_key.text().strip()
        self.config.use_gcd = self.gcd_enabled.isChecked()
        self.config.use_anilist = self.anilist_enabled.isChecked()
        self.config.gcd_path = self.gcd_path.text().strip()
        self.config.gcd_language = self.gcd_lang.currentData()
        self.config.threshold = self.threshold.value()
        self.config.use_cover_match = self.cover_match.isChecked()
        self.config.overwrite_existing = self.overwrite.isChecked()
        self.config.save(self.settings)

        chosen = self.language.currentData()
        if chosen != self._initial_language:
            self.settings.setValue("language", chosen)
            self.settings.sync()
            self.language_changed = True
        super().accept()


#: Frueherer Name - der Auto-Tag-Dialog oeffnet damit direkt den Quellen-Tab.
SourcesDialog = SettingsDialog


# ---------------------------------------------------------------------------
class AutoTagDialog(QDialog):
    """Fortschritt und Protokoll eines Auto-Tag-Laufs."""

    COLUMNS = ["Datei", "Status", "Score", "Quelle", "Treffer", "Anmerkung"]

    def __init__(self, paths: list[Path], settings: QSettings, parent=None):
        super().__init__(parent)
        self.paths = paths
        self.settings = settings
        self.thread = None
        self.worker = None
        self.counts: dict[str, int] = {}
        self._current: tuple[int, int, str] | None = None
        self._current_since = 0.0
        # Zeigt die Sekunden zur laufenden Datei - ohne das wirkt eine lange
        # Netzabfrage wie ein Absturz.
        self._tick = QTimer(self)
        self._tick.setInterval(1000)
        self._tick.timeout.connect(self._update_status)

        self.setWindowTitle(
            _("Automatisch taggen – {count} Datei(en)").format(count=len(paths)))
        self.resize(1000, 560)

        root = QVBoxLayout(self)
        self.status = QLabel(_("Bereit."))
        root.addWidget(self.status)
        self.bar = QProgressBar()
        self.bar.setRange(0, len(paths))
        self.bar.setFormat("%v / %m")
        root.addWidget(self.bar)

        self.banner = QLabel()
        self.banner.setWordWrap(True)
        self.banner.setVisible(False)
        self.banner.setObjectName("resultBanner")
        root.addWidget(self.banner)

        self.table = QTableWidget(0, len(self.COLUMNS))
        self.table.setHorizontalHeaderLabels([_(c) for c in self.COLUMNS])
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.Stretch)
        header.setSectionResizeMode(4, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(5, QHeaderView.Stretch)
        self.source_labels: dict[str, str] = {}
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        root.addWidget(self.table, 1)

        row = QHBoxLayout()
        self.btn_settings = QPushButton(_("Quellen …"))
        self.btn_settings.clicked.connect(self._open_settings)
        self.btn_start = QPushButton(_("Starten"))
        self.btn_start.clicked.connect(self.start)
        self.btn_stop = QPushButton(_("Abbrechen"))
        self.btn_stop.setEnabled(False)
        self.btn_stop.clicked.connect(self.stop)
        self.btn_close = QPushButton(_("Schliessen"))
        self.btn_close.clicked.connect(self.reject)
        row.addWidget(self.btn_settings)
        row.addStretch(1)
        row.addWidget(self.btn_start)
        row.addWidget(self.btn_stop)
        row.addWidget(self.btn_close)
        root.addLayout(row)

    # ------------------------------------------------------------------
    def _open_settings(self) -> None:
        SourcesDialog(self.settings, self).exec()

    def start(self) -> None:
        config = TaggerSettings.load(self.settings).build_config()
        if not config.providers:
            QMessageBox.information(
                self, _("Keine Quelle"),
                _("Es ist keine Quelle konfiguriert. Unter „Quellen …“ einen "
                  "ComicVine-API-Key eintragen oder einen GCD-Dump "
                  "auswaehlen."))
            return
        unavailable = [f"{_(p.label)}: {why}"
                       for p in config.providers for ok, why in [p.available()] if not ok]
        if len(unavailable) == len(config.providers):
            QMessageBox.warning(self, _("Keine Quelle nutzbar"),
                                "\n".join(unavailable))
            return

        self.source_labels = {p.name: _(p.label) for p in config.providers}
        self.table.setRowCount(0)
        self.counts.clear()
        self.banner.setVisible(False)
        self.btn_stop.setText(_("Abbrechen"))
        self._set_running(True)
        self._current_name = ""
        self._current_since = time.monotonic()
        self._tick.start()

        self.thread, self.worker = run_in_thread(self.paths, config)
        self.worker.progress.connect(self._on_progress)
        self.worker.result.connect(self._on_result)
        self.worker.finished.connect(self._on_finished)
        self.thread.start()

    def _set_running(self, running: bool) -> None:
        """Waehrend des Laufs gibt es nur einen Ausweg: Abbrechen."""
        self.btn_start.setEnabled(not running)
        self.btn_settings.setEnabled(not running)
        self.btn_stop.setEnabled(running)
        self.btn_close.setVisible(not running)
        self.bar.setVisible(True)

    @property
    def running(self) -> bool:
        return self.thread is not None and self.thread.isRunning()

    def stop(self) -> None:
        if not self.worker:
            return
        self.worker.stop()
        self.btn_stop.setEnabled(False)
        self.btn_stop.setText(_("Wird abgebrochen …"))
        self.status.setText(_("Abbruch – die laufende Datei wird noch beendet."))

    def _on_progress(self, done: int, total: int, name: str) -> None:
        self.bar.setValue(done - 1)
        self._current = (done, total, name)
        self._current_since = time.monotonic()
        self._update_status()

    def _update_status(self) -> None:
        if not getattr(self, "_current", None):
            return
        done, total, name = self._current
        seconds = int(time.monotonic() - self._current_since)
        text = _("[{done}/{total}] {name}").format(done=done, total=total, name=name)
        if seconds >= 3 and self.running:
            text += "  " + _("({seconds} s …)").format(seconds=seconds)
        self.status.setText(text)

    def _on_result(self, result: Result) -> None:
        self.counts[result.status] = self.counts.get(result.status, 0) + 1
        row = self.table.rowCount()
        self.table.insertRow(row)
        values = [result.path.name, _(result.status),
                  str(result.score) if result.score else "",
                  self.source_labels.get(result.source, result.source),
                  result.summary, result.detail]
        for col, value in enumerate(values):
            item = QTableWidgetItem(value)
            if col == 1 and result.status in STATUS_COLORS:
                item.setForeground(STATUS_COLORS[result.status])
            self.table.setItem(row, col, item)
        self.table.scrollToBottom()
        self.bar.setValue(self.bar.value() + 1)

    def _on_finished(self) -> None:
        self._tick.stop()
        self._current = None
        if self.thread:
            self.thread.quit()
            self.thread.wait(3000)
        self.thread = self.worker = None
        self._set_running(False)
        self.bar.setValue(len(self.paths))
        self.bar.setVisible(False)

        tagged = self.counts.get("getaggt", 0)
        problems = sum(v for k, v in self.counts.items()
                       if k in ("Fehler", "unsicher", "kein Treffer"))
        parts = [f"{v} {_(k)}" for k, v in sorted(self.counts.items())]
        headline = (_("Fertig – {count} getaggt").format(count=tagged) if tagged
                    else _("Fertig – nichts geändert"))
        self.status.setText("")
        self.banner.setText(f"{headline}\n{' · '.join(parts)}")
        self.banner.setProperty(
            "state", "ok" if tagged and not problems
            else "warn" if tagged or problems else "neutral")
        self.banner.style().unpolish(self.banner)
        self.banner.style().polish(self.banner)
        self.banner.setVisible(True)
        self.btn_close.setDefault(True)
        self.btn_close.setFocus()

    def reject(self) -> None:
        """Esc und das Fensterkreuz brechen ab und schliessen - immer."""
        self._detach_worker()
        super().reject()

    def closeEvent(self, event):  # noqa: N802
        self._detach_worker()
        super().closeEvent(event)

    def _detach_worker(self) -> None:
        """Lauf abbrechen und den Thread ausklinken, ohne zu blockieren.

        Kurz warten reicht meistens; haengt eine Netzabfrage laenger, wird der
        Thread beim Elternfenster geparkt und raeumt sich selbst auf. Auf ihn zu
        warten wuerde das Fenster erneut einfrieren - genau das soll es nicht.
        """
        if not self.running:
            return
        if self.worker:
            self.worker.stop()
        thread = self.thread
        thread.quit()
        if not thread.wait(400):
            parent = self.parent()
            if parent is not None:
                pending = getattr(parent, "_pending_threads", None)
                if pending is None:
                    pending = parent._pending_threads = []
                pending.append((thread, self.worker))
                thread.finished.connect(
                    lambda t=thread, w=self.worker: pending.remove((t, w))
                    if (t, w) in pending else None)
        self.thread = self.worker = None
