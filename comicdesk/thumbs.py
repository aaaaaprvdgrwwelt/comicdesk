"""Cover-Thumbnails: Hintergrund-Erzeugung mit Cache auf der Platte."""
from __future__ import annotations

import hashlib
import os
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QImage, QPixmap

from deskkit.thumbs import ThumbLoader as _ThumbLoader

from . import archive
from .imaging import load_image

THUMB_SIZE = 256


def cache_dir() -> Path:
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


def _load(path_str: str) -> QImage:
    path = Path(path_str)
    img = QImage()
    cache = _cache_path(path)
    if cache.exists():
        img.load(str(cache))
    if img.isNull():
        data = archive.cover_bytes(path)
        if data:
            raw = load_image(data)
            if not raw.isNull():
                img = raw.scaled(
                    THUMB_SIZE, THUMB_SIZE,
                    Qt.KeepAspectRatio, Qt.SmoothTransformation,
                )
                try:
                    img.save(str(cache), "PNG")
                except Exception:
                    pass
    return img


class ThumbLoader(_ThumbLoader):
    """Erzeugt Thumbnails nebenlaeufig und meldet sie per Signal."""

    def __init__(self, parent=None):
        super().__init__(_load, parent)

    def get(self, path: Path) -> QPixmap | None:
        return super().get(str(path))

    def forget(self, path: Path) -> None:
        """Zwischenspeicher fuer eine Datei verwerfen - sie hat sich geaendert."""
        super().forget(str(path))
