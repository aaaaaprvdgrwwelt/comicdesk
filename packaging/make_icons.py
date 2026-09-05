"""Programmsymbol in die Formate bringen, die Windows und macOS wollen.

Aufruf: python packaging/make_icons.py [Zielordner]

Windows braucht eine .ico mit mehreren Groessen, macOS eine .icns. Beide
entstehen aus denselben zwei SVGs wie das Symbol im Programm - unter 32
Pixel die vereinfachte Zeichnung, darueber die ausfuehrliche.
"""
from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtGui import QImage, QPainter
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtWidgets import QApplication

HIER = Path(__file__).resolve().parent
ASSETS = HIER.parent / "comicdesk" / "assets"
SMALL, LARGE = ASSETS / "comicdesk-small.svg", ASSETS / "comicdesk.svg"

ICO_SIZES = (16, 24, 32, 48, 64, 128, 256)
#: macOS erwartet genau diese Kantenlaengen in der .icns.
ICNS_SIZES = (16, 32, 64, 128, 256, 512, 1024)


def render(size: int) -> QImage:
    quelle = SMALL if size < 32 else LARGE
    bild = QImage(size, size, QImage.Format_ARGB32)
    bild.fill(0)
    maler = QPainter(bild)
    QSvgRenderer(str(quelle)).render(maler)
    maler.end()
    return bild


def write_ico(ziel: Path, tmp: Path) -> None:
    """Alle Groessen in eine .ico - Windows sucht sich die passende.

    Ueber Pillow, weil Qt in eine .ico nur eine einzige Groesse schreibt;
    Windows skalierte den Rest selbst nach, und bei 16 Pixel wird daraus
    Brei - genau dafuer gibt es die vereinfachte Zeichnung.
    """
    from PIL import Image

    tmp.mkdir(parents=True, exist_ok=True)
    bilder = []
    for groesse in ICO_SIZES:
        pfad = tmp / f"ico_{groesse}.png"
        render(groesse).save(str(pfad), "PNG")
        bilder.append(Image.open(pfad).convert("RGBA"))
    bilder[-1].save(ziel, "ICO",
                    sizes=[(b.width, b.height) for b in bilder],
                    append_images=bilder[:-1])


def write_png_set(ordner: Path) -> list[Path]:
    ordner.mkdir(parents=True, exist_ok=True)
    geschrieben = []
    for groesse in ICNS_SIZES:
        pfad = ordner / f"icon_{groesse}x{groesse}.png"
        render(groesse).save(str(pfad), "PNG")
        geschrieben.append(pfad)
        if groesse <= 512:      # @2x-Fassungen fuer Netzhautschirme
            zwei = ordner / f"icon_{groesse}x{groesse}@2x.png"
            render(groesse * 2).save(str(zwei), "PNG")
            geschrieben.append(zwei)
    return geschrieben


def main() -> int:
    app = QApplication(sys.argv)          # noqa: F841 - Qt braucht ihn
    ziel = Path(sys.argv[1]) if len(sys.argv) > 1 else HIER
    ziel.mkdir(parents=True, exist_ok=True)
    write_ico(ziel / "comicdesk.ico", ziel / "ico-teile")
    ordner = write_png_set(ziel / "comicdesk.iconset")
    print(f"geschrieben: {ziel / 'comicdesk.ico'}")
    print(f"geschrieben: {len(ordner)} PNGs in {ziel / 'comicdesk.iconset'}")
    print("Auf macOS daraus die .icns bauen:")
    print(f"  iconutil -c icns {ziel / 'comicdesk.iconset'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
