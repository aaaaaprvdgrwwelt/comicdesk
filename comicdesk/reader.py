"""Comic-Reader-Fenster."""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QObject, QRunnable, Qt, QThreadPool, Signal, Slot
from PySide6.QtGui import QAction, QImage, QKeySequence, QPixmap
from PySide6.QtWidgets import (
    QLabel, QMainWindow, QMessageBox, QScrollArea, QSizePolicy, QToolBar,
)

from .archive import ComicError, ComicFile, open_comic
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
        self.setCentralWidget(self.scroll)

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
        act("Schliessen", ["Esc", "Ctrl+W"], self.close)
        act("Erste Seite", ["Home"], lambda: self._show_page(0))
        act("Letzte Seite", ["End"],
            lambda: self._show_page((self.comic.page_count - 1) if self.comic else 0))

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
        self.statusBar().showMessage(
            _("Seite {index} / {total}  –  {name}").format(
                index=index + 1, total=self.comic.page_count,
                name=self.path.name))
        self._pool.start(_PageJob(self.comic, index, self._signals))

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
        self.label.setPixmap(scaled)
        self.label.resize(scaled.size())
        self.scroll.setWidgetResizable(self.fit_mode == FIT_PAGE)

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
        self._pool.clear()
        self._pool.waitForDone(2000)
        if self.comic:
            self.comic.close()
            self.comic = None
        self.closed.emit(str(self.path))
        super().closeEvent(event)
