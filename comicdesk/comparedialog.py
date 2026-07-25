"""Zwei Fassungen desselben Hefts nebeneinander ansehen und eine behalten.

Nach dem Umkodieren steht die Frage: hat es gelitten? Der Dialog legt
Original und neue Fassung Seite an Seite - dieselbe Seite, derselbe
Massstab, ein gemeinsamer Ausschnitt. Bei 100 % sieht man Artefakte
sofort; wer nichts sieht, kann das Original getrost gehen lassen.

Beide Fassungen als ein Bild nebeneinander zu setzen ist Absicht: so
koennen Ausschnitt und Zoom gar nicht erst auseinanderlaufen.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from PySide6.QtCore import (
    QMutex, QObject, QPoint, QPointF, QRectF, Qt, QThread, Signal,
)
from PySide6.QtGui import QColor, QImage, QPainter, QPen
from PySide6.QtWidgets import (
    QAbstractItemView, QDialog, QDialogButtonBox, QHBoxLayout, QLabel,
    QMessageBox, QPushButton, QSlider, QTableWidget, QTableWidgetItem,
    QVBoxLayout, QWidget,
)

from .archive import open_comic
from .background import stop_and_detach
from .i18n import _
from .imaging import load_image
from .recompress import human

#: Entscheidung je Paar.
UNDECIDED, KEEP_NEW, KEEP_OLD = range(3)
#: Breite des Trennstreifens zwischen beiden Fassungen.
GAP = 14


@dataclass
class Pair:
    old: Path
    new: Path
    old_size: int = 0
    new_size: int = 0
    decision: int = UNDECIDED

    @property
    def saved(self) -> int:
        return self.old_size - self.new_size


class _PairWorker(QObject):
    """Laedt beide Fassungen einer Seite - nacheinander, nie gleichzeitig.

    ZipFile vertraegt keine parallelen Zugriffe, und ueber ein Netzlaufwerk
    bringt paralleles Lesen ohnehin nichts.
    """

    ready = Signal(int, QImage, QImage, int, int)   # Seite, alt, neu, Bytes
    failed = Signal(str)
    counted = Signal(int)

    def __init__(self, pair: Pair):
        super().__init__()
        self.pair = pair
        self._wanted = 0
        self._stop = False
        self._lock = QMutex()

    def stop(self) -> None:
        self._stop = True

    def request(self, index: int) -> None:
        self._lock.lock()
        self._wanted = index
        self._lock.unlock()

    def run(self) -> None:
        alt = neu = None
        try:
            alt, neu = open_comic(self.pair.old), open_comic(self.pair.new)
            self.counted.emit(min(alt.page_count, neu.page_count))
            geliefert = -1
            while not self._stop:
                self._lock.lock()
                gewuenscht = self._wanted
                self._lock.unlock()
                if gewuenscht == geliefert:
                    QThread.msleep(40)
                    continue
                roh_alt = alt.page_bytes(gewuenscht)
                roh_neu = neu.page_bytes(gewuenscht)
                if self._stop:
                    break
                self.ready.emit(gewuenscht, load_image(roh_alt),
                                load_image(roh_neu), len(roh_alt), len(roh_neu))
                geliefert = gewuenscht
        except Exception as exc:  # noqa: BLE001
            if not self._stop:
                self.failed.emit(str(exc))
        finally:
            for comic in (alt, neu):
                if comic is not None:
                    comic.close()


class _SideBySide(QWidget):
    """Zeigt beiden Fassungen denselben Ausschnitt - nebeneinander.

    Nicht zwei aneinandergelegte Seiten: bei 100 % laege dann links das Ende
    der einen und rechts der Anfang der anderen Seite, und man vergliche
    verschiedene Stellen. Stattdessen wird derselbe Bereich der Seite aus
    beiden Fassungen geschnitten und nebeneinander gemalt.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumHeight(320)
        self.old = QImage()
        self.new = QImage()
        self.zoom = 0.0             # 0 heisst: ganze Seite einpassen
        self.offset = QPointF(0, 0)  # linke obere Ecke in Bildpunkten
        self._drag: QPoint | None = None

    # ------------------------------------------------------------------
    def set_images(self, alt: QImage, neu: QImage) -> None:
        neue_seite = alt.size() != self.old.size()
        self.old, self.new = alt, neu
        if neue_seite:
            self.offset = QPointF(0, 0)
        self._clamp()
        self.update()

    def set_zoom(self, zoom: float) -> None:
        mitte = self._center()
        self.zoom = zoom
        self._center_on(mitte)
        self.update()

    def _half(self) -> float:
        return max(1.0, (self.width() - GAP) / 2)

    def _factor(self) -> float:
        """Bildpunkte je Bildschirmpunkt."""
        if self.zoom > 0:
            return self.zoom
        if self.old.isNull():
            return 1.0
        return min(self._half() / max(1, self.old.width()),
                   self.height() / max(1, self.old.height()))

    def _view_size(self) -> tuple[float, float]:
        f = self._factor()
        return self._half() / f, self.height() / f

    def _center(self) -> QPointF:
        breite, hoehe = self._view_size()
        return QPointF(self.offset.x() + breite / 2,
                       self.offset.y() + hoehe / 2)

    def _center_on(self, punkt: QPointF) -> None:
        breite, hoehe = self._view_size()
        self.offset = QPointF(punkt.x() - breite / 2, punkt.y() - hoehe / 2)
        self._clamp()

    def _clamp(self) -> None:
        if self.old.isNull():
            return
        breite, hoehe = self._view_size()
        x = min(max(0.0, self.offset.x()), max(0.0, self.old.width() - breite))
        y = min(max(0.0, self.offset.y()), max(0.0, self.old.height() - hoehe))
        self.offset = QPointF(x, y)

    # ------------------------------------------------------------------
    def paintEvent(self, event):  # noqa: N802
        maler = QPainter(self)
        maler.fillRect(self.rect(), QColor("#202020"))
        if self.old.isNull() or self.new.isNull():
            return
        maler.setRenderHint(QPainter.SmoothPixmapTransform)
        breite, hoehe = self._view_size()
        quelle = QRectF(self.offset.x(), self.offset.y(), breite, hoehe)
        halb = self._half()
        for spalte, bild in ((0.0, self.old), (halb + GAP, self.new)):
            ziel = QRectF(spalte, 0, halb, self.height())
            maler.drawImage(ziel, bild, quelle)
        maler.setPen(QPen(QColor("#f0a030"), 2))
        mitte = halb + GAP / 2
        maler.drawLine(QPointF(mitte, 0), QPointF(mitte, self.height()))

    # --- Ziehen und Rad -----------------------------------------------
    def mousePressEvent(self, event):  # noqa: N802
        if event.button() == Qt.LeftButton:
            self._drag = event.position().toPoint()
            self.setCursor(Qt.ClosedHandCursor)
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):  # noqa: N802
        if self._drag is not None and event.buttons() & Qt.LeftButton:
            delta = event.position().toPoint() - self._drag
            self._drag = event.position().toPoint()
            f = self._factor()
            self.offset -= QPointF(delta.x() / f, delta.y() / f)
            self._clamp()
            self.update()
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):  # noqa: N802
        self._drag = None
        self.unsetCursor()
        super().mouseReleaseEvent(event)

    def wheelEvent(self, event):  # noqa: N802
        schritt = event.angleDelta().y() / self._factor() / 3
        self.offset -= QPointF(0, schritt)
        self._clamp()
        self.update()
        event.accept()

    def resizeEvent(self, event):  # noqa: N802
        super().resizeEvent(event)
        self._clamp()


