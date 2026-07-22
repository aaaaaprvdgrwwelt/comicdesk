"""Hauptfenster: Ordnerbaum, Cover-Ansicht, Dateioperationen."""
from __future__ import annotations

import shutil
from pathlib import Path

from PySide6.QtCore import (
    QAbstractListModel, QDir, QModelIndex, QRect, QSettings, QSize, Qt,
)
from PySide6.QtGui import (
    QAction, QColor, QFont, QIcon, QKeySequence, QPainter, QPen, QPixmap,
)
from PySide6.QtWidgets import (
    QAbstractItemView, QApplication, QFileSystemModel, QHBoxLayout,
    QInputDialog, QLabel, QLineEdit, QListView, QListWidget,
    QListWidgetItem, QMainWindow, QMessageBox, QSplitter, QStyle,
    QStyledItemDelegate, QToolBar, QToolButton, QTreeView, QVBoxLayout, QWidget,
)

from . import archive
from .favorites import Favorites
from .icons import icon as app_icon
from .i18n import _, set_language
from .autotagdialog import AutoTagDialog, SettingsDialog
from .index import CollectionIndex
from .indexdialog import IndexDialog
from .metapanel import MetaPanel
from .pageeditor import PageEditorDialog
from .reader import ReaderWindow
from .thumbs import ThumbLoader

RENAME_TEMPLATE_DEFAULT = "{series} #{issue} ({year}){title_dash}"

TILE_W = 190
COVER_H = 250
TEXT_LINES = 2
PAD = 8

#: Zweite, graue Zeile unter dem Dateinamen - im Suchmodus der Ordner.
SUBTITLE_ROLE = Qt.UserRole + 1

SEARCH_PLACEHOLDER = "Sammlung durchsuchen – z. B. serie:batman jahr:1990-1999 joker"
FILTER_PLACEHOLDER = "Filter (Dateiname) …"
SEARCH_FIELDS = ("serie: nummer: titel: jahr: verlag: genre: tag: "
                "figur: team: ort: autor: sprache:")


class CoverDelegate(QStyledItemDelegate):
    """Zeichnet eine Kachel: Cover oben, Dateiname (max. 2 Zeilen) darunter."""

    def sizeHint(self, option, index):  # noqa: N802
        fm = option.fontMetrics
        lines = TEXT_LINES + (1 if index.data(SUBTITLE_ROLE) else 0)
        return QSize(TILE_W, COVER_H + lines * fm.height() + 3 * PAD)

    def paint(self, painter: QPainter, option, index) -> None:  # noqa: N802
        painter.save()
        painter.setRenderHint(QPainter.Antialiasing)
        rect = option.rect.adjusted(3, 3, -3, -3)
        selected = bool(option.state & QStyle.State_Selected)
        hovered = bool(option.state & QStyle.State_MouseOver)

        if selected or hovered:
            color = option.palette.highlight().color()
            if not selected:
                color.setAlpha(60)
            painter.setPen(Qt.NoPen)
            painter.setBrush(color)
            painter.drawRoundedRect(rect, 6, 6)

        cover_rect = QRect(rect.left() + PAD, rect.top() + PAD,
                           rect.width() - 2 * PAD, COVER_H)
        icon = index.data(Qt.DecorationRole)
        if isinstance(icon, QIcon):
            avail = icon.availableSizes()
            pm = icon.pixmap(avail[0] if avail else QSize(96, 96))
            if not pm.isNull():
                target = pm.size().scaled(cover_rect.size(), Qt.KeepAspectRatio)
                x = cover_rect.left() + (cover_rect.width() - target.width()) // 2
                y = cover_rect.top() + (cover_rect.height() - target.height())
                dest = QRect(x, y, target.width(), target.height())
                painter.setPen(QPen(QColor(0, 0, 0, 90)))
                painter.setBrush(Qt.NoBrush)
                painter.drawPixmap(dest, pm)
                painter.drawRect(dest.adjusted(0, 0, -1, -1))

        fm = option.fontMetrics
        text_rect = QRect(rect.left() + 4, cover_rect.bottom() + PAD,
                          rect.width() - 8, TEXT_LINES * fm.height())
        font = QFont(option.font)
        painter.setFont(font)
        painter.setPen(option.palette.highlightedText().color() if selected
                       else option.palette.text().color())
        for i, line in enumerate(_wrap_lines(index.data(Qt.DisplayRole) or "",
                                             fm, text_rect.width(), TEXT_LINES)):
            painter.drawText(
                QRect(text_rect.left(), text_rect.top() + i * fm.height(),
                      text_rect.width(), fm.height()),
                Qt.AlignHCenter | Qt.AlignVCenter, line)

        subtitle = index.data(SUBTITLE_ROLE)
        if subtitle:
            color = painter.pen().color()
            color.setAlpha(150)
            painter.setPen(color)
            painter.drawText(
                QRect(text_rect.left(), text_rect.bottom(),
                      text_rect.width(), fm.height()),
                Qt.AlignHCenter | Qt.AlignVCenter,
                fm.elidedText(subtitle, Qt.ElideMiddle, text_rect.width()))
        painter.restore()


