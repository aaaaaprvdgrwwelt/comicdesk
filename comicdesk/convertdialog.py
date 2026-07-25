"""Seitenbilder mehrerer Comics neu kodieren.

Der Dialog stellt das Zielformat ein, rechnet auf Wunsch an einer Probeseite
vor, was das bringt, und arbeitet die Auswahl dann im Hintergrund ab.
"""
from __future__ import annotations

import os
from pathlib import Path

from PySide6.QtCore import QObject, Qt, QThread, Signal
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QDialog, QDialogButtonBox, QFormLayout, QHBoxLayout,
    QLabel, QMessageBox, QProgressBar, QPushButton, QSlider, QSpinBox,
    QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
)

from .background import stop_and_detach
from .i18n import _
from .recompress import (
    Abort, Options, Result, available_formats, convert_archive, human, sample,
)

#: Was mit der Ausgangsdatei geschieht.
KEEP, REPLACE = range(2)


def _unique(path: Path) -> Path:
    stamm, i = path, 2
    while path.exists():
        path = stamm.with_name(f"{stamm.stem} ({i}){stamm.suffix}")
        i += 1
    return path


class _Worker(QObject):
    """Arbeitet die Dateien nacheinander ab."""

    file_started = Signal(int, str)         # Zeile, Name
    file_progress = Signal(int, int, int)   # Zeile, Seite, Gesamt
    file_done = Signal(int, object, str)    # Zeile, Result oder None, Fehler
    finished = Signal(object)               # Gesamt-Result

    def __init__(self, paths: list[Path], options: Options, mode: int):
        super().__init__()
        self.paths = paths
        self.options = options
        self.mode = mode
        self._stop = False

    def stop(self) -> None:
        self._stop = True

    def run(self) -> None:
        gesamt = Result()
        for zeile, pfad in enumerate(self.paths):
            if self._stop:
                break
            self.file_started.emit(zeile, pfad.name)
            # Der Formatname im Dateinamen ist der Kuerzel, nicht das Label -
            # "JPEG XL" waere hier sonst als "JPEG" zu lesen.
            ziel = _unique(pfad.with_name(
                f"{pfad.stem} [{self.options.spec.key}].cbz"))
            try:
                ergebnis = convert_archive(
                    pfad, ziel, self.options,
                    progress=lambda a, b, z=zeile: self.file_progress.emit(z, a, b),
                    should_stop=lambda: self._stop)
            except Abort:
                break
            except Exception as exc:  # noqa: BLE001
                self.file_done.emit(zeile, None, str(exc))
                continue
            if self.mode == REPLACE:
                fehler = self._replace(pfad, ziel)
                if fehler:
                    self.file_done.emit(zeile, ergebnis, fehler)
                    continue
            gesamt.pages += ergebnis.pages
            gesamt.converted += ergebnis.converted
            gesamt.kept += ergebnis.kept
            gesamt.failed += ergebnis.failed
            gesamt.old_file += ergebnis.old_file
            gesamt.new_file += ergebnis.new_file
            self.file_done.emit(zeile, ergebnis, "")
        self.finished.emit(gesamt)

    def _replace(self, alt: Path, neu: Path) -> str:
        """Original in den Papierkorb, neue Datei an dessen Stelle."""
        from send2trash import send2trash

        try:
            send2trash(str(alt))
            neu.rename(alt.with_suffix(".cbz"))
        except Exception as exc:  # noqa: BLE001
            return str(exc)
        return ""


