"""Comic-Reader-Fenster."""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QSettings

from PySide6.QtCore import (
    QObject, QRunnable, Qt, QThread, QThreadPool, Signal, Slot,
)
from PySide6.QtGui import (
    QAction, QColor, QFont, QImage, QKeySequence, QPainter, QPen, QPixmap,
)
from PySide6.QtWidgets import (
    QLabel, QMainWindow, QMessageBox, QScrollArea, QSizePolicy, QSplitter,
    QTextBrowser, QToolBar, QVBoxLayout, QWidget,
)

from .archive import ComicError, ComicFile, open_comic
from .background import stop_and_detach
from .config import TranslationSettings
from .translate import PageStore
from .i18n import _

FIT_PAGE, FIT_WIDTH, FIT_ORIGINAL = range(3)


class _PageSignals(QObject):
    loaded = Signal(int, QImage)
    failed = Signal(int, str)


class _PageJob(QRunnable):
    def __init__(self, comic: ComicFile, index: int, signals: _PageSignals):
        super().__init__()
        self.comic, self.index, self.signals = comic, index, signals

    def run(self) -> None:
        try:
            data = self.comic.page_bytes(self.index)
            img = QImage()
            if not img.loadFromData(data):
                raise ComicError(_("Bild konnte nicht dekodiert werden."))
            self.signals.loaded.emit(self.index, img)
        except Exception as exc:  # noqa: BLE001
            self.signals.failed.emit(self.index, str(exc))


class _TranslateWorker(QObject):
    """Eine Seite uebersetzen lassen - im eigenen Thread, damit das Blaettern
    fluessig bleibt."""

    done = Signal(int, object, str)   # Seitenindex, Blasen, Fehlermeldung

    def __init__(self, translator, index: int, data: bytes):
        super().__init__()
        self.translator, self.index, self.data = translator, index, data
        self._stop = False

    def stop(self) -> None:
        self._stop = True

    def run(self) -> None:
        try:
            bubbles = self.translator.page(self.data)
        except Exception as exc:  # noqa: BLE001
            if not self._stop:
                self.done.emit(self.index, None, str(exc))
            return
        if not self._stop:
            self.done.emit(self.index, bubbles, "")


