"""Programmsymbol.

Zwei Zeichnungen: unter 32 Pixel zerfaellt die ausfuehrliche Fassung zu Brei,
deshalb gibt es dafuer eine vereinfachte. Qt waehlt anhand der eingebetteten
Groessen selbst die passende aus.
"""
from __future__ import annotations

from pathlib import Path

from PySide6.QtGui import QIcon

ASSETS = Path(__file__).parent / "assets"
DETAILED = ASSETS / "comicdesk.svg"
SIMPLE = ASSETS / "comicdesk-small.svg"

SMALL_SIZES = (16, 22, 24, 32)
LARGE_SIZES = (48, 64, 128, 256, 512)

_cached: QIcon | None = None


def icon() -> QIcon:
    global _cached
    if _cached is not None:
        return _cached
    result = QIcon()
    simple, detailed = QIcon(str(SIMPLE)), QIcon(str(DETAILED))
    for size in SMALL_SIZES:
        result.addPixmap(simple.pixmap(size, size))
    for size in LARGE_SIZES:
        result.addPixmap(detailed.pixmap(size, size))
    _cached = result
    return result


def install(target: Path | None = None) -> list[Path]:
    """PNGs ins Icon-Thema legen, damit Menue und Fensterleiste sie finden."""
    base = target or (Path.home() / ".local" / "share" / "icons" / "hicolor")
    written: list[Path] = []
    simple, detailed = QIcon(str(SIMPLE)), QIcon(str(DETAILED))
    for size in SMALL_SIZES + LARGE_SIZES:
        source = simple if size in SMALL_SIZES else detailed
        folder = base / f"{size}x{size}" / "apps"
        folder.mkdir(parents=True, exist_ok=True)
        path = folder / "comicdesk.png"
        source.pixmap(size, size).save(str(path), "PNG")
        written.append(path)
    scalable = base / "scalable" / "apps"
    scalable.mkdir(parents=True, exist_ok=True)
    target_svg = scalable / "comicdesk.svg"
    target_svg.write_bytes(DETAILED.read_bytes())
    written.append(target_svg)
    return written


if __name__ == "__main__":
    import sys

    from PySide6.QtWidgets import QApplication

    QApplication(sys.argv)
    for path in install():
        print(path)
