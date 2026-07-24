"""Comic-Reader-Fenster.

Die Ausstattung orientiert sich an MComix und YACReader, den beiden
verbreiteten Lesern: Doppelseite mit einzelner Titelseite, Manga-Richtung,
Lupe, Miniaturleiste, Lesezeichen, gemerkter Lesestand und Sprung ins
naechste Heft des Ordners.

Aufbau: `PageView` zeigt genau ein fertig zusammengesetztes Bild - ob das
eine Seite ist oder eine Doppelseite, entscheidet das Fenster. Dekodiert
wird im Threadpool, Nachbarseiten werden vorausgeladen; ueber Netzlaufwerke
ist das Entpacken sonst deutlich zu spueren.
"""
from __future__ import annotations

import time
from pathlib import Path

from PySide6.QtCore import (
    QObject, QPoint, QRect, QRunnable, QSettings, QSize, Qt, QThreadPool,
    QTimer, Signal, Slot,
)
from PySide6.QtGui import (
    QAction, QActionGroup, QColor, QImage, QKeySequence, QPainter, QPen,
    QPixmap, QTransform,
)
from PySide6.QtWidgets import (
    QDialog, QDialogButtonBox, QDockWidget, QInputDialog, QLabel,
    QListWidget, QListWidgetItem, QMainWindow, QMessageBox, QScrollArea,
    QSlider, QToolBar, QVBoxLayout, QWidget,
)

from . import archive
from .archive import ComicError, ComicFile, open_comic
from .i18n import _
from .icons import icon as app_icon
from .readstate import reading_state

FIT_PAGE, FIT_WIDTH, FIT_HEIGHT, FIT_ORIGINAL = range(4)

ZOOM_STEP = 1.25
ZOOM_MIN, ZOOM_MAX = 0.1, 8.0
#: Ganze Seiten im Speicher. Eine Seite kostet schnell 20 MB als QImage -
#: mehr als eine Handvoll lohnt nicht.
CACHE_PAGES = 8
#: Seitenverhaeltnis, ab dem eine Seite als Doppelseite gilt und in der
#: Doppelseitenansicht allein steht.
WIDE_RATIO = 1.15
THUMB_WIDTH = 104
THUMB_HEIGHT = 150

BACKGROUNDS = (("Dunkel", "#1b1b1b"), ("Schwarz", "#000000"),
               ("Grau", "#3c3c3c"), ("Hell", "#f2f2f2"))


# --- Hintergrundarbeit -------------------------------------------------
class _PageSignals(QObject):
    loaded = Signal(int, QImage)
    failed = Signal(int, str)
    thumb = Signal(int, QImage)


class _PageJob(QRunnable):
    def __init__(self, comic: ComicFile, index: int, signals: _PageSignals,
                 thumb: bool = False):
        super().__init__()
        self.comic, self.index, self.signals = comic, index, signals
        self.thumb = thumb

    def run(self) -> None:
        try:
            data = self.comic.page_bytes(self.index)
            img = QImage()
            if not img.loadFromData(data):
                raise ComicError(_("Bild konnte nicht dekodiert werden."))
            if self.thumb:
                self.signals.thumb.emit(self.index, img.scaled(
                    THUMB_WIDTH, THUMB_HEIGHT, Qt.KeepAspectRatio,
                    Qt.SmoothTransformation))
            else:
                self.signals.loaded.emit(self.index, img)
        except Exception as exc:  # noqa: BLE001
            self.signals.failed.emit(self.index, str(exc))


class PageCache:
    """Zuletzt benutzte Seiten im Speicher halten."""

    def __init__(self, limit: int = CACHE_PAGES):
        self.limit = limit
        self._items: dict[int, QImage] = {}
        self._order: list[int] = []

    def clear(self) -> None:
        self._items.clear()
        self._order.clear()

    def get(self, index: int) -> QImage | None:
        img = self._items.get(index)
        if img is not None:
            self._order.remove(index)
            self._order.append(index)
        return img

    def put(self, index: int, img: QImage) -> None:
        if index in self._items:
            self._order.remove(index)
        self._items[index] = img
        self._order.append(index)
        while len(self._order) > self.limit:
            del self._items[self._order.pop(0)]