class ReaderWindow(QMainWindow):
    closed = Signal(str)

    def __init__(self, path: Path, parent=None):
        super().__init__(parent)
        self.path = Path(path)
        self.comic: ComicFile | None = None
        self.index = 0
        self.fit_mode = FIT_PAGE
        self._current: QPixmap | None = None
        self._pool = QThreadPool(self)
        self._pool.setMaxThreadCount(2)
        self._signals = _PageSignals(self)
        self._signals.loaded.connect(self._on_page)
        self._signals.failed.connect(self._on_fail)

        self.setWindowTitle(self.path.name)
        self.resize(1000, 1300)

        self.label = QLabel(alignment=Qt.AlignCenter)
        self.label.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Ignored)
        self.label.setStyleSheet("background:#1b1b1b;")
        self.scroll = QScrollArea()
        self.scroll.setWidget(self.label)
        self.scroll.setWidgetResizable(True)
        self.scroll.setAlignment(Qt.AlignCenter)

        self.translation_view = QTextBrowser()
        self.translation_view.setOpenExternalLinks(False)
        side = QWidget()
        side_layout = QVBoxLayout(side)
        side_layout.setContentsMargins(6, 6, 6, 6)
        self.translation_title = QLabel()
        self.translation_title.setStyleSheet("font-weight:600;")
        side_layout.addWidget(self.translation_title)
        side_layout.addWidget(self.translation_view, 1)
        self.translation_side = side
        side.setVisible(False)

        self.split = QSplitter()
        self.split.addWidget(self.scroll)
        self.split.addWidget(side)
        self.split.setStretchFactor(0, 1)
        self.setCentralWidget(self.split)

        self._tr_thread: QThread | None = None
        self._tr_worker: _TranslateWorker | None = None
        #: Uebersetzungen liegen beim Comic, damit sie auf jedem Rechner da
        #: sind. Geschrieben wird beim Schliessen, nicht pro Seite - sonst
        #: wuerde das Archiv jedes Mal neu geschrieben.
        self._store: PageStore | None = None
        #: Blasen der angezeigten Seite - fuer die Nummern auf dem Bild.
        self._bubbles: list = []

        self._build_actions()
        self.statusBar().showMessage(_("Laedt ..."))

        try:
            self.comic = open_comic(self.path)
            if self.comic.page_count == 0:
                raise ComicError(_("Keine Seiten gefunden."))
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(self, _("Fehler"), str(exc))
            self.close()
            return
        self._show_page(0)

    # ------------------------------------------------------------------
    def _build_actions(self) -> None:
        tb = QToolBar(_("Reader"))
        tb.setMovable(False)
        self.addToolBar(tb)

        def act(text, shortcuts, slot, checkable=False):
            a = QAction(_(text), self)
            a.setShortcuts([QKeySequence(s) for s in shortcuts])
            a.triggered.connect(slot)
            a.setCheckable(checkable)
            self.addAction(a)
            return a

        tb.addAction(act("◀ Zurueck", ["Left", "PgUp", "Backspace"], self.prev_page))
        tb.addAction(act("Weiter ▶", ["Right", "PgDown", "Space"], self.next_page))
        tb.addSeparator()
        self.a_page = act("Ganze Seite", ["1"], lambda: self.set_fit(FIT_PAGE), True)
        self.a_width = act("Breite", ["2"], lambda: self.set_fit(FIT_WIDTH), True)
        self.a_orig = act("100 %", ["3"], lambda: self.set_fit(FIT_ORIGINAL), True)
        self.a_page.setChecked(True)
        for a in (self.a_page, self.a_width, self.a_orig):
            tb.addAction(a)
        tb.addSeparator()
        tb.addAction(act("Vollbild", ["F11"], self.toggle_fullscreen))
        tb.addAction(act("Seiten verwalten", ["Ctrl+P"], self.manage_pages))
        self.a_translate = act("Übersetzung", ["T"], self.toggle_translation, True)
        tb.addAction(self.a_translate)
        act("Schliessen", ["Esc", "Ctrl+W"], self.close)
        act("Erste Seite", ["Home"], lambda: self._show_page(0))
        act("Letzte Seite", ["End"],
            lambda: self._show_page((self.comic.page_count - 1) if self.comic else 0))

    def toggle_translation(self) -> None:
        show = self.a_translate.isChecked()
        self.translation_side.setVisible(show)
        if not show:
            self._bubbles = []
            self._rescale()
        if show:
            if self.split.sizes()[1] < 100:
                total = sum(self.split.sizes()) or self.width()
                self.split.setSizes([int(total * 0.62), int(total * 0.38)])
            self._request_translation()
        else:
            self._stop_translation()

    def _stop_translation(self) -> None:
        stop_and_detach(self, self._tr_thread, self._tr_worker)
        self._tr_thread = self._tr_worker = None

    def _request_translation(self) -> None:
        if not self.a_translate.isChecked() or self.comic is None:
            return
        index = self.index
        self.translation_title.setText(
            _("Seite {number}").format(number=index + 1))
        settings = TranslationSettings.load(QSettings("comicdesk", "comicdesk"))
        try:
            data = self.comic.page_bytes(index)
        except Exception as exc:  # noqa: BLE001
            self.translation_view.setPlainText(str(exc))
            return

        if self._store is None:
            self._store = PageStore(self.comic)
        gespeichert = self._store.get(data, settings.language)
        if gespeichert is not None:
            self._show_bubbles(gespeichert)
            return

        translator = settings.build()
        try:
            translator.right_to_left = (
                (self.comic.read_metadata().manga or "").lower()
                == "yesandrighttoleft")
        except Exception:  # noqa: BLE001
            pass
        ok, why = translator.available()
        if not ok:
            self.translation_view.setPlainText(
                why + "\n\n" + _("Einzutragen unter Extras › Einstellungen › "
                                  "Übersetzung."))
            return
        self._pending = (index, data, settings.language)

        self._stop_translation()
        self.translation_view.setPlainText(_("Wird übersetzt …"))
        self._tr_thread = QThread()
        self._tr_worker = _TranslateWorker(translator, index, data)
        self._tr_worker.moveToThread(self._tr_thread)
        self._tr_thread.started.connect(self._tr_worker.run)
        self._tr_worker.done.connect(self._on_translated)
        self._tr_thread.start()

    def _on_translated(self, index: int, bubbles, error: str) -> None:
        if self._tr_thread:
            self._tr_thread.quit()
            self._tr_thread.wait(2000)
        self._tr_thread = self._tr_worker = None
        if error:
            self.translation_view.setPlainText(error)
            return
        pending = getattr(self, "_pending", None)
        if self._store is not None and pending and pending[0] == index:
            self._store.put(pending[1], pending[2], bubbles)
        if index == self.index:
            self._show_bubbles(bubbles)

    def _save_translations(self) -> None:
        """Beim Schliessen einmal schreiben - dabei wird das Archiv neu
        geschrieben, pro Seite waere das viel zu teuer."""
        if self._store is None or not self._store.dirty:
            return
        try:
            self._store.save()
        except Exception as exc:  # noqa: BLE001
            QMessageBox.warning(
                self, _("Übersetzung"),
                _("Übersetzungen konnten nicht beim Comic gespeichert "
                  "werden:\n{error}").format(error=exc))

    def _show_bubbles(self, bubbles) -> None:
        self._bubbles = list(bubbles or [])
        self._rescale()
        if not bubbles:
            self.translation_view.setPlainText(_("Kein Text auf dieser Seite."))
            return
        import html

        rows = []
        for number, bubble in enumerate(bubbles, 1):
            speaker = f" · {html.escape(bubble.speaker)}" if bubble.speaker else ""
            rows.append(
                f"<p style='margin:0 0 2px 0;color:#888;font-size:9pt'>"
                f"{number}. {html.escape(bubble.kind_label)}{speaker}</p>"
                f"<p style='margin:0 0 1px 0;color:#888'>"
                f"{html.escape(bubble.original)}</p>"
                f"<p style='margin:0 0 14px 0;font-size:11pt'>"
                f"<b>{html.escape(bubble.translation)}</b></p>")
        self.translation_view.setHtml("".join(rows))

    def manage_pages(self) -> None:
        """Seiteneditor oeffnen. Das Archiv muss dafuer freigegeben werden."""
        from .pageeditor import PageEditorDialog

        path, parent = self.path, self.parent()
        self.close()
        dialog = PageEditorDialog(path, parent)
        if parent is not None and hasattr(parent, "_on_pages_changed"):
            dialog.changed.connect(parent._on_pages_changed)
        dialog.exec()

    def toggle_fullscreen(self) -> None:
        self.showNormal() if self.isFullScreen() else self.showFullScreen()

    def set_fit(self, mode: int) -> None:
        self.fit_mode = mode
        self.a_page.setChecked(mode == FIT_PAGE)
        self.a_width.setChecked(mode == FIT_WIDTH)
        self.a_orig.setChecked(mode == FIT_ORIGINAL)
        self._rescale()

    # ------------------------------------------------------------------
    def next_page(self) -> None:
        if self.comic and self.index + 1 < self.comic.page_count:
            self._show_page(self.index + 1)

    def prev_page(self) -> None:
        if self.index > 0:
            self._show_page(self.index - 1)

    def _show_page(self, index: int) -> None:
        if not self.comic:
            return
        self.index = index
        self._bubbles = []
        self.statusBar().showMessage(
            _("Seite {index} / {total}  –  {name}").format(
                index=index + 1, total=self.comic.page_count,
                name=self.path.name))
        self._pool.start(_PageJob(self.comic, index, self._signals))
        self._request_translation()

    @Slot(int, QImage)
    def _on_page(self, index: int, img: QImage) -> None:
        if index != self.index:
            return
        self._current = QPixmap.fromImage(img)
        self._rescale()

    @Slot(int, str)
    def _on_fail(self, index: int, msg: str) -> None:
        if index == self.index:
            self.label.setText(
                _("Seite {index} konnte nicht geladen werden:\n{error}").format(
                    index=index + 1, error=msg))

    def _rescale(self) -> None:
        pm = self._current
        if pm is None or pm.isNull():
            return
        vp = self.scroll.viewport().size()
        if self.fit_mode == FIT_PAGE:
            scaled = pm.scaled(vp, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        elif self.fit_mode == FIT_WIDTH:
            scaled = pm.scaledToWidth(max(1, vp.width()), Qt.SmoothTransformation)
        else:
            scaled = pm
        if self._bubbles and self.a_translate.isChecked():
            scaled = self._with_markers(scaled)
        self.label.setPixmap(scaled)
        self.label.resize(scaled.size())
        self.scroll.setWidgetResizable(self.fit_mode == FIT_PAGE)

    def _with_markers(self, pixmap: QPixmap) -> QPixmap:
        """Nummerierte Marker auf die Seite - erst dadurch sagt die Nummer im
        Panel etwas darueber aus, wo der Text steht."""
        marked = QPixmap(pixmap)
        painter = QPainter(marked)
        painter.setRenderHint(QPainter.Antialiasing)
        radius = max(11, round(min(marked.width(), marked.height()) * 0.022))
        font = QFont()
        font.setBold(True)
        font.setPixelSize(round(radius * 1.15))
        painter.setFont(font)
        for number, bubble in enumerate(self._bubbles, 1):
            center = bubble.center
            if center is None:
                continue
            x = round(center[0] / 100 * marked.width())
            y = round(center[1] / 100 * marked.height())
            painter.setPen(QPen(QColor(255, 255, 255, 230), 2))
            painter.setBrush(QColor(20, 20, 30, 210))
            painter.drawEllipse(x - radius, y - radius, radius * 2, radius * 2)
            painter.setPen(QColor(255, 255, 255))
            painter.drawText(x - radius, y - radius, radius * 2, radius * 2,
                             Qt.AlignCenter, str(number))
        painter.end()
        return marked

    def resizeEvent(self, event):  # noqa: N802
        super().resizeEvent(event)
        self._rescale()

    def wheelEvent(self, event):  # noqa: N802
        if event.modifiers() & Qt.ControlModifier:
            self.next_page() if event.angleDelta().y() < 0 else self.prev_page()
            event.accept()
        else:
            super().wheelEvent(event)

    def closeEvent(self, event):  # noqa: N802
        self._stop_translation()
        self._save_translations()
        self._pool.clear()
        self._pool.waitForDone(2000)
        if self.comic:
            self.comic.close()
            self.comic = None
        self.closed.emit(str(self.path))
        super().closeEvent(event)
