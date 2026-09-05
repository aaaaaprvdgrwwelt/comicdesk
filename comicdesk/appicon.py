"""Programmsymbol.

Zwei Zeichnungen: unter 32 Pixel zerfaellt die ausfuehrliche Fassung zu Brei,
deshalb gibt es dafuer eine vereinfachte. Qt waehlt anhand der eingebetteten
Groessen selbst die passende aus.
"""
from __future__ import annotations

from pathlib import Path

from deskkit.appicon import build_icon
from deskkit.appicon import install as _install

ASSETS = Path(__file__).parent / "assets"
DETAILED = ASSETS / "comicdesk.svg"
SIMPLE = ASSETS / "comicdesk-small.svg"

SMALL_SIZES = (16, 22, 24, 32)
LARGE_SIZES = (48, 64, 128, 256, 512)
_SIZE_TO_SVG = {
    **{size: SIMPLE for size in SMALL_SIZES},
    **{size: DETAILED for size in LARGE_SIZES},
}

_cached = None


def icon():
    global _cached
    if _cached is None:
        _cached = build_icon(_SIZE_TO_SVG)
    return _cached


def install(target: Path | None = None) -> list[Path]:
    return _install(_SIZE_TO_SVG, "comicdesk", DETAILED, target)


if __name__ == "__main__":
    import sys

    from PySide6.QtWidgets import QApplication

    QApplication(sys.argv)
    for path in install():
        print(path)
