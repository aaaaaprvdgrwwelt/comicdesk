"""Hauptfenster: Ordnerbaum, Cover-Ansicht, Dateioperationen."""
from __future__ import annotations

import shutil
from pathlib import Path

from PySide6.QtCore import (
    QAbstractListModel, QDir, QModelIndex, QRect, QSettings, QSize, Qt,
    QTimer,
)
from PySide6.QtGui import (
    QAction, QColor, QFont, QIcon, QKeySequence, QPainter, QPen, QPixmap,
)
from PySide6.QtWidgets import (
    QAbstractItemView, QApplication, QComboBox, QFileSystemModel, QHBoxLayout,
    QInputDialog, QLabel, QLineEdit, QListView, QListWidget, QListWidgetItem,
    QMainWindow, QMenu, QMessageBox, QSplitter, QStyle, QStyledItemDelegate,
    QToolBar, QToolButton, QTreeView, QVBoxLayout, QWidget,
)

from . import archive
from .favorites import Favorites
from .icons import icon as app_icon
from .i18n import _, set_language
from .autotagdialog import AutoTagDialog, SettingsDialog
from .index import CollectionIndex
from .indexdialog import CollectionsDialog
from .metapanel import MetaPanel
from .pageeditor import PageEditorDialog
from .reader import ReaderWindow
from .seriesdialog import SeriesDialog
from .thumbs import ThumbLoader

RENAME_TEMPLATE_DEFAULT = "{series} #{issue} ({year}){title_dash}"

TILE_W = 190
COVER_H = 250
TEXT_LINES = 2
PAD = 8

#: Zweite, graue Zeile unter dem Dateinamen - im Suchmodus der Ordner.
SUBTITLE_ROLE = Qt.UserRole + 1
#: (hat Tags, Quelle) aus dem Index - fuer die Ecke der Kachel.
STATUS_ROLE = Qt.UserRole + 2
#: Ordner werden anders gezeichnet als Cover.
IS_DIR_ROLE = Qt.UserRole + 3
FOLDER_ICON_SIZE = 72
#: Enthaelt die Ansicht nur Ordner, braucht sie keine Cover-Hoehe.
COMPACT_COVER_H = 96

SOURCE_COLORS = {
    "comicvine": QColor(60, 130, 200),
    "gcd": QColor(70, 155, 95),
    "manual": QColor(120, 120, 120),
    "unknown": QColor(185, 185, 185),
}

SEARCH_PLACEHOLDER = "Sammlung durchsuchen – z. B. serie:batman jahr:1990-1999 joker"
FILTER_PLACEHOLDER = "Filter (Dateiname) …"
SEARCH_FIELDS = ("serie: nummer: titel: jahr: verlag: genre: tag: figur: "
                "team: ort: autor: sprache: quelle: getaggt:")


