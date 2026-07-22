"""Cover-Thumbnails: Hintergrund-Erzeugung mit Cache auf der Platte."""
from __future__ import annotations

import hashlib
from pathlib import Path

from PySide6.QtCore import QObject, QRunnable, Qt, QThreadPool, Signal
from PySide6.QtGui import QImage, QPixmap

from . import archive

THUMB_SIZE = 256


def cache_dir() -> Path:
    import os

    base = os.environ.get("XDG_CACHE_HOME") or (Path.home() / ".cache")
    d = Path(base) / "comicdesk" / "thumbs"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _cache_path(path: Path) -> Path:
    try:
        st = path.stat()
        key = f"{path.resolve()}|{st.st_mtime_ns}|{st.st_size}|{THUMB_SIZE}"
        if path.is_dir():
            # Ordner-Zeitstempel aendert sich nur beim Hinzufuegen/Loeschen -
            # genau dann soll die Vorschau neu bestimmt werden.
            key += "|dir"
    except OSError:
        key = str(path)
    return cache_dir() / (hashlib.sha1(key.encode()).hexdigest() + ".png")


class _Signals(QObject):
    done = Signal(str, QImage)


class _Job(QRunnable):
    def __init__(self, path: Path, signals: _Signals):
        super().__init__()
        self.path = path
        self.signals = signals
        self.setAutoDelete(True)

    def run(self) -> None:
        img = QImage()
        cache = _cache_path(self.path)
        if cache.exists():
            img.load(str(cache))
        if img.isNull():
            data = archive.cover_bytes(self.path)
            if data:
                raw = QImage()
                if raw.loadFromData(data):
                    img = raw.scaled(
                        THUMB_SIZE, THUMB_SIZE,
                        Qt.KeepAspectRatio, Qt.SmoothTransformation,
                    )
                    try:
                        img.save(str(cache), "PNG")
                    except Exception:
                        pass
        self.signals.done.emit(str(self.path), img)


class ThumbLoader(QObject):
    """Erzeugt Thumbnails nebenlaeufig und meldet sie per Signal."""

    ready = Signal(str, QPixmap)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._pool = QThreadPool(self)
        self._pool.setMaxThreadCount(max(2, QThreadPool.globalInstance().maxThreadCount() - 1))
        self._signals = _Signals(self)
        self._signals.done.connect(self._on_done)
        self._pending: set[str] = set()
        self._cache: dict[str, QPixmap] = {}

    def get(self, path: Path) -> QPixmap | None:
        key = str(path)
        if key in self._cache:
            return self._cache[key]
        if key not in self._pending:
            self._pending.add(key)
            self._pool.start(_Job(path, self._signals))
        return None

    def forget(self, path: Path) -> None:
        """Zwischenspeicher fuer eine Datei verwerfen - sie hat sich geaendert."""
        self._cache.pop(str(path), None)
        self._pending.discard(str(path))

    def clear_queue(self) -> None:
        self._pool.clear()
        self._pending.clear()

    def _on_done(self, key: str, img: QImage) -> None:
        self._pending.discard(key)
        pm = QPixmap.fromImage(img) if not img.isNull() else QPixmap()
        self._cache[key] = pm
        self.ready.emit(key, pm)