def _wrap_lines(text: str, fm, width: int, max_lines: int) -> list[str]:
    """Bricht `text` auf hoechstens `max_lines` Zeilen um, letzte Zeile elidiert."""
    words = text.split(" ")
    lines: list[str] = []
    current = ""
    for i, word in enumerate(words):
        cand = f"{current} {word}".strip()
        if current and fm.horizontalAdvance(cand) > width:
            if len(lines) == max_lines - 1:
                rest = " ".join(words[i - len(current.split(" ")):])
                lines.append(fm.elidedText(rest, Qt.ElideRight, width))
                return lines
            lines.append(current)
            current = word
        else:
            current = cand
    if current:
        lines.append(fm.elidedText(current, Qt.ElideRight, width))
    return lines


# ---------------------------------------------------------------------------
class ComicListModel(QAbstractListModel):
    def __init__(self, loader: ThumbLoader, parent=None):
        super().__init__(parent)
        self.entries: list[Path] = []
        self.loader = loader
        self.folder_icon = QIcon()
        self.file_icon = QIcon()
        #: Im Suchmodus steht der Ordner unter dem Dateinamen.
        self.show_parent = False
        loader.ready.connect(self._on_thumb)

    def set_entries(self, entries: list[Path], show_parent: bool = False) -> None:
        self.beginResetModel()
        self.entries = entries
        self.show_parent = show_parent
        self.endResetModel()

    def rowCount(self, parent=QModelIndex()) -> int:  # noqa: N802
        return 0 if parent.isValid() else len(self.entries)

    def path_at(self, index: QModelIndex) -> Path | None:
        if index.isValid() and 0 <= index.row() < len(self.entries):
            return self.entries[index.row()]
        return None

    def data(self, index: QModelIndex, role=Qt.DisplayRole):
        p = self.path_at(index)
        if p is None:
            return None
        if role == Qt.DisplayRole:
            return p.name
        if role == Qt.ToolTipRole:
            return str(p)
        if role == SUBTITLE_ROLE:
            return p.parent.name if self.show_parent else None
        if role == Qt.DecorationRole:
            if p.is_dir():
                return self.folder_icon
            pm = self.loader.get(p)
            if pm is None:
                return self.file_icon
            return QIcon(pm) if not pm.isNull() else self.file_icon
        if role == Qt.TextAlignmentRole:
            return Qt.AlignHCenter | Qt.AlignTop
        return None

    def _on_thumb(self, key: str, _pm: QPixmap) -> None:
        for row, p in enumerate(self.entries):
            if str(p) == key:
                idx = self.index(row, 0)
                self.dataChanged.emit(idx, idx, [Qt.DecorationRole])
                return


