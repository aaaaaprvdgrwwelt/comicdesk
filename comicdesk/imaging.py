"""Bilddaten laden - auch Formate, die Qt nicht kennt.

Qt liest JPEG, PNG, GIF und WebP, aber kein AVIF und kein JPEG XL. Genau
die tauchen in neueren Sammlungen auf (und der eigene Konverter schreibt
AVIF), deshalb springt fuer unbekannte Daten Pillow ein.
"""
from __future__ import annotations

import io

from PySide6.QtGui import QImage

#: Pillow-Modi, die sich unveraendert nach Qt uebertragen lassen.
_QT_FORMATS = {
    "RGBA": QImage.Format_RGBA8888,
    "RGB": QImage.Format_RGB888,
    "L": QImage.Format_Grayscale8,
}


def load_image(data: bytes) -> QImage:
    """Bild aus Rohdaten. Ein leeres QImage heisst: nicht lesbar."""
    img = QImage()
    if img.loadFromData(data):
        return img
    return _load_with_pillow(data)


def _load_with_pillow(data: bytes) -> QImage:
    try:
        from PIL import Image

        Image.init()
        with Image.open(io.BytesIO(data)) as bild:
            bild.load()
            if bild.mode not in _QT_FORMATS:
                bild = bild.convert("RGBA" if "A" in bild.mode
                                    or bild.mode == "P" else "RGB")
            roh = bild.tobytes()
            # QImage kopiert die Daten nicht - ohne copy() zeigt es auf einen
            # Puffer, den Python jederzeit einsammeln darf.
            return QImage(roh, bild.width, bild.height,
                          len(roh) // bild.height,
                          _QT_FORMATS[bild.mode]).copy()
    except Exception:  # noqa: BLE001
        return QImage()
