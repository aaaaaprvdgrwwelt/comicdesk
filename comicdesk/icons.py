"""Eigene Icons als SVG.

Icon-Themes gibt es unter Windows und macOS nicht und unter Linux nicht
zuverlaessig. Deshalb werden die paar gebrauchten Symbole selbst gezeichnet.
Sie uebernehmen die Textfarbe der Palette und funktionieren damit in hellen
wie dunklen Themes.
"""
from __future__ import annotations

from PySide6.QtCore import QByteArray, QRectF, Qt
from PySide6.QtGui import QColor, QIcon, QPainter, QPalette, QPixmap
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtWidgets import QApplication

#: Strichzeichnungen auf einem 24x24-Raster.
PATHS = {
    "up": '<path d="M12 19V6M6 12l6-6 6 6"/>',
    "refresh": '<path d="M20 12a8 8 0 1 1-2.3-5.6"/><path d="M20 4v4h-4"/>',
    "read": '<path d="M4 5.5A2 2 0 0 1 6 4h4.5a2 2 0 0 1 2 2v13a1.5 1.5 0 0 0-1.5-1.5H6a2 2 0 0 1-2-2z"/>'
            '<path d="M20 5.5A2 2 0 0 0 18 4h-4.5a2 2 0 0 0-2 2v13a1.5 1.5 0 0 1 1.5-1.5H18a2 2 0 0 0 2-2z"/>',
    "rename": '<path d="M4 20h5l9.5-9.5a2.1 2.1 0 0 0-3-3L6 17z"/><path d="M14.5 6.5l3 3"/>',
    "delete": '<path d="M4 7h16"/><path d="M9 7V5a1 1 0 0 1 1-1h4a1 1 0 0 1 1 1v2"/>'
              '<path d="M6 7l1 12a2 2 0 0 0 2 2h6a2 2 0 0 0 2-2l1-12"/>'
              '<path d="M10 11v6M14 11v6"/>',
    "tag": '<path d="M11 3H4a1 1 0 0 0-1 1v7l9.5 9.5a1.5 1.5 0 0 0 2.1 0l6-6a1.5 1.5 0 0 0 0-2.1z"/>'
           '<circle cx="7.5" cy="7.5" r="1.4"/>',
    "search": '<circle cx="10.5" cy="10.5" r="6"/><path d="M15 15l5 5"/>',
    "folder_new": '<path d="M3 7a1 1 0 0 1 1-1h5l2 2h8a1 1 0 0 1 1 1v9a1 1 0 0 1-1 1H4a1 1 0 0 1-1-1z"/>'
                  '<path d="M12 11v5M9.5 13.5h5"/>',
    "settings": '<circle cx="12" cy="12" r="3"/>'
                '<path d="M12 2.5v3M12 18.5v3M21.5 12h-3M5.5 12h-3'
                'M18.7 5.3l-2.1 2.1M7.4 16.6l-2.1 2.1M18.7 18.7l-2.1-2.1M7.4 7.4L5.3 5.3"/>',
    "left": '<path d="M19 12H6M12 6l-6 6 6 6"/>',
    "right": '<path d="M5 12h13M12 6l6 6-6 6"/>',
    "first": '<path d="M20 12H8M14 6l-6 6 6 6"/><path d="M4.5 5v14"/>',
    "last": '<path d="M4 12h12M10 6l6 6-6 6"/><path d="M19.5 5v14"/>',
    "undo": '<path d="M4 9h11a5 5 0 0 1 0 10h-6"/><path d="M8 5L4 9l4 4"/>',
    "save": '<path d="M5 4h11l3 3v13H5z"/><path d="M8 4v5h7V4"/><path d="M8 20v-6h8v6"/>',
    "star": '<path d="M12 3.5l2.6 5.3 5.9.9-4.3 4.1 1 5.8-5.2-2.7-5.2 2.7 1-5.8-4.3-4.1 5.9-.9z"/>',
    "star_off": '<path d="M12 3.5l2.6 5.3 5.9.9-4.3 4.1 1 5.8-5.2-2.7-5.2 2.7 1-5.8-4.3-4.1 5.9-.9z" '
                'stroke-dasharray="2.5 2"/>',
    "folder": '<path d="M3 7a1 1 0 0 1 1-1h5l2 2h8a1 1 0 0 1 1 1v9a1 1 0 0 1-1 1H4a1 1 0 0 1-1-1z"/>',
    "index": '<path d="M4 6h16M4 12h16M4 18h10"/><circle cx="18.5" cy="18" r="3"/>',
    # --- Reader
    "fit_page": '<rect x="5" y="3.5" width="14" height="17" rx="1"/>'
                '<path d="M9 8l3-2.5L15 8M9 16l3 2.5 3-2.5"/>',
    "fit_width": '<rect x="5" y="3.5" width="14" height="17" rx="1"/>'
                 '<path d="M8 9L5.5 12 8 15M16 9l2.5 3-2.5 3"/>',
    "fit_height": '<rect x="5" y="3.5" width="14" height="17" rx="1"/>'
                  '<path d="M9 7l3-2.5L15 7M9 17l3 2.5 3-2.5"/>',
    "zoom_in": '<circle cx="10.5" cy="10.5" r="6"/><path d="M15 15l5 5"/>'
               '<path d="M10.5 8v5M8 10.5h5"/>',
    "zoom_out": '<circle cx="10.5" cy="10.5" r="6"/><path d="M15 15l5 5"/>'
                '<path d="M8 10.5h5"/>',
    "double": '<rect x="2.5" y="4" width="8.5" height="16" rx="1"/>'
              '<rect x="13" y="4" width="8.5" height="16" rx="1"/>',
    "manga": '<rect x="2.5" y="4" width="8.5" height="16" rx="1"/>'
             '<rect x="13" y="4" width="8.5" height="16" rx="1"/>'
             '<path d="M11.8 12H6.5M8.6 9.8 6.3 12l2.3 2.2"/>',
    "rotate": '<path d="M20 12a8 8 0 1 0-2.3 5.6"/><path d="M20 20v-4h-4"/>',
    "lens": '<circle cx="10.5" cy="10.5" r="6"/><path d="M15 15l5 5"/>'
            '<path d="M7.6 9a3.8 3.8 0 0 1 2.6-1.8"/>',
    "thumbs": '<rect x="3.5" y="3.5" width="6" height="7" rx="1"/>'
              '<rect x="3.5" y="13.5" width="6" height="7" rx="1"/>'
              '<path d="M13 6h7M13 9.5h5M13 16h7M13 19.5h5"/>',
    "bookmark": '<path d="M7 4h10v16l-5-4-5 4z"/>',
    "fullscreen": '<path d="M4 9V5a1 1 0 0 1 1-1h4M15 4h4a1 1 0 0 1 1 1v4'
                  'M20 15v4a1 1 0 0 1-1 1h-4M9 20H5a1 1 0 0 1-1-1v-4"/>',
    "goto": '<path d="M12 3v14M7 12l5 5 5-5"/>'
            '<path d="M4 21h16" stroke-dasharray="2 3"/>',
    "pages": '<rect x="4" y="3.5" width="12" height="15" rx="1"/>'
             '<path d="M8 21h11a1 1 0 0 0 1-1V8"/>',
}

_TEMPLATE = (
    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" '
    'stroke="{color}" stroke-width="1.7" stroke-linecap="round" '
    'stroke-linejoin="round">{body}</svg>'
)

_cache: dict[tuple[str, str, int], QIcon] = {}


def _text_color() -> QColor:
    app = QApplication.instance()
    if app is None:
        return QColor("#303030")
    return app.palette().color(QPalette.WindowText)


def icon(name: str, size: int = 24) -> QIcon:
    """Icon `name` in Textfarbe. Unbekannte Namen ergeben ein leeres Icon."""
    body = PATHS.get(name)
    if not body:
        return QIcon()
    color = _text_color()
    key = (name, color.name(), size)
    if key in _cache:
        return _cache[key]

    svg = _TEMPLATE.format(color=color.name(), body=body)
    renderer = QSvgRenderer(QByteArray(svg.encode()))
    result = QIcon()
    for scale in (1, 2):
        pixmap = QPixmap(size * scale, size * scale)
        pixmap.fill(Qt.transparent)
        painter = QPainter(pixmap)
        renderer.render(painter, QRectF(pixmap.rect()))
        painter.end()
        pixmap.setDevicePixelRatio(scale)
        result.addPixmap(pixmap)
    _cache[key] = result
    return result
