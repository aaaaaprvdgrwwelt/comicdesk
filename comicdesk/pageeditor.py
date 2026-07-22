"""Seiten eines Comics loeschen und umsortieren."""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QObject, QSize, Qt, QThread, Signal
from PySide6.QtGui import QAction, QImage, QKeySequence, QPixmap
from PySide6.QtWidgets import (
    QAbstractItemView, QDialog, QLabel, QListWidget, QListWidgetItem,
    QMessageBox, QToolBar, QVBoxLayout,
)

from .archive import ComicError, open_comic
from .background import stop_and_detach
from .i18n import _
from .icons import icon as app_icon

THUMB = 150
#: Der urspruengliche Seitenindex haengt am Listeneintrag.
PAGE_ROLE = Qt.UserRole + 1


class _ThumbWorker(QObject):
    """Laedt die Seitenbilder der Reihe nach in einem eigenen Thread.

    Bewusst sequentiell: ZipFile und fitz.Document vertragen keine parallelen
    Zugriffe, und fuer die Vorschau reicht das voellig.
    """

    ready = Signal(int, QImage)
    finished = Signal()

    def __init__(self, path: Path, count: int):
        super().__init__()
        self.path = path
        self.count = count
        self._stop = False

    def stop(self) -> None:
        self._stop = True

    def run(self) -> None:
        comic = None
        try:
            comic = open_comic(self.path)
            for index in range(self.count):
                if self._stop:
                    break
                try:
                    image = QImage()
                    image.loadFromData(comic.page_bytes(index))
                    if not image.isNull():
                        self.ready.emit(
                            index,
                            image.scaled(THUMB, THUMB, Qt.KeepAspectRatio,
                                         Qt.SmoothTransformation))
                except Exception:  # noqa: BLE001
                    continue
        except Exception:  # noqa: BLE001
            pass
        finally:
            if comic is not None:
                comic.close()
            self.finished.emit()