class CoverDelegate(QStyledItemDelegate):
    """Zeichnet eine Kachel: Cover oben, Dateiname (max. 2 Zeilen) darunter."""

    @staticmethod
    def cover_height(index) -> int:
        model = index.model()
        return COMPACT_COVER_H if getattr(model, "compact", False) else COVER_H

    def sizeHint(self, option, index):  # noqa: N802
        fm = option.fontMetrics
        lines = TEXT_LINES + (1 if index.data(SUBTITLE_ROLE) else 0)
        return QSize(TILE_W, self.cover_height(index) + lines * fm.height()
                     + 3 * PAD)

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
                           rect.width() - 2 * PAD, self.cover_height(index))
        is_dir = bool(index.data(IS_DIR_ROLE))
        icon = index.data(Qt.DecorationRole)
        pm = QPixmap()
        if isinstance(icon, QIcon):
            avail = icon.availableSizes()
            pm = icon.pixmap(avail[0] if avail else QSize(96, 96))
        has_cover = not pm.isNull() and pm.width() > FOLDER_ICON_SIZE

        if is_dir and not has_cover:
            # Ohne Vorschau ein kleines Symbol mittig - nicht das System-Icon
            # auf Kachelgroesse aufblasen.
            size = FOLDER_ICON_SIZE
            glyph = app_icon("folder", size).pixmap(size, size)
            painter.drawPixmap(
                cover_rect.left() + (cover_rect.width() - size) // 2,
                cover_rect.top() + (cover_rect.height() - size) // 2,
                glyph)
        elif not pm.isNull():
            target = pm.size().scaled(cover_rect.size(), Qt.KeepAspectRatio)
            x = cover_rect.left() + (cover_rect.width() - target.width()) // 2
            y = cover_rect.top() + (cover_rect.height() - target.height())
            dest = QRect(x, y, target.width(), target.height())
            painter.setPen(QPen(QColor(0, 0, 0, 60)))
            painter.setBrush(Qt.NoBrush)
            painter.drawPixmap(dest, pm)
            painter.drawRect(dest.adjusted(0, 0, -1, -1))
            if is_dir:
                # Sonst ist ein Ordner von einem Heft nicht zu unterscheiden.
                badge = QRect(dest.left() + 4, dest.top() + 4, 22, 22)
                painter.setPen(Qt.NoPen)
                painter.setBrush(QColor(0, 0, 0, 130))
                painter.drawRoundedRect(badge, 5, 5)
                painter.drawPixmap(badge.adjusted(3, 3, -3, -3),
                                   _folder_badge().pixmap(16, 16))

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

        status = index.data(STATUS_ROLE)
        if status is not None:
            has_tags, source = status
            dot = QRect(cover_rect.right() - 13, cover_rect.top() + 3, 10, 10)
            painter.setPen(QPen(QColor(255, 255, 255, 200), 1.5))
            if has_tags:
                painter.setBrush(SOURCE_COLORS.get(source, SOURCE_COLORS["manual"]))
                painter.drawEllipse(dot)
            else:
                painter.setBrush(QColor(200, 90, 60))
                painter.drawEllipse(dot)
                painter.setPen(QPen(QColor(255, 255, 255), 1.6))
                painter.drawLine(dot.center().x(), dot.top() + 2,
                                 dot.center().x(), dot.bottom() - 3)

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


#: Ab so vielen Treffern im selben Ordner lohnt ein eigener Reihen-Treffer.
SERIES_HIT_MIN = 2


def _group_hits(hits: list[Path]) -> tuple[list[Path], list[Path], dict[str, str]]:
    """Treffer nach Ordner buendeln: erst die Reihen, dann die Ausgaben.

    Wer nach "batman" sucht, will meist die Reihe, nicht 40 Einzelhefte -
    beides zu zeigen ist nuetzlicher als nur eines davon.
    """
    from collections import Counter

    counts = Counter(hit.parent for hit in hits)
    folders = sorted((folder for folder, number in counts.items()
                      if number >= SERIES_HIT_MIN),
                     key=lambda f: (-counts[f], f.name.casefold()))
    subtitles = {str(folder): _("{count} Hefte").format(count=counts[folder])
                 for folder in folders}
    return folders, folders + hits, subtitles


_badge_cache: dict[str, QIcon] = {}