# ---------------------------------------------------------------------------
class MainWindow(QMainWindow):

    def __init__(self):
        super().__init__()
        self.settings = QSettings("comicdesk", "comicdesk")
        self.current_dir = Path(
            self.settings.value("last_dir", str(Path.home()))
        ).expanduser()
        if not self.current_dir.is_dir():
            self.current_dir = Path.home()
        self.clipboard: list[Path] = []
        self.clipboard_cut = False
        self.readers: dict[str, ReaderWindow] = {}

        self.setWindowTitle("ComicDesk")
        self.resize(1400, 900)
        geometry = self.settings.value("geometry")
        if geometry:
            self.restoreGeometry(geometry)

        self.loader = ThumbLoader(self)
        self.index = CollectionIndex()
        self.favorites = Favorites()
        self._build_ui()
        self._build_actions()
        self.set_directory(self.current_dir)

    # ------------------------------------------------------------------
    def _build_ui(self) -> None:
        style = self.style()

        self.fs_model = QFileSystemModel(self)
        self.fs_model.setRootPath("")
        self.fs_model.setFilter(QDir.AllDirs | QDir.NoDotAndDotDot | QDir.Drives)

        self.tree = QTreeView()
        self.tree.setModel(self.fs_model)
        for col in range(1, self.fs_model.columnCount()):
            self.tree.hideColumn(col)
        self.tree.setHeaderHidden(True)
        self.tree.clicked.connect(self._tree_clicked)

        self.fav_list = QListWidget()
        self.fav_list.setDragDropMode(QAbstractItemView.InternalMove)
        self.fav_list.setDefaultDropAction(Qt.MoveAction)
        self.fav_list.setContextMenuPolicy(Qt.ActionsContextMenu)
        self.fav_list.itemClicked.connect(self._favorite_clicked)
        self.fav_list.itemActivated.connect(self._favorite_activated)
        self.fav_list.model().rowsMoved.connect(lambda *_a: self._save_fav_order())

        fav_box = QWidget()
        fav_layout = QVBoxLayout(fav_box)
        fav_layout.setContentsMargins(0, 0, 0, 0)
        fav_layout.setSpacing(2)
        fav_header = QLabel(_("Favoriten"))
        fav_header.setStyleSheet("font-weight:600; padding:4px 6px;")
        fav_layout.addWidget(fav_header)
        fav_layout.addWidget(self.fav_list, 1)

        left = QSplitter(Qt.Vertical)
        left.addWidget(fav_box)
        left.addWidget(self.tree)
        left.setStretchFactor(1, 1)
        left.setSizes([200, 600])
        self.left_splitter = left

        self.model = ComicListModel(self.loader, self)
        self.model.folder_icon = style.standardIcon(QStyle.SP_DirIcon)
        self.model.file_icon = style.standardIcon(QStyle.SP_FileIcon)

        self.view = QListView()
        self.view.setModel(self.model)
        self.view.setViewMode(QListView.IconMode)
        self.view.setItemDelegate(CoverDelegate(self))
        self.view.setResizeMode(QListView.Adjust)
        self.view.setUniformItemSizes(True)
        self.view.setMouseTracking(True)
        self.view.setSpacing(4)
        self.view.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.view.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.view.doubleClicked.connect(self._activate)
        self.view.selectionModel().selectionChanged.connect(self._selection_changed)

        self.path_edit = QLineEdit()
        self.path_edit.returnPressed.connect(
            lambda: self.set_directory(Path(self.path_edit.text()).expanduser())
        )
        self.filter_edit = QLineEdit(placeholderText=_(FILTER_PLACEHOLDER))
        self.filter_edit.setClearButtonEnabled(True)
        self.filter_edit.textChanged.connect(lambda _: self.refresh())
        self.filter_edit.setMinimumWidth(320)

        self.search_toggle = QToolButton()
        self.search_toggle.setText(_("Sammlung"))
        self.search_toggle.setCheckable(True)
        self.search_toggle.setToolTip(_(
            "Statt im aktuellen Ordner in der gesamten indizierten Sammlung "
            "suchen (Strg+F)"))
        self.search_toggle.toggled.connect(self._toggle_search_mode)

        bar = QHBoxLayout()
        bar.setContentsMargins(6, 4, 6, 4)
        bar.addWidget(QLabel(_("Ordner:")))
        bar.addWidget(self.path_edit, 1)
        bar.addWidget(self.search_toggle)
        bar.addWidget(self.filter_edit, 1)

        center = QWidget()
        cv = QVBoxLayout(center)
        cv.setContentsMargins(0, 0, 0, 0)
        cv.addLayout(bar)
        cv.addWidget(self.view, 1)

        self.meta = MetaPanel()
        self.meta.saved.connect(self._on_tags_saved)

        split = QSplitter()
        split.addWidget(left)
        split.addWidget(center)
        split.addWidget(self.meta)
        split.setStretchFactor(1, 1)
        split.setSizes([260, 800, 360])
        self.setCentralWidget(split)
        state = self.settings.value("splitter")
        if state:
            split.restoreState(state)
        left_state = self.settings.value("left_splitter")
        if left_state:
            left.restoreState(left_state)
        self.splitter = split
        self.refresh_favorites()

    def _build_actions(self) -> None:
        """Menueleiste mit allem, Werkzeugleiste nur mit dem Haeufigen."""
        def act(text, shortcut, slot, icon=None, on_view=False):
            """on_view: Kuerzel gilt nur im Dateibereich, damit Strg+C/X/V und
            Entf in den Metadaten-Feldern weiterhin normal funktionieren.
            Im Menue bleibt der Eintrag trotzdem jederzeit anklickbar."""
            a = QAction(_(text), self)
            if icon:
                a.setIcon(app_icon(icon))
            if shortcut:
                a.setShortcut(QKeySequence(shortcut))
                a.setShortcutContext(
                    Qt.WidgetWithChildrenShortcut if on_view else Qt.WindowShortcut)
            a.triggered.connect(slot)
            (self.view if on_view else self).addAction(a)
            return a

        a = self.actions_map = {
            "up": act("Nach oben", "Alt+Up", self.go_up, "up"),
            "refresh": act("Aktualisieren", "F5", self.refresh, "refresh"),
            "read": act("Lesen", "Return", self.open_selected,
                        "read", on_view=True),
            "reveal": act("Ordner anzeigen", "Ctrl+G", self.reveal_selected,
                          on_view=True),
            "new_folder": act("Neuer Ordner", "Ctrl+Shift+N", self.new_folder,
                              "folder_new"),
            "quit": act("Beenden", "Ctrl+Q", self.close),
            "copy": act("Kopieren", "Ctrl+C", self.copy_selected, on_view=True),
            "cut": act("Ausschneiden", "Ctrl+X", self.cut_selected, on_view=True),
            "paste": act("Einfuegen", "Ctrl+V", self.paste, on_view=True),
            "rename": act("Umbenennen", "F2", self.rename_selected,
                          "rename", on_view=True),
            "delete": act("Loeschen", "Del", self.delete_selected,
                          "delete", on_view=True),
            "search": act("Suchen", "Ctrl+F", self.focus_search, "search"),
            "autotag": act("Automatisch taggen", "Ctrl+T", self.auto_tag,
                           "tag", on_view=True),
            "rename_tpl": act("Nach Tags benennen", "Ctrl+R",
                              self.rename_by_template, on_view=True),
            "pages": act("Seiten verwalten …", "Ctrl+P", self.edit_pages,
                         on_view=True),
            "fav_add": act("Zu Favoriten hinzufuegen", "Ctrl+D",
                           self.toggle_favorite, "star", on_view=True),
            "fav_remove": act("Aus Favoriten entfernen", None,
                              self.remove_favorite),
            "fav_rename": act("Favorit umbenennen", None, self.rename_favorite),
            "fav_prune": act("Verschwundene Favoriten aufraeumen", None,
                             self.prune_favorites),
            "convert": act("Nach CBZ konvertieren", None, self.convert_selected,
                           on_view=True),
            "index": act("Sammlung indizieren …", None, self.edit_index, "index"),
            "settings": act("Einstellungen …", "Ctrl+,", self.edit_settings,
                            "settings"),
            "about": act("Ueber ComicDesk", None, self.show_about),
        }

        # --- Menueleiste ---------------------------------------------
        bar = self.menuBar()
        menu = bar.addMenu(_("&Datei"))
        for key in ("up", "refresh", "new_folder"):
            menu.addAction(a[key])
        menu.addSeparator()
        for key in ("read", "reveal"):
            menu.addAction(a[key])
        menu.addSeparator()
        menu.addAction(a["fav_add"])
        menu.addSeparator()
        menu.addAction(a["quit"])

        menu = bar.addMenu(_("&Bearbeiten"))
        for key in ("copy", "cut", "paste"):
            menu.addAction(a[key])
        menu.addSeparator()
        for key in ("rename", "delete"):
            menu.addAction(a[key])

        menu = bar.addMenu(_("&Ansicht"))
        menu.addAction(a["search"])
        self.action_search_mode = QAction(_("In der Sammlung suchen"), self)
        self.action_search_mode.setCheckable(True)
        self.action_search_mode.toggled.connect(self.search_toggle.setChecked)
        self.search_toggle.toggled.connect(self.action_search_mode.setChecked)
        menu.addAction(self.action_search_mode)

        menu = bar.addMenu(_("E&xtras"))
        for key in ("autotag", "rename_tpl", "pages", "convert"):
            menu.addAction(a[key])
        menu.addSeparator()
        menu.addAction(a["index"])
        menu.addAction(a["settings"])

        bar.addMenu(_("&Hilfe")).addAction(a["about"])

        # --- Werkzeugleiste: nur was staendig gebraucht wird ----------
        tb = QToolBar(_("Aktionen"))
        tb.setMovable(False)
        tb.setToolButtonStyle(Qt.ToolButtonIconOnly)
        self.addToolBar(tb)
        for key in ("up", "refresh"):
            tb.addAction(a[key])
        tb.addSeparator()
        tb.addAction(a["read"])
        tb.widgetForAction(a["read"]).setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        tb.addSeparator()
        for key in ("rename", "delete", "autotag", "fav_add"):
            tb.addAction(a[key])
        for action in a.values():
            if action.shortcut().isEmpty():
                action.setToolTip(action.text())
            else:
                action.setToolTip(
                    f"{action.text()}  ({action.shortcut().toString()})")

        for key in ("fav_add", "fav_rename", "fav_remove", "fav_prune"):
            self.fav_list.addAction(a[key])

        # --- Kontextmenue der Dateiansicht ----------------------------
        self.view.setContextMenuPolicy(Qt.ActionsContextMenu)
        self.statusBar().showMessage(_("Bereit"))

    # ------------------------------------------------------------------
    def set_directory(self, path: Path) -> None:
        path = Path(path).expanduser()
        if not path.is_dir():
            QMessageBox.warning(self, _("Ordner"),
                                _("Nicht gefunden: {path}").format(path=path))
            return
        self.current_dir = path
        self.path_edit.setText(str(path))
        idx = self.fs_model.index(str(path))
        self.tree.setCurrentIndex(idx)
        self.tree.scrollTo(idx)
        self.tree.expand(idx)
        self.settings.setValue("last_dir", str(path))
        self.refresh()
        self._update_favorite_action()

    def go_up(self) -> None:
        if self.current_dir.parent != self.current_dir:
            self.set_directory(self.current_dir.parent)

    @property
    def search_mode(self) -> bool:
        return self.search_toggle.isChecked()

    def _toggle_search_mode(self, on: bool) -> None:
        self.filter_edit.setPlaceholderText(
            _(SEARCH_PLACEHOLDER if on else FILTER_PLACEHOLDER))
        self.filter_edit.setFocus()
        self.refresh()

    def focus_search(self) -> None:
        self.search_toggle.setChecked(True)
        self.filter_edit.selectAll()
        self.filter_edit.setFocus()

    def refresh(self) -> None:
        if self.search_mode:
            self._refresh_search()
            return
        needle = self.filter_edit.text().strip().lower()
        try:
            children = list(self.current_dir.iterdir())
        except OSError as exc:
            QMessageBox.warning(self, _("Ordner"), str(exc))
            return
        dirs = sorted(
            (p for p in children if p.is_dir() and not p.name.startswith(".")),
            key=lambda p: archive.natural_key(p.name),
        )
        comics = sorted(
            (p for p in children if p.is_file() and archive.is_comic(p)),
            key=lambda p: archive.natural_key(p.name),
        )
        if needle:
            dirs = [p for p in dirs if needle in p.name.lower()]
            comics = [p for p in comics if needle in p.name.lower()]
        self.model.set_entries(dirs + comics)
        self.meta.clear()
        self.statusBar().showMessage(
            _("{comics} Comics, {dirs} Ordner in {path}").format(
                comics=len(comics), dirs=len(dirs), path=self.current_dir))

    def _refresh_search(self) -> None:
        query = self.filter_edit.text().strip()
        indexed = self.index.count()
        if not query:
            self.model.set_entries([])
            self.meta.clear()
            self.statusBar().showMessage(
                _("Suchmodus – {total} Comics im Index. Felder: {fields}")
                .format(total=indexed, fields=SEARCH_FIELDS)
                if indexed else
                _("Suchmodus – der Index ist noch leer. Erst „Sammlung "
                  "indizieren …“ ausfuehren."))
            return
        try:
            hits = self.index.search(query)
        except Exception as exc:  # noqa: BLE001
            self.statusBar().showMessage(
                _("Suche fehlgeschlagen: {error}").format(error=exc), 6000)
            return
        self.model.set_entries(hits, show_parent=True)
        self.meta.clear()
        self.statusBar().showMessage(
            _("{hits} Treffer von {total} indizierten Comics").format(
                hits=len(hits), total=indexed))

    # ------------------------------------------------------------------
    def selected_paths(self) -> list[Path]:
        out = []
        for idx in self.view.selectionModel().selectedIndexes():
            p = self.model.path_at(idx)
            if p is not None:
                out.append(p)
        return out

    def _selection_changed(self, *_args) -> None:
        paths = [p for p in self.selected_paths() if p.is_file()]
        self.meta.load(paths[0] if len(paths) == 1 else None)
        self._update_favorite_action()

    def _tree_clicked(self, index: QModelIndex) -> None:
        self.set_directory(Path(self.fs_model.filePath(index)))

    def _activate(self, index: QModelIndex) -> None:
        p = self.model.path_at(index)
        if p is None:
            return
        if p.is_dir():
            self.set_directory(p)
        else:
            self.open_comic(p)

    def open_selected(self) -> None:
        for p in self.selected_paths()[:5]:
            if p.is_dir():
                self.set_directory(p)
                return
            self.open_comic(p)

    def open_comic(self, path: Path) -> None:
        key = str(path)
        if key in self.readers:
            self.readers[key].raise_()
            self.readers[key].activateWindow()
            return
        win = ReaderWindow(path, self)
        win.setAttribute(Qt.WA_DeleteOnClose)
        win.closed.connect(lambda k: self.readers.pop(k, None))
        self.readers[key] = win
        win.show()

    # --- Dateioperationen ---------------------------------------------
    def rename_selected(self) -> None:
        paths = self.selected_paths()
        if len(paths) != 1:
            self.statusBar().showMessage(_("Bitte genau einen Eintrag waehlen."), 4000)
            return
        old = paths[0]
        new_name, ok = QInputDialog.getText(
            self, _("Umbenennen"), _("Neuer Name:"), QLineEdit.Normal, old.name
        )
        if not ok or not new_name.strip() or new_name == old.name:
            return
        self._do_rename(old, old.parent / new_name.strip())

    def _do_rename(self, old: Path, new: Path) -> bool:
        if new.exists():
            QMessageBox.warning(self, _("Umbenennen"),
                                _("{name} existiert bereits.").format(name=new.name))
            return False
        try:
            old.rename(new)
        except OSError as exc:
            QMessageBox.critical(self, _("Umbenennen"), str(exc))
            return False
        self._deindex(old)
        self._reindex(new)
        self.favorites.move_path(old, new)
        self.refresh_favorites()
        return True

    def rename_by_template(self) -> None:
        paths = [p for p in self.selected_paths() if p.is_file()]
        if not paths:
            return
        template = self.settings.value("rename_template", RENAME_TEMPLATE_DEFAULT)
        template, ok = QInputDialog.getText(
            self, _("Nach Tags benennen"),
            _("Schema – verfuegbar: {series} {issue} {title} {title_dash} "
              "{year} {month} {volume} {publisher}"),
            QLineEdit.Normal, template,
        )
        if not ok or not template.strip():
            return
        self.settings.setValue("rename_template", template)

        planned: list[tuple[Path, Path]] = []
        skipped = 0
        for p in paths:
            comic = None
            try:
                comic = archive.open_comic(p)
                md = comic.read_metadata()
            except Exception:  # noqa: BLE001
                skipped += 1
                continue
            finally:
                if comic is not None:
                    comic.close()
            name = _format_name(template, md)
            if not name:
                skipped += 1
                continue
            target = p.parent / (name + p.suffix.lower())
            if target != p:
                planned.append((p, target))

        if not planned:
            QMessageBox.information(
                self, _("Nach Tags benennen"),
                _("Nichts umzubenennen ({count} ohne brauchbare Tags).")
                .format(count=skipped))
            return
        preview = "\n".join(f"{a.name}\n   →  {b.name}" for a, b in planned[:15])
        more = ("\n… " + _("und {count} weitere").format(count=len(planned) - 15)
                if len(planned) > 15 else "")
        if QMessageBox.question(
            self, _("Umbenennen bestaetigen"),
            _("{count} Datei(en) umbenennen?\n\n{preview}{more}").format(
                count=len(planned), preview=preview, more=more),
        ) != QMessageBox.Yes:
            return
        for old, new in planned:
            self._do_rename(old, new)
        self.refresh()

    def copy_selected(self) -> None:
        self.clipboard = self.selected_paths()
        self.clipboard_cut = False
        self.statusBar().showMessage(
            _("{count} kopiert.").format(count=len(self.clipboard)), 4000)

    def cut_selected(self) -> None:
        self.clipboard = self.selected_paths()
        self.clipboard_cut = True
        self.statusBar().showMessage(
            _("{count} ausgeschnitten.").format(count=len(self.clipboard)), 4000)

    def paste(self) -> None:
        if not self.clipboard:
            return
        errors = []
        for src in self.clipboard:
            if not src.exists():
                continue
            dest = _unique(self.current_dir / src.name)
            try:
                if self.clipboard_cut:
                    shutil.move(str(src), str(dest))
                    self._deindex(src)
                elif src.is_dir():
                    shutil.copytree(src, dest)
                else:
                    shutil.copy2(src, dest)
            except OSError as exc:
                errors.append(f"{src.name}: {exc}")
        if self.clipboard_cut:
            self.clipboard = []
        if errors:
            QMessageBox.warning(self, _("Einfuegen"), "\n".join(errors))
        self.refresh()

    def delete_selected(self) -> None:
        paths = self.selected_paths()
        if not paths:
            return
        names = "\n".join(p.name for p in paths[:12])
        more = ("\n… " + _("und {count} weitere").format(count=len(paths) - 12)
                if len(paths) > 12 else "")
        if QMessageBox.question(
            self, _("Loeschen"),
            _("{count} Eintrag/Eintraege in den Papierkorb verschieben?"
              "\n\n{names}{more}").format(
                count=len(paths), names=names, more=more),
        ) != QMessageBox.Yes:
            return
        errors = []
        for p in paths:
            try:
                from send2trash import send2trash

                send2trash(str(p))
                self._deindex(p)
            except Exception as exc:  # noqa: BLE001
                errors.append(f"{p.name}: {exc}")
        if errors:
            QMessageBox.warning(self, _("Loeschen"), "\n".join(errors))
        self.refresh()

    def new_folder(self) -> None:
        name, ok = QInputDialog.getText(self, _("Neuer Ordner"), _("Name:"))
        if not ok or not name.strip():
            return
        try:
            (self.current_dir / name.strip()).mkdir()
        except OSError as exc:
            QMessageBox.critical(self, _("Neuer Ordner"), str(exc))
        self.refresh()

    def auto_tag(self) -> None:
        """Auswahl (oder den ganzen Ordner) gegen ComicVine/GCD abgleichen."""
        paths = [p for p in self.selected_paths() if p.is_file()]
        if not paths:
            paths = [p for p in self.model.entries if p.is_file()]
        if not paths:
            self.statusBar().showMessage(_("Keine Comics zum Taggen."), 4000)
            return
        dialog = AutoTagDialog(paths, self.settings, self)
        dialog.exec()
        for path in paths:
            self._reindex(path)
        self.refresh()

    def apply_language(self, code: str) -> None:
        """Sprache uebernehmen und das Fenster neu aufbauen."""
        set_language(code)
        geometry = self.saveGeometry()
        fresh = MainWindow()
        fresh.restoreGeometry(geometry)
        fresh.show()
        # Referenz halten, damit das neue Fenster nicht eingesammelt wird.
        QApplication.instance().setProperty("comicdesk_main", fresh)
        self.close()

    def edit_pages(self) -> None:
        """Seiten der ausgewaehlten Datei loeschen oder umsortieren."""
        paths = [p for p in self.selected_paths() if p.is_file()]
        if len(paths) != 1:
            self.statusBar().showMessage(_("Bitte genau einen Eintrag waehlen."), 4000)
            return
        target = paths[0]
        reader = self.readers.get(str(target))
        if reader:
            reader.close()
        dialog = PageEditorDialog(target, self)
        dialog.changed.connect(self._on_pages_changed)
        dialog.exec()

    def _on_pages_changed(self, path: str) -> None:
        """Cover-Thumbnail und Index nachziehen - die Datei hat sich geaendert."""
        target = Path(path)
        self.loader.forget(target)
        self._reindex(target)
        self.refresh()
        self.statusBar().showMessage(_("Seiten gespeichert."), 4000)

    def edit_settings(self, start_tab: int = 0) -> None:
        dialog = SettingsDialog(self.settings, self, start_tab)
        if dialog.exec() and dialog.language_changed:
            self.apply_language(self.settings.value("language", "auto"))

    def show_about(self) -> None:
        QMessageBox.about(self, _("Ueber ComicDesk"), _(
            "ComicDesk – ein Dateimanager nur fuer Comics.\n\n"
            "Browsen, lesen, taggen und ordnen von CBZ, CBR, CB7, CBT und PDF. "
            "Tags werden als ComicInfo.xml geschrieben.\n\n"
            "Metadaten von ComicVine und der Grand Comics Database."))

    def edit_index(self) -> None:
        IndexDialog(self.index, self.current_dir, self).exec()
        self.refresh()

    def reveal_selected(self) -> None:
        """Aus der Sammlungssuche zurueck in den Ordner der Datei springen."""
        paths = self.selected_paths()
        if not paths:
            return
        target = paths[0]
        self.search_toggle.setChecked(False)
        self.filter_edit.clear()
        self.set_directory(target.parent if target.is_file() else target)
        for row, entry in enumerate(self.model.entries):
            if entry == target:
                idx = self.model.index(row, 0)
                self.view.setCurrentIndex(idx)
                self.view.scrollTo(idx)
                break

    # --- Favoriten ----------------------------------------------------
    def refresh_favorites(self) -> None:
        self.fav_list.blockSignals(True)
        self.fav_list.clear()
        for entry in self.favorites.entries:
            item = QListWidgetItem(entry.display)
            item.setData(Qt.UserRole, entry.path)
            item.setIcon(app_icon("folder" if entry.is_dir else "read"))
            if entry.exists:
                item.setToolTip(entry.path)
            else:
                font = item.font()
                font.setItalic(True)
                item.setFont(font)
                item.setForeground(Qt.gray)
                item.setToolTip(
                    _("Nicht gefunden: {path}").format(path=entry.path))
            self.fav_list.addItem(item)
        self.fav_list.blockSignals(False)
        self._update_favorite_action()

    def _favorite_target(self) -> Path | None:
        """Was gerade als Favorit gemeint ist: Auswahl, sonst der Ordner."""
        paths = self.selected_paths()
        return paths[0] if paths else self.current_dir

    def _update_favorite_action(self) -> None:
        # Wird schon beim Aufbau der Ansicht gerufen - da gibt es noch keine
        # Aktionen.
        action = getattr(self, "actions_map", {}).get("fav_add")
        target = self._favorite_target()
        if action is None or target is None:
            return
        is_fav = self.favorites.contains(target)
        action.setText(_("Aus Favoriten entfernen") if is_fav
                       else _("Zu Favoriten hinzufuegen"))
        action.setIcon(app_icon("star" if is_fav else "star_off"))

    def toggle_favorite(self) -> None:
        target = self._favorite_target()
        if target is None:
            return
        added = self.favorites.toggle(target)
        self.refresh_favorites()
        self.statusBar().showMessage(
            _("„{name}“ zu den Favoriten hinzugefuegt.").format(name=target.name)
            if added else
            _("„{name}“ aus den Favoriten entfernt.").format(name=target.name),
            4000)

    def _selected_favorite(self) -> Path | None:
        item = self.fav_list.currentItem()
        return Path(item.data(Qt.UserRole)) if item else None

    def remove_favorite(self) -> None:
        target = self._selected_favorite()
        if target is None:
            return
        self.favorites.remove(target)
        self.refresh_favorites()

    def rename_favorite(self) -> None:
        target = self._selected_favorite()
        if target is None:
            return
        item = self.fav_list.currentItem()
        label, ok = QInputDialog.getText(
            self, _("Favorit umbenennen"), _("Anzeigename:"),
            QLineEdit.Normal, item.text())
        if ok:
            self.favorites.rename(target, label.strip())
            self.refresh_favorites()

    def prune_favorites(self) -> None:
        removed = self.favorites.prune_missing()
        self.refresh_favorites()
        self.statusBar().showMessage(
            _("{count} verschwundene Favoriten entfernt.").format(count=removed),
            4000)

    def _save_fav_order(self) -> None:
        self.favorites.reorder([
            self.fav_list.item(r).data(Qt.UserRole)
            for r in range(self.fav_list.count())])

    def _favorite_clicked(self, item: QListWidgetItem) -> None:
        target = Path(item.data(Qt.UserRole))
        if not target.exists():
            self.statusBar().showMessage(
                _("Nicht gefunden: {path}").format(path=target), 6000)
            return
        if target.is_dir():
            self.search_toggle.setChecked(False)
            self.set_directory(target)
        else:
            self._select_in_folder(target)

    def _favorite_activated(self, item: QListWidgetItem) -> None:
        target = Path(item.data(Qt.UserRole))
        if target.is_file():
            self.open_comic(target)

    def _select_in_folder(self, target: Path) -> None:
        self.search_toggle.setChecked(False)
        self.set_directory(target.parent)
        for row, entry in enumerate(self.model.entries):
            if entry == target:
                index = self.model.index(row, 0)
                self.view.setCurrentIndex(index)
                self.view.scrollTo(index)
                break

    # --- Index aktuell halten -----------------------------------------
    def _on_tags_saved(self, path: str) -> None:
        self._reindex(Path(path))
        self.statusBar().showMessage(_("Tags gespeichert."), 4000)

    def _reindex(self, path: Path) -> None:
        """Einzelne Datei neu einlesen - nach Tag-Aenderungen oder Umbenennen."""
        if not path.is_file() or not archive.is_comic(path):
            return
        try:
            comic = archive.open_comic(path)
            try:
                self.index.upsert(path, comic.read_metadata(), comic.page_count)
            finally:
                comic.close()
        except Exception:  # noqa: BLE001
            pass  # Index ist nur Cache - ein Fehler hier darf nichts kaputtmachen

    def _deindex(self, path: Path) -> None:
        try:
            self.index.remove(path)
        except Exception:  # noqa: BLE001
            pass

    def convert_selected(self) -> None:
        paths = [p for p in self.selected_paths()
                 if p.is_file() and p.suffix.lower() != ".cbz"]
        if not paths:
            self.statusBar().showMessage(_("Keine konvertierbaren Dateien gewaehlt."), 4000)
            return
        if QMessageBox.question(
            self, _("Nach CBZ konvertieren"),
            _("{count} Datei(en) nach CBZ konvertieren? "
              "Die Originale bleiben erhalten.").format(count=len(paths)),
        ) != QMessageBox.Yes:
            return
        errors = []
        for p in paths:
            try:
                archive.convert_to_cbz(p, _unique(p.with_suffix(".cbz")))
            except Exception as exc:  # noqa: BLE001
                errors.append(f"{p.name}: {exc}")
        if errors:
            QMessageBox.warning(self, _("Konvertieren"), "\n".join(errors))
        self.refresh()

    # ------------------------------------------------------------------
    def closeEvent(self, event):  # noqa: N802
        self._store_session()
        super().closeEvent(event)

    def _store_session(self) -> None:
        """Sofort auf Platte schreiben - ein Absturz soll nichts kosten."""
        self.settings.setValue("splitter", self.splitter.saveState())
        self.settings.setValue("left_splitter", self.left_splitter.saveState())
        self.settings.setValue("geometry", self.saveGeometry())
        self.settings.setValue("last_dir", str(self.current_dir))
        self.settings.sync()


# ---------------------------------------------------------------------------
_INVALID = '<>:"/\\|?*\n\r\t'


def _sanitize(name: str) -> str:
    for ch in _INVALID:
        name = name.replace(ch, "_")
    return " ".join(name.split()).strip(" .")


def _format_name(template: str, md) -> str | None:
    if not md.series and not md.title:
        return None
    values = {
        "series": md.series or "",
        "issue": md.issue or "",
        "title": md.title or "",
        "year": str(md.year) if md.year else "",
        "month": f"{md.month:02d}" if md.month else "",
        "volume": str(md.volume) if md.volume else "",
        "publisher": md.publisher or "",
        "title_dash": f" - {md.title}" if md.title else "",
    }
    try:
        name = template.format(**values)
    except (KeyError, IndexError, ValueError):
        return None
    name = name.replace("()", "").replace("#,", "")
    return _sanitize(name) or None


def _unique(path: Path) -> Path:
    if not path.exists():
        return path
    stem, suffix = path.stem, path.suffix
    i = 2
    while True:
        cand = path.with_name(f"{stem} ({i}){suffix}")
        if not cand.exists():
            return cand
        i += 1