class ConvertDialog(QDialog):
    """Zielformat waehlen, Probe rechnen, Auswahl umkodieren."""

    #: Fertige Dateien - das Hauptfenster indiziert sie nach.
    converted = Signal(str)

    COLUMNS = ["Datei", "Seiten", "Vorher", "Nachher", "Ersparnis"]

    def __init__(self, paths: list[Path], settings, parent=None):
        super().__init__(parent)
        self.paths = [Path(p) for p in paths]
        self.settings = settings
        self.thread: QThread | None = None
        self.worker: _Worker | None = None

        self.setWindowTitle(_("Bilder konvertieren"))
        self.resize(760, 560)
        root = QVBoxLayout(self)

        root.addWidget(QLabel(_(
            "Schreibt die Seiten neu - als CBZ, mit den Tags. WebP und AVIF "
            "sind bei gleichem Aussehen deutlich kleiner als alte "
            "JPEG-Scans. Seiten, die schon im Zielformat vorliegen, bleiben "
            "unberührt.")))

        form = QFormLayout()
        self.format = QComboBox()
        for spec in available_formats():
            self.format.addItem(_(spec.label), spec.key)
        self.format.currentIndexChanged.connect(self._on_format)
        form.addRow(_("Format"), self.format)

        self.quality = QSlider(Qt.Horizontal)
        self.quality.setRange(30, 100)
        self.quality.setTickInterval(10)
        self.quality.setTickPosition(QSlider.TicksBelow)
        self.quality_label = QLabel()
        self.quality.valueChanged.connect(self._on_quality)
        zeile = QHBoxLayout()
        zeile.addWidget(self.quality, 1)
        zeile.addWidget(self.quality_label)
        rahmen = QWidget()
        rahmen.setLayout(zeile)
        form.addRow(_("Qualität"), rahmen)

        self.lossless = QCheckBox(_("Verlustfrei"))
        self.lossless.toggled.connect(self._on_lossless)
        form.addRow("", self.lossless)
        self.hint = QLabel()
        self.hint.setWordWrap(True)
        self.hint.setStyleSheet("color:gray;")
        form.addRow("", self.hint)

        self.max_edge = QSpinBox()
        self.max_edge.setRange(0, 8000)
        self.max_edge.setSingleStep(100)
        self.max_edge.setSpecialValueText(_("unverändert"))
        self.max_edge.setSuffix(" px")
        self.max_edge.setToolTip(_(
            "Begrenzt die längere Kante. 0 lässt die Auflösung, wie sie ist."))
        form.addRow(_("Größe begrenzen"), self.max_edge)

        self.smaller = QCheckBox(_("Nur übernehmen, wenn kleiner"))
        self.smaller.setChecked(True)
        self.smaller.setToolTip(_(
            "Seiten, die durch das Umkodieren wachsen würden, bleiben im "
            "alten Format."))
        form.addRow("", self.smaller)

        self.mode = QComboBox()
        self.mode.addItem(_("Neue Datei daneben legen"), KEEP)
        self.mode.addItem(_("Original ersetzen (in den Papierkorb)"), REPLACE)
        form.addRow(_("Originale"), self.mode)

        self.threads = QSpinBox()
        self.threads.setRange(1, 32)
        self.threads.setValue(min(8, max(2, (os.cpu_count() or 4))))
        form.addRow(_("Gleichzeitig"), self.threads)
        root.addLayout(form)

        probe = QHBoxLayout()
        self.btn_sample = QPushButton(_("Probe rechnen"))
        self.btn_sample.setToolTip(_(
            "Kodiert eine Seite aus der Mitte des ersten Hefts und zeigt, "
            "was das bringt."))
        self.btn_sample.clicked.connect(self.run_sample)
        self.sample_label = QLabel()
        probe.addWidget(self.btn_sample)
        probe.addWidget(self.sample_label, 1)
        root.addLayout(probe)

        self.table = QTableWidget(len(self.paths), len(self.COLUMNS))
        self.table.setHorizontalHeaderLabels([_(c) for c in self.COLUMNS])
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.setColumnWidth(0, 300)
        self.table.verticalHeader().setVisible(False)
        for zeile, pfad in enumerate(self.paths):
            self.table.setItem(zeile, 0, QTableWidgetItem(pfad.name))
        root.addWidget(self.table, 1)

        self.progress = QProgressBar()
        self.progress.setVisible(False)
        root.addWidget(self.progress)
        self.status = QLabel()
        root.addWidget(self.status)

        self.buttons = QDialogButtonBox()
        self.btn_start = self.buttons.addButton(_("Umkodieren"),
                                                QDialogButtonBox.AcceptRole)
        self.btn_close = self.buttons.addButton(QDialogButtonBox.Close)
        self.btn_close.setText(_("Schliessen"))
        self.btn_start.clicked.connect(self.start)
        self.btn_close.clicked.connect(self.reject)
        root.addWidget(self.buttons)

        self._restore()
        self._on_format()

    # --- Einstellungen ------------------------------------------------
    def _restore(self) -> None:
        s = self.settings
        gemerkt = str(s.value("convert/format", "WEBP"))
        index = self.format.findData(gemerkt)
        self.format.setCurrentIndex(max(0, index))
        self.quality.setValue(int(s.value("convert/quality", 80)))
        self.lossless.setChecked(s.value("convert/lossless", False, type=bool))
        self.max_edge.setValue(int(s.value("convert/max_edge", 0)))
        self.smaller.setChecked(s.value("convert/smaller", True, type=bool))

    def _store(self) -> None:
        s = self.settings
        s.setValue("convert/format", self.format.currentData())
        s.setValue("convert/quality", self.quality.value())
        s.setValue("convert/lossless", self.lossless.isChecked())
        s.setValue("convert/max_edge", self.max_edge.value())
        s.setValue("convert/smaller", self.smaller.isChecked())

    def options(self) -> Options:
        return Options(
            format=self.format.currentData(),
            quality=self.quality.value(),
            lossless=self.lossless.isChecked() and self.lossless.isEnabled(),
            max_edge=self.max_edge.value(),
            only_if_smaller=self.smaller.isChecked(),
            threads=self.threads.value(),
        )

    def _on_format(self) -> None:
        spec = self.options().spec
        self.lossless.setEnabled(spec.lossless and spec.key != "PNG")
        if not self.lossless.isEnabled():
            self.lossless.setChecked(False)
        self.lossless.setToolTip(_(
            "Bei JPEG XL werden vorhandene JPEG-Seiten bit-genau umgepackt: "
            "kein Verlust, trotzdem rund ein Fünftel kleiner.")
            if spec.key == "JXL" else _(
            "Nur bei Strichzeichnungen sinnvoll - Fotos und Rasterscans "
            "werden dabei meist größer."))
        # PNG ist immer verlustfrei, die Qualitaet waere ohne Wirkung.
        verlustbehaftet = spec.key != "PNG" and not self.lossless.isChecked()
        self.quality.setEnabled(verlustbehaftet)
        self._on_quality()
        self._update_hint()
        self.sample_label.clear()

    def _on_lossless(self) -> None:
        self.quality.setEnabled(not self.lossless.isChecked()
                                and self.options().spec.key != "PNG")
        self._update_hint()
        self.sample_label.clear()

    def _update_hint(self) -> None:
        spec = self.options().spec
        if spec.key == "JXL" and self.lossless.isChecked():
            self.hint.setText(_(
                "JPEG-Seiten werden bit-genau umgepackt – die Bildpunkte "
                "bleiben identisch, die Datei wird trotzdem rund 20 % "
                "kleiner. Seiten, die kein JPEG sind, werden verlustfrei neu "
                "kodiert und können dabei wachsen."))
        elif spec.key == "AVIF":
            self.hint.setText(_(
                "Holt bei Scans am meisten heraus, braucht dafür aber rund "
                "eine halbe Sekunde je Seite."))
        else:
            self.hint.clear()

    def _on_quality(self) -> None:
        wert = self.quality.value()
        hinweis = (_("sichtbar weicher") if wert < 55
                   else _("guter Kompromiss") if wert < 90 else _("nah am Original"))
        self.quality_label.setText(
            f"{wert}  ({hinweis})" if self.quality.isEnabled() else _("–"))

    # --- Probe --------------------------------------------------------
    def run_sample(self) -> None:
        if not self.paths:
            return
        self.btn_sample.setEnabled(False)
        self.sample_label.setText(_("Wird gerechnet …"))
        # Eine einzelne Seite ist schnell genug fuer den Vordergrund; nur
        # die Anzeige muss vorher noch durchkommen.
        self.sample_label.repaint()
        try:
            alt, neu = sample(self.paths[0], self.options())
        except Exception as exc:  # noqa: BLE001
            self.sample_label.setText(str(exc))
            self.btn_sample.setEnabled(True)
            return
        anteil = round((alt - neu) * 100 / alt) if alt else 0
        self.sample_label.setText(_(
            "Probeseite: {old} → {new}  ({percent} %)").format(
                old=human(alt), new=human(neu),
                percent=f"+{-anteil}" if anteil < 0 else f"−{anteil}"))
        self.btn_sample.setEnabled(True)

    # --- Lauf ---------------------------------------------------------
    def start(self) -> None:
        if self.thread is not None:
            return
        if self.mode.currentData() == REPLACE and QMessageBox.question(
            self, _("Originale ersetzen"),
            _("{count} Datei(en) umkodieren und die Originale in den "
              "Papierkorb legen?").format(count=len(self.paths)),
        ) != QMessageBox.Yes:
            return
        self._store()
        self.btn_start.setEnabled(False)
        self.progress.setVisible(True)
        self.progress.setRange(0, 0)
        for zeile in range(self.table.rowCount()):
            for spalte in range(1, len(self.COLUMNS)):
                self.table.setItem(zeile, spalte, QTableWidgetItem(""))

        self.thread = QThread()
        self.worker = _Worker(self.paths, self.options(),
                              self.mode.currentData())
        self.worker.moveToThread(self.thread)
        self.thread.started.connect(self.worker.run)
        self.worker.file_started.connect(self._on_started)
        self.worker.file_progress.connect(self._on_progress)
        self.worker.file_done.connect(self._on_done)
        self.worker.finished.connect(self._on_finished)
        self.thread.start()

    def _on_started(self, zeile: int, name: str) -> None:
        self.status.setText(_("{name} …").format(name=name))
        self.table.selectRow(zeile)

    def _on_progress(self, zeile: int, seite: int, gesamt: int) -> None:
        self.progress.setRange(0, gesamt)
        self.progress.setValue(seite)
        self.table.setItem(zeile, 1, QTableWidgetItem(f"{seite} / {gesamt}"))

    def _on_done(self, zeile: int, ergebnis, fehler: str) -> None:
        if ergebnis is None:
            self.table.setItem(zeile, 1, QTableWidgetItem(_("Fehler")))
            self.table.setItem(zeile, 2, QTableWidgetItem(fehler))
            return
        werte = [str(ergebnis.pages), human(ergebnis.old_file),
                 human(ergebnis.new_file),
                 fehler or _("{percent} %").format(percent=ergebnis.percent)]
        for spalte, wert in enumerate(werte, 1):
            self.table.setItem(zeile, spalte, QTableWidgetItem(wert))
        self.converted.emit(str(self.paths[zeile]))

    def _on_finished(self, gesamt) -> None:
        self._stop_all()
        self.progress.setVisible(False)
        self.btn_start.setEnabled(True)
        if not gesamt.old_file:
            self.status.setText(_("Nichts umkodiert."))
            return
        self.status.setText(_(
            "{files} Datei(en): {old} → {new}, {saved} gespart ({percent} %). "
            "{kept} Seite(n) unverändert gelassen.").format(
                files=len(self.paths), old=human(gesamt.old_file),
                new=human(gesamt.new_file), saved=human(gesamt.saved),
                percent=gesamt.percent, kept=gesamt.kept))

    # ------------------------------------------------------------------
    def _stop_all(self) -> None:
        stop_and_detach(self, self.thread, self.worker)
        self.thread = self.worker = None

    def reject(self) -> None:
        if self.thread is not None:
            self.status.setText(_("Wird abgebrochen …"))
            self._stop_all()
        super().reject()

    def closeEvent(self, event):  # noqa: N802
        self._stop_all()
        super().closeEvent(event)