def _folder_badge() -> QIcon:
    """Weisses Ordnersymbol fuer die Ecke einer Ordner-Vorschau."""
    if "badge" not in _badge_cache:
        from .icons import PATHS, _TEMPLATE
        from PySide6.QtCore import QByteArray, QRectF
        from PySide6.QtGui import QPainter as _P
        from PySide6.QtSvg import QSvgRenderer

        svg = _TEMPLATE.format(color="#ffffff", body=PATHS["folder"])
        renderer = QSvgRenderer(QByteArray(svg.encode()))
        pixmap = QPixmap(32, 32)
        pixmap.fill(Qt.transparent)
        painter = _P(pixmap)
        renderer.render(painter, QRectF(pixmap.rect()))
        painter.end()
        _badge_cache["badge"] = QIcon(pixmap)
    return _badge_cache["badge"]


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
        #: Pfad -> (hat Tags, Quelle); leer heisst "nicht im Index".
        self.status: dict[str, tuple[bool, str | None]] = {}
        #: Pfad -> Text unter dem Namen; sonst greift show_parent.
        self.subtitles: dict[str, str] = {}
        #: Reine Ordneransicht - dann reichen niedrigere Kacheln.
        self.compact = False
        #: Ordner mit dem Cover ihres ersten Comics zeigen.
        self.folder_covers = True
        #: Einmal ermittelt statt bei jedem Neuzeichnen - auf Netzlaufwerken
        #: ist jedes is_dir() ein Netzzugriff.
        self._dirs: set[str] = set()
        loader.ready.connect(self._on_thumb)

    def set_entries(self, entries: list[Path], show_parent: bool = False,
                    status: dict[str, tuple[bool, str | None]] | None = None,
                    dirs: set[str] | None = None,
                    subtitles: dict[str, str] | None = None) -> None:
        self.beginResetModel()
        self.entries = entries
        self.show_parent = show_parent
        self.status = status or {}
        self.subtitles = subtitles or {}
        # Der Aufrufer weiss meist schon, was Ordner sind; sonst einmal fragen.
        self._dirs = dirs if dirs is not None else {
            str(p) for p in entries if p.is_dir()}
        self.compact = (bool(entries) and not self.folder_covers
                        and len(self._dirs) == len(entries))
        self.endResetModel()

    def is_dir(self, path: Path) -> bool:
        return str(path) in self._dirs

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
            own = self.subtitles.get(str(p))
            if own is not None:
                return own
            return p.parent.name if self.show_parent else None
        if role == IS_DIR_ROLE:
            return self.is_dir(p)
        if role == STATUS_ROLE:
            return None if self.is_dir(p) else self.status.get(str(p))
        if role == Qt.DecorationRole:
            if self.is_dir(p):
                if not self.folder_covers:
                    return self.folder_icon
                pm = self.loader.get(p)
                if pm is None or pm.isNull():
                    return self.folder_icon
                return QIcon(pm)
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
        # Das Lesen der Tags geht auf die Datei - auf Netzlaufwerken kostet
        # das bis zu 200 ms. Ohne Verzoegerung friert das Fenster bei jedem
        # Klick ein und schnelle Klickfolgen (Klick, Shift-Klick) geraten
        # durcheinander.
        self._meta_timer = QTimer(self)
        self._meta_timer.setSingleShot(True)
        self._meta_timer.setInterval(150)
        self._meta_timer.timeout.connect(self._load_metadata_now)
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
        self.tree.setContextMenuPolicy(Qt.CustomContextMenu)
        self.tree.customContextMenuRequested.connect(self._tree_menu)
        self.tree.clicked.connect(self._tree_selected)
        # currentChanged deckt auch Pfeiltasten und Pos1/Ende ab -
        # clicked allein reagiert nur auf die Maus.
        self.tree.selectionModel().currentChanged.connect(
            lambda current, _previous: self._tree_selected(current))

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
        fav_header.setStyleSheet("font-weight:600; padding:6px 4px 2px 4px;")
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
        self.collection_box = QComboBox()
        self.collection_box.setMinimumWidth(150)
        self.collection_box.setToolTip(
            _("In welcher Sammlung gesucht wird"))
        self.collection_box.activated.connect(self._collection_chosen)
        bar.addWidget(self.search_toggle)
        bar.addWidget(self.collection_box)
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
        self.refresh_collections()

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
            "untagged": act("Ungetaggte anzeigen", "Ctrl+U", self.show_untagged),
            "series": act("Reihen …", "Ctrl+E", self.show_series, "index"),
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
        menu.addAction(a["untagged"])
        menu.addAction(a["series"])
        menu.addSeparator()
        self.action_folder_covers = QAction(_("Ordner mit Cover anzeigen"), self)
        self.action_folder_covers.setCheckable(True)
        self.action_folder_covers.setChecked(
            str(self.settings.value("folder_covers", "true")).lower() != "false")
        self.action_folder_covers.toggled.connect(self._toggle_folder_covers)
        menu.addAction(self.action_folder_covers)
        self.model.folder_covers = self.action_folder_covers.isChecked()
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
        self.collection_box.setVisible(on)
        self.filter_edit.setPlaceholderText(
            _(SEARCH_PLACEHOLDER if on else FILTER_PLACEHOLDER))
        # Ordnerfilter und Sammlungssuche haben verschiedene Abfragesprachen;
        # ein stehengebliebenes "getaggt:nein" wuerde sonst als Dateiname gesucht.
        self.filter_edit.blockSignals(True)
        self.filter_edit.clear()
        self.filter_edit.blockSignals(False)
        self.filter_edit.setFocus()
        self.refresh()

    def show_series(self) -> None:
        """Reihen-Ansicht: was fehlt, und wie sicher das ist."""
        SeriesDialog(self.index, self.settings, self.active_collection, self).exec()

    def show_untagged(self) -> None:
        """Alle Comics der aktiven Sammlung ohne Tags auflisten."""
        if not self.search_mode:
            self.search_toggle.setChecked(True)
        self.filter_edit.setText("getaggt:nein")
        self.filter_edit.setFocus()

    def _toggle_folder_covers(self, on: bool) -> None:
        self.settings.setValue("folder_covers", on)
        self.model.folder_covers = on
        self.loader.clear_queue()
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
        self.model.set_entries(dirs + comics,
                               status=self.index.status_for(comics),
                               dirs={str(p) for p in dirs})
        self.meta.clear()
        status = self.model.status
        untagged = sum(1 for c in comics if not status.get(str(c), (False, None))[0])
        message = _("{comics} Comics, {dirs} Ordner in {path}").format(
            comics=len(comics), dirs=len(dirs), path=self.current_dir)
        if comics and untagged:
            message += "  ·  " + _("{count} ohne Tags").format(count=untagged)
        self.statusBar().showMessage(message)

    def _refresh_search(self) -> None:
        query = self.filter_edit.text().strip()
        collection = self.active_collection
        indexed = self.index.count(collection)
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
            hits = self.index.search(query, collection=collection)
        except Exception as exc:  # noqa: BLE001
            self.statusBar().showMessage(
                _("Suche fehlgeschlagen: {error}").format(error=exc), 6000)
            return
        folders, entries, subtitles = _group_hits(hits)
        self.model.set_entries(entries, show_parent=True,
                               status=self.index.status_for(hits),
                               dirs={str(f) for f in folders},
                               subtitles=subtitles)
        self.meta.clear()
        message = _("{hits} Treffer von {total} indizierten Comics").format(
            hits=len(hits), total=indexed)
        if folders:
            message = _("{series} Reihen und {hits} Ausgaben von {total} "
                        "indizierten Comics").format(
                series=len(folders), hits=len(hits), total=indexed)
        self.statusBar().showMessage(message)

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
        if len(paths) == 1:
            # Erst wenn die Auswahl steht, sonst liest jeder Zwischenschritt
            # einer Mehrfachauswahl unnoetig eine Datei.
            self._meta_timer.start()
        else:
            self._meta_timer.stop()
            self.meta.clear()
        self._update_favorite_action()

    def _load_metadata_now(self) -> None:
        paths = [p for p in self.selected_paths() if p.is_file()]
        self.meta.load(paths[0] if len(paths) == 1 else None)

    def _tree_menu(self, pos) -> None:
        """Kontextmenue fuer den rechtsgeklickten Ordner - nicht fuer den
        gerade ausgewaehlten."""
        index = self.tree.indexAt(pos)
        if not index.isValid():
            return
        menu = self.build_tree_menu(Path(self.fs_model.filePath(index)), index)
        menu.exec(self.tree.viewport().mapToGlobal(pos))

    def build_tree_menu(self, folder: Path, index: QModelIndex) -> QMenu:
        menu = QMenu(self.tree)

        def add(text, slot, icon=None):
            action = QAction(_(text), menu)
            if icon:
                action.setIcon(app_icon(icon))
            action.triggered.connect(slot)
            menu.addAction(action)
            return action

        add("Oeffnen", lambda: self.set_directory(folder), "folder")
        menu.addSeparator()
        if self.favorites.contains(folder):
            add("Aus Favoriten entfernen",
                lambda: self._set_favorite(folder, False), "star")
        else:
            add("Zu Favoriten hinzufuegen",
                lambda: self._set_favorite(folder, True), "star_off")
        menu.addSeparator()
        add("Hier automatisch taggen", lambda: self._tag_folder(folder), "tag")
        add("Neuer Ordner …", lambda: self._new_folder_in(folder), "folder_new")
        menu.addSeparator()
        add("Aktualisieren", lambda: self._reload_tree(index), "refresh")
        return menu

    def _set_favorite(self, folder: Path, add: bool) -> None:
        if add:
            self.favorites.add(folder)
        else:
            self.favorites.remove(folder)
        self.refresh_favorites()

    def _tag_folder(self, folder: Path) -> None:
        self.set_directory(folder)
        self.view.clearSelection()
        self.auto_tag()

    def _new_folder_in(self, folder: Path) -> None:
        name, ok = QInputDialog.getText(self, _("Neuer Ordner"), _("Name:"))
        if not ok or not name.strip():
            return
        try:
            (folder / name.strip()).mkdir()
        except OSError as exc:
            QMessageBox.critical(self, _("Neuer Ordner"), str(exc))
            return
        self._reload_tree(self.fs_model.index(str(folder)))
        if folder == self.current_dir:
            self.refresh()

    def _reload_tree(self, index: QModelIndex) -> None:
        self.fs_model.setRootPath("")
        self.tree.collapse(index)
        self.tree.expand(index)

    def _tree_selected(self, index: QModelIndex) -> None:
        if not index.isValid():
            return
        path = Path(self.fs_model.filePath(index))
        # set_directory setzt selbst den Baumeintrag - ohne diese Bremse
        # riefe das Signal sich endlos gegenseitig auf.
        if path == self.current_dir:
            return
        self.set_directory(path)

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
            # Unter Wayland darf sich ein Fenster nicht selbst nach vorn
            # holen - raise() bleibt wirkungslos. showNormal() holt es
            # wenigstens aus der Minimierung zurueck.
            window = self.readers[key]
            window.showNormal()
            window.raise_()
            window.activateWindow()
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
        self.refresh_collections()
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
        CollectionsDialog(self.index, self.current_dir, self).exec()
        self.refresh_collections()
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

    # --- Sammlungen ---------------------------------------------------
    def refresh_collections(self) -> None:
        """Auswahlfeld neu befuellen und die gemerkte Sammlung wiederherstellen."""
        wanted = self.settings.value("active_collection", "")
        self.collection_box.blockSignals(True)
        self.collection_box.clear()
        names = [c.name for c in self.index.collections()]
        for name in names:
            self.collection_box.addItem(name, name)
        self.collection_box.addItem(_("Alle Sammlungen"), "")
        self.collection_box.insertSeparator(self.collection_box.count())
        self.collection_box.addItem(_("Sammlungen verwalten …"), "__manage__")
        index = self.collection_box.findData(wanted if wanted in names else "")
        self.collection_box.setCurrentIndex(max(0, index))
        self.collection_box.blockSignals(False)
        self.collection_box.setVisible(self.search_mode)

    @property
    def active_collection(self) -> str | None:
        """None heisst: ueber alle Sammlungen suchen."""
        data = self.collection_box.currentData()
        return data or None

    def _collection_chosen(self, _index: int) -> None:
        if self.collection_box.currentData() == "__manage__":
            self.refresh_collections()   # Auswahl zuruecksetzen
            self.edit_index()
            return
        self.settings.setValue("active_collection", self.active_collection or "")
        self.refresh()

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
        self.refresh_collections()
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
        self.refresh_collections()

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
        self.refresh_collections()

    def prune_favorites(self) -> None:
        removed = self.favorites.prune_missing()
        self.refresh_favorites()
        self.refresh_collections()
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
                self.index.upsert(path, comic.read_metadata(), comic.page_count,
                                  self.index.collection_for(path))
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
        self._stop_pending_threads()
        super().closeEvent(event)

    def _stop_pending_threads(self) -> None:
        """Abgebrochene Tag-Laeufe beenden, bevor Qt ihre Threads einsammelt.

        Sonst stuerzt Qt beim Beenden ab ("QThread: Destroyed while thread is
        still running"). Gewartet wird begrenzt - haengt eine Netzabfrage noch,
        soll das Schliessen trotzdem durchgehen.
        """
        pending = getattr(self, "_pending_threads", [])
        for thread, worker in list(pending):
            if worker is not None:
                worker.stop()
        for thread, _worker in list(pending):
            thread.quit()
            thread.wait(3000)
        pending.clear()

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