# --- Anzeige -----------------------------------------------------------
class _Canvas(QWidget):
    """Malt die Seite, die Lupe und nimmt Maus-Eingaben entgegen."""

    clicked = Signal(float)     # 0..1: waagerechte Position des Klicks

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMouseTracking(True)
        self.pixmap = QPixmap()          # skaliert, so wie gezeigt
        self.source = QPixmap()          # volle Aufloesung, fuer die Lupe
        self.background = QColor("#1b1b1b")
        self.lens = False
        self.lens_size = 260
        self.lens_zoom = 2.0
        self._cursor = QPoint(-1, -1)
        self._drag_from: QPoint | None = None
        self._moved = False

    # --- Zeichnen -----------------------------------------------------
    def offset(self) -> QPoint:
        """Linke obere Ecke der Seite - sie sitzt mittig auf der Flaeche."""
        return QPoint(max(0, (self.width() - self.pixmap.width()) // 2),
                      max(0, (self.height() - self.pixmap.height()) // 2))

    def paintEvent(self, event):  # noqa: N802
        painter = QPainter(self)
        painter.fillRect(self.rect(), self.background)
        if self.pixmap.isNull():
            return
        painter.drawPixmap(self.offset(), self.pixmap)
        if self.lens and self.rect().contains(self._cursor):
            self._paint_lens(painter)

    def _paint_lens(self, painter: QPainter) -> None:
        if self.source.isNull() or not self.pixmap.width():
            return
        auf_seite = self._cursor - self.offset()
        if not self.pixmap.rect().contains(auf_seite):
            return
        faktor = self.source.width() / self.pixmap.width()
        # Ausschnitt in Originalpunkten, damit die Lupe echte Aufloesung
        # zeigt statt das bereits verkleinerte Bild noch einmal zu strecken.
        seite = max(8, int(self.lens_size / self.lens_zoom * faktor))
        mitte = QPoint(int(auf_seite.x() * faktor), int(auf_seite.y() * faktor))
        quelle = QRect(mitte.x() - seite // 2, mitte.y() - seite // 2,
                       seite, seite)
        quelle = quelle.intersected(self.source.rect())
        if quelle.isEmpty():
            return
        ziel = QRect(0, 0, self.lens_size, self.lens_size)
        ziel.moveCenter(self._cursor)
        painter.setRenderHint(QPainter.SmoothPixmapTransform)
        painter.fillRect(ziel, self.background)
        painter.drawPixmap(ziel, self.source, quelle)
        painter.setPen(QPen(QColor(255, 255, 255, 190), 2))
        painter.drawRect(ziel.adjusted(0, 0, -1, -1))

    # --- Maus ---------------------------------------------------------
    def mousePressEvent(self, event):  # noqa: N802
        if event.button() == Qt.LeftButton:
            self._drag_from = event.position().toPoint()
            self._moved = False
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):  # noqa: N802
        pos = event.position().toPoint()
        if self.lens:
            self._cursor = pos
            self.update()
        if self._drag_from is not None and event.buttons() & Qt.LeftButton:
            delta = pos - self._drag_from
            if not self.lens and (abs(delta.x()) > 2 or abs(delta.y()) > 2):
                self._moved = True
                view = self.parent().parent()
                if isinstance(view, PageView):
                    view.pan(delta)
                    return          # Ziehen verschiebt, der Punkt bleibt
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):  # noqa: N802
        if event.button() == Qt.LeftButton and self._drag_from is not None:
            if not self._moved and not self.lens and self.width():
                self.clicked.emit(event.position().x() / self.width())
            self._drag_from = None
        super().mouseReleaseEvent(event)

    def leaveEvent(self, event):  # noqa: N802
        self._cursor = QPoint(-1, -1)
        if self.lens:
            self.update()
        super().leaveEvent(event)


class PageView(QScrollArea):
    """Skaliert die Seite nach Anpassung und Zoom, verschiebt per Ziehen."""

    clicked = Signal(float)
    #: Rad ohne Strg am Ende des Rollwegs: umblaettern (True = vorwaerts).
    flipped = Signal(bool)
    #: Rad mit Strg: zoomen. Richtung und Punkt unter dem Zeiger.
    zoomed = Signal(int, QPoint)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.canvas = _Canvas()
        self.canvas.clicked.connect(self.clicked)
        self.setWidget(self.canvas)
        self.setWidgetResizable(False)
        self.setAlignment(Qt.AlignCenter)
        self.setFrameShape(QScrollArea.NoFrame)
        self.fit_mode = FIT_PAGE
        self.zoom = 1.0
        self.rotation = 0
        self._source = QPixmap()
        self._scaled_for: tuple | None = None

    # ------------------------------------------------------------------
    def set_background(self, color: str) -> None:
        self.canvas.background = QColor(color)
        self.viewport().setStyleSheet(f"background:{color};")
        self.canvas.update()

    def set_page(self, pixmap: QPixmap, keep_position: bool = False) -> None:
        self._source = pixmap
        self.rescale()
        if not keep_position:
            self.verticalScrollBar().setValue(0)
            self.horizontalScrollBar().setValue(
                self.horizontalScrollBar().maximum() // 2)

    def set_fit(self, mode: int) -> None:
        self.fit_mode = mode
        self.zoom = 1.0
        self.rescale()

    def set_zoom(self, zoom: float, anchor: QPoint | None = None) -> None:
        zoom = max(ZOOM_MIN, min(ZOOM_MAX, zoom))
        if abs(zoom - self.zoom) < 0.001:
            return
        alt = self.canvas.size()
        self.zoom = zoom
        self.rescale()
        self._keep_anchor(alt, anchor)

    def _keep_anchor(self, alt: QSize, anchor: QPoint | None) -> None:
        """Nach dem Zoomen soll der Punkt unter dem Zeiger dort bleiben."""
        if anchor is None or not alt.width() or not alt.height():
            return
        neu = self.canvas.size()
        hbar, vbar = self.horizontalScrollBar(), self.verticalScrollBar()
        x = (hbar.value() + anchor.x()) * neu.width() / alt.width()
        y = (vbar.value() + anchor.y()) * neu.height() / alt.height()
        hbar.setValue(int(x - anchor.x()))
        vbar.setValue(int(y - anchor.y()))

    def set_rotation(self, grad: int) -> None:
        self.rotation = grad % 360
        self.rescale()

    # ------------------------------------------------------------------
    def _rotated(self) -> QPixmap:
        if self._source.isNull() or not self.rotation:
            return self._source
        return self._source.transformed(QTransform().rotate(self.rotation),
                                        Qt.SmoothTransformation)

    def rescale(self) -> None:
        quelle = self._rotated()
        self.canvas.source = quelle
        if quelle.isNull():
            self.canvas.pixmap = QPixmap()
            self.canvas.resize(self.viewport().size())
            self.canvas.update()
            return
        einzeln = self.fit_mode == FIT_PAGE
        self.setHorizontalScrollBarPolicy(
            Qt.ScrollBarAlwaysOff if einzeln else Qt.ScrollBarAsNeeded)
        self.setVerticalScrollBarPolicy(
            Qt.ScrollBarAlwaysOff if einzeln else Qt.ScrollBarAsNeeded)
        vp = self.viewport().size()
        breite, hoehe = quelle.width(), quelle.height()
        if self.fit_mode == FIT_PAGE:
            faktor = min(vp.width() / breite, vp.height() / hoehe)
        elif self.fit_mode == FIT_WIDTH:
            faktor = vp.width() / breite
        elif self.fit_mode == FIT_HEIGHT:
            faktor = vp.height() / hoehe
        else:
            faktor = 1.0
        faktor *= self.zoom
        ziel = QSize(max(1, int(breite * faktor)), max(1, int(hoehe * faktor)))
        marke = (quelle.cacheKey(), ziel.width(), ziel.height())
        if marke != self._scaled_for:
            self.canvas.pixmap = quelle.scaled(ziel, Qt.IgnoreAspectRatio,
                                               Qt.SmoothTransformation)
            self._scaled_for = marke
        self.canvas.resize(ziel.expandedTo(self.viewport().size()))
        self.canvas.update()

    def pan(self, delta: QPoint) -> None:
        self.horizontalScrollBar().setValue(
            self.horizontalScrollBar().value() - delta.x())
        self.verticalScrollBar().setValue(
            self.verticalScrollBar().value() - delta.y())

    def scroll_step(self, forward: bool) -> bool:
        """Ein Stueck weiterrollen. False, wenn schon am Ende."""
        bar = self.verticalScrollBar()
        if bar.maximum() == 0:
            return False
        if forward and bar.value() >= bar.maximum():
            return False
        if not forward and bar.value() <= 0:
            return False
        schritt = max(40, int(self.viewport().height() * 0.9))
        bar.setValue(bar.value() + (schritt if forward else -schritt))
        return True

    def wheelEvent(self, event):  # noqa: N802
        delta = event.angleDelta().y()
        if not delta:
            super().wheelEvent(event)
            return
        if event.modifiers() & Qt.ControlModifier:
            self.zoomed.emit(delta, self.canvas.mapFrom(self,
                                                        event.position().toPoint()))
            event.accept()
            return
        bar = self.verticalScrollBar()
        am_ende = (bar.value() >= bar.maximum() if delta < 0
                   else bar.value() <= bar.minimum())
        if am_ende:
            # Ganze Seite hat keinen Rollweg - dann blaettert das Rad sofort.
            self.flipped.emit(delta < 0)
            event.accept()
            return
        super().wheelEvent(event)

    def resizeEvent(self, event):  # noqa: N802
        super().resizeEvent(event)
        self.rescale()


# --- Fenster -----------------------------------------------------------
class ReaderWindow(QMainWindow):
    closed = Signal(str)
    #: Der Reader hat auf ein anderes Heft gewechselt (alt, neu).
    retitled = Signal(str, str)

    def __init__(self, path: Path, parent=None):
        super().__init__(parent)
        self.path = Path(path)
        self.comic: ComicFile | None = None
        self.index = 0
        self.pages: list[int] = []
        self.settings = QSettings("comicdesk", "comicdesk")
        self.state = reading_state()
        self.cache = PageCache()
        self._images: dict[int, QImage] = {}
        self._aspect: dict[int, float] = {}
        self._end_hint = 0.0

        self._pool = QThreadPool(self)
        self._pool.setMaxThreadCount(2)
        self._signals = _PageSignals(self)
        self._signals.loaded.connect(self._on_page)
        self._signals.failed.connect(self._on_fail)
        self._signals.thumb.connect(self._on_thumb)

        self.resize(1000, 1300)
        self.view = PageView(self)
        self.view.clicked.connect(self._on_click)
        self.view.flipped.connect(
            lambda vor: self.next_page() if vor else self.prev_page())
        self.view.zoomed.connect(self._on_wheel_zoom)
        self.setCentralWidget(self.view)

        self._build_thumbs()
        self._build_actions()
        self._build_status()
        self._restore_settings()

        if not self._load(self.path, first=True):
            return
        self._resume()

    # --- Aufbau -------------------------------------------------------
    def _build_thumbs(self) -> None:
        self.thumbs = QListWidget()
        self.thumbs.setIconSize(QSize(THUMB_WIDTH, THUMB_HEIGHT))
        self.thumbs.setUniformItemSizes(True)
        self.thumbs.setSpacing(2)
        # Bild oben, Seitenzahl darunter - in der Listenansicht saesse die
        # Zahl neben dem Bild und die Spalte waere doppelt so breit.
        self.thumbs.setViewMode(QListWidget.IconMode)
        self.thumbs.setFlow(QListWidget.TopToBottom)
        self.thumbs.setWrapping(False)
        self.thumbs.setMovement(QListWidget.Static)
        self.thumbs.setResizeMode(QListWidget.Adjust)
        self.thumbs.setGridSize(QSize(THUMB_WIDTH + 12, THUMB_HEIGHT + 30))
        self.thumbs.setFixedWidth(THUMB_WIDTH + 34)
        self.thumbs.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.thumbs.currentRowChanged.connect(self._on_thumb_row)
        self.dock = QDockWidget(_("Seiten"), self)
        self.dock.setObjectName("thumbs")
        self.dock.setWidget(self.thumbs)
        self.dock.setAllowedAreas(Qt.LeftDockWidgetArea | Qt.RightDockWidgetArea)
        self.addDockWidget(Qt.LeftDockWidgetArea, self.dock)
        self.dock.hide()
        # Nur die sichtbaren Miniaturen erzeugen - ein Heft kann 200 Seiten
        # haben, und jede kostet einen Entpackvorgang.
        self._thumb_timer = QTimer(self)
        self._thumb_timer.setInterval(150)
        self._thumb_timer.setSingleShot(True)
        self._thumb_timer.timeout.connect(self._fill_visible_thumbs)
        self.thumbs.verticalScrollBar().valueChanged.connect(
            lambda _v: self._thumb_timer.start())
        self._thumb_wanted: set[int] = set()

    def _act(self, text, shortcuts, slot, checkable=False, icon=None):
        action = QAction(_(text), self)
        if shortcuts:
            action.setShortcuts([QKeySequence(s) for s in shortcuts])
        action.triggered.connect(slot)
        action.setCheckable(checkable)
        if icon:
            action.setIcon(app_icon(icon))
        self.addAction(action)
        return action

    def _build_actions(self) -> None:
        bar = self.menuBar()
        tb = QToolBar(_("Reader"))
        tb.setMovable(False)
        tb.setObjectName("readertools")
        self.addToolBar(tb)
        self.toolbar = tb

        # --- Blaettern
        self.a_prev = self._act("◀ Zurueck", ["Left", "PgUp", "Backspace"],
                                self.prev_page, icon="left")
        self.a_next = self._act("Weiter ▶", ["Right", "PgDown"],
                                self.next_page, icon="right")
        a_first = self._act("Erste Seite", ["Home"], lambda: self.go_to(0),
                            icon="first")
        a_last = self._act("Letzte Seite", ["End"], self.go_last, icon="last")
        a_goto = self._act("Gehe zu Seite …", ["Ctrl+G"], self.go_to_dialog,
                           icon="goto")
        # Leertaste rollt weiter und blaettert erst am Fuss der Seite um.
        self._act("Weiterrollen", ["Space"], lambda: self.smart_scroll(True))
        self._act("Zurueckrollen", ["Shift+Space"],
                  lambda: self.smart_scroll(False))
        a_next_comic = self._act("Naechstes Heft", ["N"],
                                 lambda: self.open_sibling(1))
        a_prev_comic = self._act("Voriges Heft", ["P"],
                                 lambda: self.open_sibling(-1))

        # --- Ansicht
        self.a_fit = {
            FIT_PAGE: self._act("Ganze Seite", ["1"],
                                lambda: self.set_fit(FIT_PAGE), True, "fit_page"),
            FIT_WIDTH: self._act("Breite", ["2"],
                                 lambda: self.set_fit(FIT_WIDTH), True, "fit_width"),
            FIT_HEIGHT: self._act("Höhe", ["3"],
                                  lambda: self.set_fit(FIT_HEIGHT), True,
                                  "fit_height"),
            FIT_ORIGINAL: self._act("100 %", ["4"],
                                    lambda: self.set_fit(FIT_ORIGINAL), True),
        }
        gruppe = QActionGroup(self)
        for action in self.a_fit.values():
            gruppe.addAction(action)
        self.a_fit[FIT_PAGE].setChecked(True)
        a_zoom_in = self._act("Vergrössern", ["+", "="],
                              lambda: self.zoom_by(ZOOM_STEP), icon="zoom_in")
        a_zoom_out = self._act("Verkleinern", ["-"],
                               lambda: self.zoom_by(1 / ZOOM_STEP),
                               icon="zoom_out")
        a_zoom_reset = self._act("Zoom zurücksetzen", ["0"], self.zoom_reset)

        self.a_double = self._act("Doppelseite", ["D"], self.toggle_double,
                                  True, "double")
        self.a_cover = self._act("Titelseite einzeln", None,
                                 self.toggle_cover_single, True)
        self.a_manga = self._act("Mangamodus (rechts nach links)", ["M"],
                                 self.toggle_manga, True, "manga")
        a_rot_right = self._act("Nach rechts drehen", ["R"],
                                lambda: self.rotate(90), icon="rotate")
        a_rot_left = self._act("Nach links drehen", ["Shift+R"],
                               lambda: self.rotate(-90))
        self.a_lens = self._act("Lupe", ["L"], self.toggle_lens, True, "lens")
        a_lens_more = self._act("Lupe stärker", ["Ctrl++"],
                                lambda: self.lens_zoom_by(0.5))
        a_lens_less = self._act("Lupe schwächer", ["Ctrl+-"],
                                lambda: self.lens_zoom_by(-0.5))
        self.a_thumbs = self._act("Miniaturen", ["F9"], self.toggle_thumbs,
                                  True, "thumbs")
        self.a_full = self._act("Vollbild", ["F11"], self.toggle_fullscreen,
                                True, "fullscreen")

        # --- Lesezeichen
        self.a_mark = self._act("Lesezeichen setzen", ["Ctrl+D"],
                                self.toggle_bookmark, True, "bookmark")
        a_marks = self._act("Lesezeichen …", ["Ctrl+B"], self.show_bookmarks)

        a_pages = self._act("Seiten verwalten", ["Ctrl+P"], self.manage_pages,
                            icon="pages")
        self._act("Schliessen", ["Esc", "Ctrl+W"], self.close)

        # --- Menues
        m_datei = bar.addMenu(_("Datei"))
        m_datei.addAction(a_next_comic)
        m_datei.addAction(a_prev_comic)
        m_datei.addSeparator()
        m_datei.addAction(a_pages)

        m_ansicht = bar.addMenu(_("Ansicht"))
        for action in self.a_fit.values():
            m_ansicht.addAction(action)
        m_ansicht.addSeparator()
        m_ansicht.addAction(a_zoom_in)
        m_ansicht.addAction(a_zoom_out)
        m_ansicht.addAction(a_zoom_reset)
        m_ansicht.addSeparator()
        m_ansicht.addAction(self.a_double)
        m_ansicht.addAction(self.a_cover)
        m_ansicht.addAction(self.a_manga)
        m_ansicht.addSeparator()
        m_ansicht.addAction(a_rot_right)
        m_ansicht.addAction(a_rot_left)
        m_ansicht.addSeparator()
        m_ansicht.addAction(self.a_lens)
        m_ansicht.addAction(a_lens_more)
        m_ansicht.addAction(a_lens_less)
        m_ansicht.addSeparator()
        m_hintergrund = m_ansicht.addMenu(_("Hintergrund"))
        self.bg_group = QActionGroup(self)
        for name, farbe in BACKGROUNDS:
            action = QAction(_(name), self, checkable=True)
            action.triggered.connect(lambda _c, f=farbe: self.set_background(f))
            action.setData(farbe)
            self.bg_group.addAction(action)
            m_hintergrund.addAction(action)
        m_ansicht.addSeparator()
        m_ansicht.addAction(self.a_thumbs)
        m_ansicht.addAction(self.a_full)

        m_gehe = bar.addMenu(_("Navigation"))
        for action in (self.a_prev, self.a_next, a_first, a_last, a_goto):
            m_gehe.addAction(action)

        self.m_marks = bar.addMenu(_("Lesezeichen"))
        self.m_marks.addAction(self.a_mark)
        self.m_marks.addAction(a_marks)

        # --- Werkzeugleiste
        for action in (self.a_prev, self.a_next, None, a_first, a_last, a_goto,
                       None, self.a_fit[FIT_PAGE], self.a_fit[FIT_WIDTH],
                       self.a_fit[FIT_HEIGHT], a_zoom_out, a_zoom_in, None,
                       self.a_double, self.a_manga, a_rot_right, self.a_lens,
                       None, self.a_mark, self.a_thumbs, self.a_full):
            tb.addSeparator() if action is None else tb.addAction(action)

    def _build_status(self) -> None:
        self.slider = QSlider(Qt.Horizontal)
        self.slider.setMaximumWidth(320)
        self.slider.setPageStep(1)
        self.slider.setTracking(False)
        self.slider.valueChanged.connect(self._on_slider)
        self.page_label = QLabel()
        self.statusBar().addPermanentWidget(self.page_label)
        self.statusBar().addPermanentWidget(self.slider)

    def _restore_settings(self) -> None:
        s = self.settings
        modus = int(s.value("reader/fit", FIT_PAGE))
        self.view.fit_mode = modus if modus in self.a_fit else FIT_PAGE
        self.a_fit[self.view.fit_mode].setChecked(True)
        self.double = s.value("reader/double", False, type=bool)
        self.cover_single = s.value("reader/cover_single", True, type=bool)
        self.manga = s.value("reader/manga", False, type=bool)
        self.a_double.setChecked(self.double)
        self.a_cover.setChecked(self.cover_single)
        self.a_manga.setChecked(self.manga)
        farbe = str(s.value("reader/background", BACKGROUNDS[0][1]))
        self.set_background(farbe)
        self.view.canvas.lens_zoom = float(s.value("reader/lens_zoom", 2.0))
        if s.value("reader/thumbs", False, type=bool):
            self.a_thumbs.setChecked(True)
            self.dock.show()

    def _save_settings(self) -> None:
        s = self.settings
        s.setValue("reader/fit", self.view.fit_mode)
        s.setValue("reader/double", self.double)
        s.setValue("reader/cover_single", self.cover_single)
        s.setValue("reader/manga", self.manga)
        s.setValue("reader/thumbs", self.dock.isVisible())
        s.setValue("reader/lens_zoom", self.view.canvas.lens_zoom)

    # --- Datei --------------------------------------------------------
    def _load(self, path: Path, first: bool = False) -> bool:
        """Heft oeffnen. False, wenn das Fenster deshalb schliesst."""
        alt = self.comic
        try:
            comic = open_comic(path)
            if comic.page_count == 0:
                raise ComicError(_("Keine Seiten gefunden."))
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(self, _("Fehler"), str(exc))
            if first:
                QTimer.singleShot(0, self.close)
                return False
            return False
        if alt is not None:
            alt.close()
        self.comic = comic
        self.path = Path(path)
        self.setWindowTitle(self.path.name)
        self.cache.clear()
        self._images.clear()
        self._aspect.clear()
        self.index = 0
        self._end_hint = 0.0
        # Zoom und Drehung galten dem alten Heft, nicht dem neuen.
        self.view.zoom = 1.0
        self.view.rotation = 0
        self.slider.blockSignals(True)
        self.slider.setRange(1, comic.page_count)
        self.slider.blockSignals(False)
        self._fill_thumb_list()
        return True

    def _resume(self) -> None:
        """Beim letzten Stand weiterlesen, sofern es einen gibt."""
        eintrag = self.state.get(self.path)
        start = 0
        if 0 < eintrag.page < (self.comic.page_count if self.comic else 0):
            if not eintrag.finished:
                start = eintrag.page
                self.statusBar().showMessage(
                    _("Weiter auf Seite {page}.").format(page=start + 1), 4000)
        self.go_to(start)

    def _siblings(self) -> list[Path]:
        try:
            entries = [p for p in self.path.parent.iterdir()
                       if p.is_file() and archive.is_comic(p)]
        except OSError:
            return []
        return sorted(entries, key=lambda p: archive.natural_key(p.name))

    def _neighbour(self, delta: int) -> Path | None:
        geschwister = self._siblings()
        try:
            pos = geschwister.index(self.path)
        except ValueError:
            return None
        ziel = pos + delta
        return geschwister[ziel] if 0 <= ziel < len(geschwister) else None

    def open_sibling(self, delta: int) -> None:
        ziel = self._neighbour(delta)
        if ziel is None:
            self.statusBar().showMessage(
                _("Kein weiteres Heft in diesem Ordner."), 4000)
            return
        alt = str(self.path)
        self._pool.clear()
        if self._load(ziel):
            self.retitled.emit(alt, str(self.path))
            self._resume()

    # --- Seitenauswahl ------------------------------------------------
    def _is_wide(self, index: int) -> bool:
        verhaeltnis = self._aspect.get(index)
        return verhaeltnis is not None and verhaeltnis > WIDE_RATIO

    def _spread(self, index: int) -> list[int]:
        """Welche Seiten gehoeren bei dieser Position zusammen?"""
        if not self.comic:
            return []
        if not self.double:
            return [index]
        if index == 0 and self.cover_single:
            return [0]
        zweite = index + 1
        if zweite >= self.comic.page_count:
            return [index]
        if self._is_wide(index) or self._is_wide(zweite):
            return [index]
        return [index, zweite]

    def go_to(self, index: int) -> None:
        if not self.comic:
            return
        index = max(0, min(index, self.comic.page_count - 1))
        self.index = index
        self.pages = self._spread(index)
        self._images = {}
        for seite in self.pages:
            zwischen = self.cache.get(seite)
            if zwischen is not None:
                self._images[seite] = zwischen
            else:
                self._pool.start(_PageJob(self.comic, seite, self._signals))
        self._update_status()
        self.state.set_page(self.path, index, self.comic.page_count)
        if len(self._images) == len(self.pages):
            self._compose()
        self._prefetch()

    def _prefetch(self) -> None:
        if not self.comic:
            return
        voraus = [p for p in range(self.index + len(self.pages),
                                   self.index + len(self.pages) + 2)
                  if p < self.comic.page_count]
        zurueck = [self.index - 1] if self.index > 0 else []
        for seite in voraus + zurueck:
            if self.cache.get(seite) is None and seite not in self._images:
                self._pool.start(_PageJob(self.comic, seite, self._signals))

    def next_page(self) -> None:
        if not self.comic:
            return
        weiter = self.index + len(self.pages or [self.index])
        if weiter >= self.comic.page_count:
            self._at_end()
            return
        self.go_to(weiter)

    def prev_page(self) -> None:
        if self.index <= 0:
            return
        ziel = self.index - (2 if self.double else 1)
        if self.double and self.cover_single and ziel < 1:
            ziel = 0
        self.go_to(max(0, ziel))

    def go_last(self) -> None:
        if self.comic:
            self.go_to(self.comic.page_count - 1)

    def _at_end(self) -> None:
        """Am Ende nicht einfach weiterspringen - erst fragen, dann gehen."""
        naechstes = self._neighbour(1)
        if naechstes is None:
            self.statusBar().showMessage(_("Letzte Seite."), 3000)
            return
        if time.monotonic() - self._end_hint < 4.0:
            self.open_sibling(1)
            return
        self._end_hint = time.monotonic()
        self.statusBar().showMessage(
            _("Ende – nochmal blättern öffnet „{name}“.").format(
                name=naechstes.name), 4000)

    def smart_scroll(self, forward: bool) -> None:
        if self.view.scroll_step(forward):
            return
        self.next_page() if forward else self.prev_page()

    def go_to_dialog(self) -> None:
        if not self.comic:
            return
        nummer, ok = QInputDialog.getInt(
            self, _("Gehe zu Seite"), _("Seite:"), self.index + 1, 1,
            self.comic.page_count)
        if ok:
            self.go_to(nummer - 1)

    def _on_click(self, anteil: float) -> None:
        """Klick in die linke oder rechte Haelfte blaettert."""
        vor = anteil > 0.5
        if self.manga:
            vor = not vor
        self.next_page() if vor else self.prev_page()

    # --- Seiten kommen an ---------------------------------------------
    @Slot(int, QImage)
    def _on_page(self, index: int, img: QImage) -> None:
        if img.height():
            self._aspect[index] = img.width() / img.height()
        self.cache.put(index, img)
        if index not in self.pages:
            return              # war nur Vorausladen
        # Eine Doppelseite steht allein - die Aufteilung kann sich also
        # erst jetzt herausstellen, wo die Groesse bekannt ist.
        neu = self._spread(self.index)
        if neu != self.pages:
            self.pages = neu
            self._images = {p: i for p, i in self._images.items() if p in neu}
            self._update_status()
        self._images[index] = img
        if all(p in self._images for p in self.pages):
            self._compose()

    def _compose(self) -> None:
        bilder = [self._images[p] for p in self.pages if p in self._images]
        if not bilder:
            return
        if len(bilder) == 2 and self.manga:
            bilder.reverse()
        if len(bilder) == 1:
            fertig = QPixmap.fromImage(bilder[0])
        else:
            hoehe = max(b.height() for b in bilder)
            skaliert = [b if b.height() == hoehe else
                        b.scaledToHeight(hoehe, Qt.SmoothTransformation)
                        for b in bilder]
            breite = sum(b.width() for b in skaliert)
            fertig = QPixmap(breite, hoehe)
            fertig.fill(self.view.canvas.background)
            maler = QPainter(fertig)
            x = 0
            for bild in skaliert:
                maler.drawImage(x, 0, bild)
                x += bild.width()
            maler.end()
        self.view.set_page(fertig)

    @Slot(int, str)
    def _on_fail(self, index: int, msg: str) -> None:
        if index in self.pages:
            self.statusBar().showMessage(
                _("Seite {index} konnte nicht geladen werden: {error}").format(
                    index=index + 1, error=msg), 8000)

    # --- Ansicht ------------------------------------------------------
    def set_fit(self, mode: int) -> None:
        self.view.set_fit(mode)
        self.a_fit[mode].setChecked(True)
        self._update_status()

    def zoom_by(self, faktor: float) -> None:
        self.view.set_zoom(self.view.zoom * faktor)
        self._update_status()

    def zoom_reset(self) -> None:
        self.view.set_zoom(1.0)
        self._update_status()

    def rotate(self, grad: int) -> None:
        self.view.set_rotation(self.view.rotation + grad)

    def set_background(self, farbe: str) -> None:
        self.view.set_background(farbe)
        self.settings.setValue("reader/background", farbe)
        for action in self.bg_group.actions():
            action.setChecked(action.data() == farbe)

    def toggle_double(self) -> None:
        self.double = self.a_double.isChecked()
        self.go_to(self.index)

    def toggle_cover_single(self) -> None:
        self.cover_single = self.a_cover.isChecked()
        self.go_to(self.index)

    def toggle_manga(self) -> None:
        self.manga = self.a_manga.isChecked()
        self.go_to(self.index)

    def toggle_lens(self) -> None:
        self.view.canvas.lens = self.a_lens.isChecked()
        self.view.canvas.setCursor(
            Qt.CrossCursor if self.a_lens.isChecked() else Qt.ArrowCursor)
        self.view.canvas.update()

    def lens_zoom_by(self, schritt: float) -> None:
        canvas = self.view.canvas
        canvas.lens_zoom = max(1.5, min(8.0, canvas.lens_zoom + schritt))
        canvas.update()
        self.statusBar().showMessage(
            _("Lupe {factor}×").format(factor=round(canvas.lens_zoom, 1)), 2000)

    def toggle_fullscreen(self) -> None:
        if self.isFullScreen():
            self.showNormal()
            self.menuBar().show()
            self.toolbar.show()
            self.statusBar().show()
        else:
            # Im Vollbild soll die Seite den Schirm haben, nicht die Leisten.
            self.menuBar().hide()
            self.toolbar.hide()
            self.statusBar().hide()
            self.showFullScreen()
        self.a_full.setChecked(self.isFullScreen())

    # --- Miniaturen ---------------------------------------------------
    def toggle_thumbs(self) -> None:
        self.dock.setVisible(self.a_thumbs.isChecked())
        if self.dock.isVisible():
            self.thumbs.setCurrentRow(self.index)
            self._thumb_timer.start()

    def _fill_thumb_list(self) -> None:
        self.thumbs.blockSignals(True)
        self.thumbs.clear()
        self._thumb_wanted.clear()
        for seite in range(self.comic.page_count if self.comic else 0):
            item = QListWidgetItem(str(seite + 1))
            item.setTextAlignment(Qt.AlignCenter)
            item.setSizeHint(QSize(THUMB_WIDTH + 12, THUMB_HEIGHT + 26))
            self.thumbs.addItem(item)
        self.thumbs.blockSignals(False)
        if self.dock.isVisible():
            self._thumb_timer.start()

    def _fill_visible_thumbs(self) -> None:
        if not self.comic or not self.dock.isVisible():
            return
        bereich = self.thumbs.viewport().rect()
        erste = self.thumbs.indexAt(bereich.topLeft()).row()
        letzte = self.thumbs.indexAt(bereich.bottomLeft()).row()
        if erste < 0:
            erste = 0
        if letzte < 0:
            letzte = min(self.thumbs.count() - 1, erste + 12)
        for row in range(erste, letzte + 2):
            item = self.thumbs.item(row)
            if item is None or not item.icon().isNull():
                continue
            if row in self._thumb_wanted:
                continue
            self._thumb_wanted.add(row)
            self._pool.start(_PageJob(self.comic, row, self._signals, thumb=True))

    @Slot(int, QImage)
    def _on_thumb(self, index: int, img: QImage) -> None:
        item = self.thumbs.item(index)
        if item is not None:
            item.setIcon(QPixmap.fromImage(img))

    def _on_thumb_row(self, row: int) -> None:
        if row >= 0 and row != self.index and row not in self.pages:
            self.go_to(row)

    # --- Lesezeichen --------------------------------------------------
    def toggle_bookmark(self) -> None:
        gesetzt = self.state.toggle_bookmark(self.path, self.index)
        self.a_mark.setChecked(gesetzt)
        self.statusBar().showMessage(
            _("Lesezeichen auf Seite {page} gesetzt.").format(page=self.index + 1)
            if gesetzt else
            _("Lesezeichen auf Seite {page} entfernt.").format(page=self.index + 1),
            3000)

    def show_bookmarks(self) -> None:
        marken = self.state.get(self.path).bookmarks
        if not marken:
            self.statusBar().showMessage(
                _("Keine Lesezeichen in diesem Heft."), 3000)
            return
        dialog = QDialog(self)
        dialog.setWindowTitle(_("Lesezeichen"))
        layout = QVBoxLayout(dialog)
        liste = QListWidget()
        for seite in marken:
            liste.addItem(_("Seite {page}").format(page=seite + 1))
        layout.addWidget(liste)
        knoepfe = QDialogButtonBox(QDialogButtonBox.Open | QDialogButtonBox.Close)
        knoepfe.accepted.connect(dialog.accept)
        knoepfe.rejected.connect(dialog.reject)
        liste.doubleClicked.connect(lambda _i: dialog.accept())
        layout.addWidget(knoepfe)
        liste.setCurrentRow(0)
        if dialog.exec() and liste.currentRow() >= 0:
            self.go_to(marken[liste.currentRow()])

    # --- Anzeigepflege ------------------------------------------------
    def _update_status(self) -> None:
        if not self.comic:
            return
        gesamt = self.comic.page_count
        if len(self.pages) == 2:
            nummer = _("{first}–{second}").format(first=self.pages[0] + 1,
                                                  second=self.pages[1] + 1)
        else:
            nummer = str(self.index + 1)
        eintrag = self.state.get(self.path)
        self.a_mark.setChecked(self.index in eintrag.bookmarks)
        teile = [_("Seite {index} / {total}").format(index=nummer, total=gesamt)]
        if abs(self.view.zoom - 1.0) > 0.01:
            teile.append(f"{round(self.view.zoom * 100)} %")
        if self.manga:
            teile.append(_("Manga"))
        self.page_label.setText("  ·  ".join(teile))
        self.slider.blockSignals(True)
        self.slider.setValue(self.index + 1)
        self.slider.blockSignals(False)
        if self.dock.isVisible():
            self.thumbs.blockSignals(True)
            self.thumbs.setCurrentRow(self.index)
            self.thumbs.blockSignals(False)
            self._thumb_timer.start()

    def _on_slider(self, wert: int) -> None:
        if wert - 1 != self.index:
            self.go_to(wert - 1)

    # --- Sonstiges ----------------------------------------------------
    def manage_pages(self) -> None:
        """Seiteneditor oeffnen. Das Archiv muss dafuer freigegeben werden."""
        from .pageeditor import PageEditorDialog

        path, parent = self.path, self.parent()
        self.close()
        dialog = PageEditorDialog(path, parent)
        if parent is not None and hasattr(parent, "_on_pages_changed"):
            dialog.changed.connect(parent._on_pages_changed)
        dialog.exec()

    def _on_wheel_zoom(self, delta: int, anker: QPoint) -> None:
        self.view.set_zoom(self.view.zoom * (ZOOM_STEP if delta > 0
                                             else 1 / ZOOM_STEP), anker)
        self._update_status()

    def closeEvent(self, event):  # noqa: N802
        self._save_settings()
        if self.comic:
            self.state.set_page(self.path, self.index, self.comic.page_count)
        self.state.save(force=True)
        self._pool.clear()
        self._pool.waitForDone(2000)
        if self.comic:
            self.comic.close()
            self.comic = None
        self.closed.emit(str(self.path))
        super().closeEvent(event)