class CompareDialog(QDialog):
    """Fassungen vergleichen und je Heft eine davon in den Papierkorb legen."""

    #: Ein Paar ist entschieden (behaltene Datei, geloeschte Datei).
    resolved = Signal(str, str)

    def __init__(self, pairs: list[Pair], parent=None):
        super().__init__(parent)
        self.pairs = pairs
        self.current = 0
        self.pages = 0
        self.page = 0
        self.thread: QThread | None = None
        self.worker: _PairWorker | None = None

        self.setWindowTitle(_("Fassungen vergleichen"))
        self.resize(1150, 800)
        root = QVBoxLayout(self)
        root.addWidget(QLabel(_(
            "Links das Original, rechts die neue Fassung – dieselbe Seite im "
            "selben Ausschnitt. Bei 100 % zeigen sich Artefakte am ehesten in "
            "Flächen und an Rasterpunkten. Was du behältst, bleibt liegen; "
            "die andere Fassung wandert in den Papierkorb.")))

        mitte = QHBoxLayout()
        self.table = QTableWidget(len(pairs), 4)
        self.table.setHorizontalHeaderLabels(
            [_(c) for c in ("Datei", "Vorher", "Nachher", "Entscheidung")])
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setMinimumWidth(390)
        self.table.setMaximumWidth(430)
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.currentCellChanged.connect(
            lambda zeile, *_a: self.show_pair(zeile))
        for zeile, paar in enumerate(pairs):
            self.table.setItem(zeile, 0, QTableWidgetItem(paar.old.name))
            self.table.setItem(zeile, 1, QTableWidgetItem(human(paar.old_size)))
            self.table.setItem(zeile, 2, QTableWidgetItem(human(paar.new_size)))
            self.table.setItem(zeile, 3, QTableWidgetItem(""))
        self.table.setColumnWidth(0, 150)
        for spalte in (1, 2):
            self.table.setColumnWidth(spalte, 62)
        mitte.addWidget(self.table)

        rechts = QVBoxLayout()
        kopf = QHBoxLayout()
        self.head_old = QLabel()
        self.head_new = QLabel()
        for label in (self.head_old, self.head_new):
            label.setAlignment(Qt.AlignCenter)
            kopf.addWidget(label, 1)
        rechts.addLayout(kopf)

        self.view = _SideBySide()
        rechts.addWidget(self.view, 1)

        steuer = QHBoxLayout()
        self.slider = QSlider(Qt.Horizontal)
        self.slider.setMinimum(1)
        self.slider.valueChanged.connect(self._on_page)
        self.page_label = QLabel()
        for text, zoom in ((_("Ganze Seite"), 0.0), ("100 %", 1.0),
                           ("200 %", 2.0), ("400 %", 4.0)):
            knopf = QPushButton(text)
            knopf.setMaximumWidth(90)
            knopf.clicked.connect(lambda _c, z=zoom: self.view.set_zoom(z))
            steuer.addWidget(knopf)
        steuer.addWidget(self.slider, 1)
        steuer.addWidget(self.page_label)
        rechts.addLayout(steuer)

        wahl = QHBoxLayout()
        self.btn_new = QPushButton(_("Neue behalten, Original löschen"))
        self.btn_new.clicked.connect(lambda: self.decide(KEEP_NEW))
        self.btn_old = QPushButton(_("Original behalten, neue löschen"))
        self.btn_old.clicked.connect(lambda: self.decide(KEEP_OLD))
        self.btn_skip = QPushButton(_("Offen lassen"))
        self.btn_skip.clicked.connect(lambda: self.decide(UNDECIDED))
        for knopf in (self.btn_new, self.btn_old, self.btn_skip):
            wahl.addWidget(knopf)
        rechts.addLayout(wahl)
        mitte.addLayout(rechts, 1)
        root.addLayout(mitte)

        self.status = QLabel()
        root.addWidget(self.status)

        knoepfe = QDialogButtonBox()
        self.btn_apply = knoepfe.addButton(_("Ausführen"),
                                           QDialogButtonBox.AcceptRole)
        self.btn_close = knoepfe.addButton(QDialogButtonBox.Close)
        self.btn_close.setText(_("Schliessen"))
        self.btn_apply.clicked.connect(self.apply)
        self.btn_close.clicked.connect(self.reject)
        root.addWidget(knoepfe)

        if pairs:
            self.table.selectRow(0)

    # --- Paar zeigen --------------------------------------------------
    def show_pair(self, zeile: int) -> None:
        if not 0 <= zeile < len(self.pairs):
            return
        self._stop_all()
        self.current = zeile
        paar = self.pairs[zeile]
        self.head_old.setText(_("Original · {size}").format(
            size=human(paar.old_size)))
        self.head_new.setText(_("Neu · {size} ({percent} %)").format(
            size=human(paar.new_size),
            percent=round(paar.saved * 100 / paar.old_size)
            if paar.old_size else 0))
        self.status.setText(_("Seiten werden geladen …"))

        self.thread = QThread()
        self.worker = _PairWorker(paar)
        self.worker.moveToThread(self.thread)
        self.thread.started.connect(self.worker.run)
        self.worker.counted.connect(self._on_count)
        self.worker.ready.connect(self._on_pages)
        self.worker.failed.connect(self.status.setText)
        self.thread.start()
        self.worker.request(self.page if self.page < self.pages else 0)

    def _on_count(self, anzahl: int) -> None:
        self.pages = anzahl
        self.slider.blockSignals(True)
        self.slider.setMaximum(max(1, anzahl))
        self.page = min(self.page, max(0, anzahl - 1))
        self.slider.setValue(self.page + 1)
        self.slider.blockSignals(False)
        if self.worker is not None:
            self.worker.request(self.page)

    def _on_page(self, wert: int) -> None:
        self.page = wert - 1
        if self.worker is not None:
            self.worker.request(self.page)

    def _on_pages(self, index: int, alt: QImage, neu: QImage,
                  alt_bytes: int, neu_bytes: int) -> None:
        if alt.isNull() or neu.isNull():
            self.status.setText(_("Seite {page} nicht lesbar.").format(
                page=index + 1))
            return
        self.view.set_images(alt, neu)
        self.page_label.setText(_("Seite {page} / {total}").format(
            page=index + 1, total=self.pages))
        self.status.setText(_(
            "Diese Seite: {old} → {new}  ·  {ow}×{oh} gegen {nw}×{nh}").format(
                old=human(alt_bytes), new=human(neu_bytes),
                ow=alt.width(), oh=alt.height(),
                nw=neu.width(), nh=neu.height()))

    # --- Entscheiden --------------------------------------------------
    def decide(self, wahl: int) -> None:
        if not self.pairs:
            return
        paar = self.pairs[self.current]
        paar.decision = wahl
        text = {KEEP_NEW: _("neue behalten"), KEEP_OLD: _("Original behalten"),
                UNDECIDED: ""}[wahl]
        self.table.setItem(self.current, 3, QTableWidgetItem(text))
        if self.current + 1 < len(self.pairs):
            self.table.selectRow(self.current + 1)

    def apply(self) -> None:
        from send2trash import send2trash

        offen = [p for p in self.pairs if p.decision == UNDECIDED]
        entschieden = [p for p in self.pairs if p.decision != UNDECIDED]
        if not entschieden:
            self.status.setText(_("Nichts entschieden."))
            return
        if QMessageBox.question(
            self, _("Fassungen aufräumen"),
            _("{count} Datei(en) in den Papierkorb legen?{rest}").format(
                count=len(entschieden),
                rest=("\n\n" + _("{open} Heft(e) bleiben unentschieden – dort "
                                 "passiert nichts.").format(open=len(offen)))
                if offen else ""),
        ) != QMessageBox.Yes:
            return
        self._stop_all()
        fehler = []
        erledigt = 0
        for paar in entschieden:
            behalten = paar.new if paar.decision == KEEP_NEW else paar.old
            weg = paar.old if paar.decision == KEEP_NEW else paar.new
            try:
                send2trash(str(weg))
                if paar.decision == KEEP_NEW:
                    # Die neue Fassung tritt an die Stelle des Originals -
                    # sonst bleibt "[AVIF]" fuer immer im Dateinamen stehen.
                    ziel = paar.old.with_suffix(".cbz")
                    if not ziel.exists():
                        behalten.rename(ziel)
                        behalten = ziel
            except Exception as exc:  # noqa: BLE001
                fehler.append(f"{weg.name}: {exc}")
                continue
            erledigt += 1
            paar.decision = UNDECIDED
            self.resolved.emit(str(behalten), str(weg))
        if fehler:
            QMessageBox.warning(self, _("Fassungen aufräumen"),
                                "\n".join(fehler[:10]))
        self.status.setText(_("{count} Datei(en) in den Papierkorb gelegt."
                              ).format(count=erledigt))
        if not offen:
            self.accept()

    # ------------------------------------------------------------------
    def _stop_all(self) -> None:
        stop_and_detach(self, self.thread, self.worker)
        self.thread = self.worker = None

    def reject(self) -> None:
        self._stop_all()
        super().reject()

    def accept(self) -> None:
        self._stop_all()
        super().accept()

    def closeEvent(self, event):  # noqa: N802
        self._stop_all()
        super().closeEvent(event)