class PageEditorDialog(QDialog):
    """Seitenraster mit Ziehen zum Umsortieren und Entf zum Loeschen."""

    changed = Signal(str)

    def __init__(self, path: Path, parent=None):
        super().__init__(parent)
        self.path = Path(path)
        self.thread: QThread | None = None
        self.worker: _ThumbWorker | None = None
        self._history: list[list[int]] = []

        self.setWindowTitle(_("Seiten verwalten – {name}").format(
            name=self.path.name))
        self.resize(1000, 720)
        root = QVBoxLayout(self)

        comic = None
        try:
            comic = open_comic(self.path)
            self.total = comic.page_count
            self.editable = comic.can_edit_pages
            labels = [comic.page_label(i) for i in range(self.total)]
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(self, _("Fehler"), str(exc))
            self.total, self.editable, labels = 0, False, []
        finally:
            if comic is not None:
                comic.close()

        self.list = QListWidget()
        self.list.setViewMode(QListWidget.IconMode)
        self.list.setIconSize(QSize(THUMB, THUMB))
        self.list.setGridSize(QSize(THUMB + 26, THUMB + 46))
        self.list.setResizeMode(QListWidget.Adjust)
        self.list.setMovement(QListWidget.Static)
        self.list.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.list.setDragDropMode(QAbstractItemView.InternalMove)
        self.list.setDefaultDropAction(Qt.MoveAction)
        self.list.setWordWrap(True)
        self.list.model().rowsMoved.connect(lambda *_a: self._refresh_status())

        placeholder = QPixmap(THUMB, THUMB)
        placeholder.fill(Qt.transparent)
        for index in range(self.total):
            item = QListWidgetItem(placeholder, "")
            item.setData(PAGE_ROLE, index)
            item.setToolTip(labels[index])
            item.setTextAlignment(Qt.AlignHCenter | Qt.AlignBottom)
            self.list.addItem(item)

        self._build_toolbar(root)
        root.addWidget(self.list, 1)
        self.status = QLabel()
        root.addWidget(self.status)

        if not self.editable:
            self.status.setStyleSheet("color:#c07000;")
        self._renumber()
        self._start_thumbs()

    # ------------------------------------------------------------------
    def _build_toolbar(self, layout) -> None:
        tb = QToolBar()
        tb.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        layout.addWidget(tb)

        def act(text, shortcut, slot, name=None):
            a = QAction(_(text), self)
            if name:
                a.setIcon(app_icon(name))
            if shortcut:
                a.setShortcut(QKeySequence(shortcut))
            a.triggered.connect(slot)
            tb.addAction(a)
            self.addAction(a)
            return a

        self.a_delete = act("Seiten loeschen", "Del", self.delete_selected, "delete")
        tb.addSeparator()
        self.a_left = act("Nach vorne", "Ctrl+Left",
                          lambda: self.move_selected(-1), "left")
        self.a_right = act("Nach hinten", "Ctrl+Right",
                           lambda: self.move_selected(1), "right")
        self.a_first = act("An den Anfang", "Ctrl+Home", self.move_to_start, "first")
        self.a_last = act("Ans Ende", "Ctrl+End", self.move_to_end, "last")
        tb.addSeparator()
        self.a_undo = act("Rueckgaengig", "Ctrl+Z", self.undo, "undo")
        tb.addSeparator()
        self.a_save = act("Speichern", "Ctrl+S", self.save, "save")
        act("Schliessen", "Esc", self.reject)

        for a in (self.a_delete, self.a_left, self.a_right, self.a_first,
                  self.a_last, self.a_undo, self.a_save):
            a.setEnabled(self.editable)
        self.a_undo.setEnabled(False)

    # ------------------------------------------------------------------
    def _start_thumbs(self) -> None:
        if not self.total:
            return
        self.thread = QThread()
        self.worker = _ThumbWorker(self.path, self.total)
        self.worker.moveToThread(self.thread)
        self.thread.started.connect(self.worker.run)
        self.worker.ready.connect(self._on_thumb)
        self.worker.finished.connect(self.thread.quit)
        self.thread.start()

    def _on_thumb(self, index: int, image: QImage) -> None:
        pixmap = QPixmap.fromImage(image)
        for row in range(self.list.count()):
            item = self.list.item(row)
            if item.data(PAGE_ROLE) == index:
                item.setIcon(pixmap)
                return

    # --- Bearbeiten ---------------------------------------------------
    def current_order(self) -> list[int]:
        return [self.list.item(r).data(PAGE_ROLE)
                for r in range(self.list.count())]

    def _snapshot(self) -> None:
        self._history.append(self.current_order())
        self.a_undo.setEnabled(True)

    def undo(self) -> None:
        if not self._history:
            return
        order = self._history.pop()
        icons = {self.list.item(r).data(PAGE_ROLE): self.list.item(r).icon()
                 for r in range(self.list.count())}
        tips = {self.list.item(r).data(PAGE_ROLE): self.list.item(r).toolTip()
                for r in range(self.list.count())}
        self.list.clear()
        for index in order:
            item = QListWidgetItem(icons.get(index, QPixmap()), "")
            item.setData(PAGE_ROLE, index)
            item.setToolTip(tips.get(index, ""))
            item.setTextAlignment(Qt.AlignHCenter | Qt.AlignBottom)
            self.list.addItem(item)
        self.a_undo.setEnabled(bool(self._history))
        self._renumber()

    def delete_selected(self) -> None:
        rows = sorted((self.list.row(i) for i in self.list.selectedItems()),
                      reverse=True)
        if not rows or len(rows) >= self.list.count():
            if rows:
                QMessageBox.information(
                    self, _("Seiten loeschen"),
                    _("Ein Comic braucht mindestens eine Seite."))
            return
        self._snapshot()
        for row in rows:
            self.list.takeItem(row)
        self._renumber()

    def move_selected(self, offset: int) -> None:
        rows = sorted(self.list.row(i) for i in self.list.selectedItems())
        if not rows:
            return
        if offset < 0 and rows[0] == 0:
            return
        if offset > 0 and rows[-1] == self.list.count() - 1:
            return
        self._snapshot()
        for row in (rows if offset < 0 else reversed(rows)):
            item = self.list.takeItem(row)
            self.list.insertItem(row + offset, item)
            item.setSelected(True)
        self._renumber()

    def move_to_start(self) -> None:
        self._move_to_edge(start=True)

    def move_to_end(self) -> None:
        self._move_to_edge(start=False)

    def _move_to_edge(self, start: bool) -> None:
        rows = sorted(self.list.row(i) for i in self.list.selectedItems())
        if not rows:
            return
        self._snapshot()
        items = [self.list.takeItem(r) for r in reversed(rows)][::-1]
        for offset, item in enumerate(items):
            self.list.insertItem(
                offset if start else self.list.count(), item)
            item.setSelected(True)
        self._renumber()

    def _renumber(self) -> None:
        for row in range(self.list.count()):
            self.list.item(row).setText(str(row + 1))
        self._refresh_status()

    def _refresh_status(self) -> None:
        current = self.list.count()
        removed = self.total - current
        moved = self.current_order() != list(range(self.total))
        parts = [_("{count} Seiten").format(count=current)]
        if removed:
            parts.append(_("{count} werden geloescht").format(count=removed))
        if moved and not removed:
            parts.append(_("Reihenfolge geaendert"))
        if not self.editable:
            parts.append(_("Diese Datei ist nicht bearbeitbar – erst nach CBZ "
                           "konvertieren."))
        self.status.setText(" · ".join(parts))
        self.a_save.setEnabled(self.editable and (removed > 0 or moved))

    # --- Speichern ----------------------------------------------------
    def save(self) -> None:
        order = self.current_order()
        removed = self.total - len(order)
        question = (
            _("{count} Seite(n) werden dauerhaft aus der Datei entfernt. "
              "Fortfahren?").format(count=removed) if removed else
            _("Neue Seitenreihenfolge in die Datei schreiben?"))
        if QMessageBox.question(self, _("Seiten speichern"), question) != \
                QMessageBox.Yes:
            return
        self._stop_thumbs(wait=True)
        comic = None
        try:
            comic = open_comic(self.path)
            comic.save_page_order(order)
        except ComicError as exc:
            QMessageBox.warning(self, _("Seiten speichern"), str(exc))
            return
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(self, _("Seiten speichern"),
                                 _("Fehlgeschlagen:\n{error}").format(error=exc))
            return
        finally:
            if comic is not None:
                comic.close()
        self.changed.emit(str(self.path))
        self.accept()

    # ------------------------------------------------------------------
    def _stop_thumbs(self, wait: bool = False) -> None:
        """`wait=True` vor dem Schreiben: der Vorschau-Thread haelt die Datei
        offen. Beim Schliessen dagegen nie warten - sonst haengt das Fenster.
        """
        if wait and self.thread is not None:
            if self.worker:
                self.worker.stop()
            self.thread.quit()
            self.thread.wait(5000)
            self.thread = self.worker = None
            return
        stop_and_detach(self, self.thread, self.worker)
        self.thread = self.worker = None

    def closeEvent(self, event):  # noqa: N802
        self._stop_thumbs()
        super().closeEvent(event)

    def reject(self) -> None:
        self._stop_thumbs()
        super().reject()
