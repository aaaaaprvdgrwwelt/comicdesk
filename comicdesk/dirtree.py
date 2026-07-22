"""Ordnerbaum, der bei den Sammlungen beginnt.

QFileSystemModel kann nur eine Wurzel und faengt sonst bei "/" an - in einem
Comic-Verwalter also mit /bin, /boot, /dev. Dieses Modell zeigt stattdessen
oben die Sammlungen und laedt Unterordner erst beim Aufklappen; das ganze
Dateisystem haengt als letzter Eintrag darunter, falls man doch hin muss.
"""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QAbstractItemModel, QModelIndex, Qt
from PySide6.QtGui import QFont

from .i18n import _
from .icons import icon as app_icon

COLLECTION, DIRECTORY, FILESYSTEM = range(3)


class Node:
    __slots__ = ("kind", "label", "path", "roots", "parent", "children", "row")

    def __init__(self, kind: int, label: str, path: Path | None = None,
                 roots: list[Path] | None = None, parent: "Node | None" = None,
                 row: int = 0):
        self.kind = kind
        self.label = label
        self.path = path
        self.roots = roots or []
        self.parent = parent
        self.row = row
        #: None heisst: noch nicht geladen.
        self.children: list[Node] | None = None

    @property
    def sources(self) -> list[Path]:
        """Verzeichnisse, aus denen sich die Kinder ergeben."""
        if self.path is not None:
            return [self.path]
        return self.roots


def _subdirs(folder: Path) -> list[Path]:
    try:
        entries = [p for p in folder.iterdir()
                   if p.is_dir() and not p.name.startswith(".")]
    except OSError:
        return []
    from . import archive

    return sorted(entries, key=lambda p: archive.natural_key(p.name))


class DirTreeModel(QAbstractItemModel):
    """Sammlungen als Wurzeln, Unterordner beim Aufklappen nachgeladen."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._root = Node(DIRECTORY, "", None)
        self._root.children = []

    # --- Aufbau -------------------------------------------------------
    def set_collections(self, collections, show_filesystem: bool = True) -> None:
        self.beginResetModel()
        children: list[Node] = []
        for entry in collections:
            paths = [Path(r) for r in entry.roots]
            existing = [p for p in paths if p.is_dir()]
            single = existing[0] if len(existing) == 1 else None
            children.append(Node(COLLECTION, entry.name, single, existing,
                                 self._root, len(children)))
        if show_filesystem:
            children.append(Node(FILESYSTEM, _("Ganzes Dateisystem"),
                                 Path("/"), None, self._root, len(children)))
        self._root.children = children
        self.endResetModel()

    # --- Qt-Schnittstelle ---------------------------------------------
    def _node(self, index: QModelIndex) -> Node:
        return index.internalPointer() if index.isValid() else self._root

    def columnCount(self, parent=QModelIndex()) -> int:  # noqa: N802
        return 1

    def rowCount(self, parent=QModelIndex()) -> int:  # noqa: N802
        node = self._node(parent)
        return len(node.children) if node.children is not None else 0

    def index(self, row: int, column: int, parent=QModelIndex()) -> QModelIndex:
        node = self._node(parent)
        if node.children is None or not 0 <= row < len(node.children):
            return QModelIndex()
        return self.createIndex(row, column, node.children[row])

    def parent(self, index: QModelIndex) -> QModelIndex:  # noqa: A003
        node = self._node(index)
        parent = node.parent
        if parent is None or parent is self._root:
            return QModelIndex()
        return self.createIndex(parent.row, 0, parent)

    def hasChildren(self, parent=QModelIndex()) -> bool:  # noqa: N802
        node = self._node(parent)
        if node.children is not None:
            return bool(node.children)
        # Noch nicht geladen: Aufklapppfeil anbieten. Ist der Ordner leer,
        # verschwindet er nach dem ersten Aufklappen von selbst.
        return bool(node.sources)

    def canFetchMore(self, parent=QModelIndex()) -> bool:  # noqa: N802
        return self._node(parent).children is None

    def fetchMore(self, parent=QModelIndex()) -> None:  # noqa: N802
        node = self._node(parent)
        if node.children is not None:
            return
        folders: list[Path] = []
        if node.kind == COLLECTION and node.path is None:
            folders = list(node.roots)          # mehrere Wurzeln: direkt zeigen
        else:
            for source in node.sources:
                folders += _subdirs(source)
        if not folders:
            node.children = []
            return
        self.beginInsertRows(parent, 0, len(folders) - 1)
        node.children = [Node(DIRECTORY, path.name or str(path), path, None,
                              node, row)
                         for row, path in enumerate(folders)]
        self.endInsertRows()

    def data(self, index: QModelIndex, role=Qt.DisplayRole):
        if not index.isValid():
            return None
        node = self._node(index)
        if role == Qt.DisplayRole:
            return node.label
        if role == Qt.ToolTipRole:
            if node.kind == COLLECTION:
                return "\n".join(str(p) for p in node.roots) or node.label
            return str(node.path)
        if role == Qt.DecorationRole:
            return app_icon("index" if node.kind == COLLECTION else "folder")
        if role == Qt.FontRole and node.kind != DIRECTORY:
            font = QFont()
            font.setBold(True)
            return font
        return None

    # --- Hilfen fuer das Hauptfenster ---------------------------------
    def path_at(self, index: QModelIndex) -> Path | None:
        node = self._node(index)
        return node.path if index.isValid() else None

    def collection_at(self, index: QModelIndex) -> str | None:
        """Zu welcher Sammlung gehoert dieser Eintrag?"""
        node = self._node(index)
        while node is not None and node is not self._root:
            if node.kind == COLLECTION:
                return node.label
            node = node.parent
        return None

    def index_for(self, path: Path) -> QModelIndex:
        """Eintrag zu einem Pfad suchen und den Weg dorthin nachladen."""
        path = Path(path)
        if self._root.children is None:
            return QModelIndex()
        for top in self._root.children:
            start = self._index_of(top)
            found = self._descend(start, top, path)
            if found.isValid():
                return found
        return QModelIndex()

    def _index_of(self, node: Node) -> QModelIndex:
        if node.parent is None:
            return QModelIndex()
        return self.createIndex(node.row, 0, node)

    def _descend(self, index: QModelIndex, node: Node, target: Path) -> QModelIndex:
        if node.path is not None and node.path == target:
            return index
        bases = node.sources
        if not any(_within(target, base) for base in bases):
            return QModelIndex()
        if node.children is None:
            self.fetchMore(index)
        for child in node.children or []:
            found = self._descend(self._index_of(child), child, target)
            if found.isValid():
                return found
        return QModelIndex()

    def refresh(self, index: QModelIndex) -> None:
        """Kinder eines Eintrags verwerfen, damit sie neu gelesen werden."""
        node = self._node(index)
        if node.children is None:
            return
        if node.children:
            self.beginRemoveRows(index, 0, len(node.children) - 1)
            node.children = None
            self.endRemoveRows()
        else:
            node.children = None


def _within(path: Path, base: Path) -> bool:
    if path == base:
        return True
    try:
        path.relative_to(base)
    except ValueError:
        return False
    return True
