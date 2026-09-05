"""ComicDesk - Dateimanager fuer Comics."""
from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtCore import (
    QSettings, QtMsgType, qInstallMessageHandler, qVersion,
)
from PySide6.QtWidgets import QApplication

from deskkit import theme

from .appicon import icon as app_icon
from .i18n import set_language
from .mainwindow import MainWindow


#: Bekannte, folgenlose Meldungen. Nur genau diese werden geschluckt - alles
#: andere bleibt sichtbar.
#:
#: * libpng: Scanner schreiben gern unzulaessige PNG-Schluesselwoerter
#:   ("EPSON  sRGB"). Qt laedt das Bild trotzdem korrekt, meldet es aber pro
#:   Datei.
#: * "This plugin ...": unter Wayland verbietet das Protokoll, was X11 erlaubte
#:   (Maus greifen, Fenster nach vorn holen). Qt meldet das bei jedem Versuch;
#:   aendern laesst es sich in der Anwendung nicht.
QUIET = (
    "libpng warning",
    "This plugin supports grabbing the mouse only for popup windows",
    "This plugin does not support grabbing the keyboard",
    "This plugin does not support propagateSizeHints()",
    "This plugin does not support raise()",
)


def _quiet_libpng(mode, context, message: str) -> None:
    if any(noise in message for noise in QUIET):
        return
    stream = sys.stderr if mode in (QtMsgType.QtWarningMsg,
                                    QtMsgType.QtCriticalMsg,
                                    QtMsgType.QtFatalMsg) else sys.stdout
    print(message, file=stream)


def selftest() -> int:
    """Kurzer Start ohne Fenster - fuer die Pruefung fertiger Pakete.

    Ein Paket, dem eine Bibliothek fehlt, stuerzt sonst erst beim Nutzer ab.
    Hier faellt es beim Bauen auf.
    """
    import os

    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    zeilen: list[str] = []

    def sag(text: str) -> None:
        zeilen.append(text)
        # Im Fenstermodus hat PyInstaller keine Ausgabe - dann faengt die
        # Datei am Ende alles auf.
        if sys.stdout is not None:
            print(text)

    app = QApplication(sys.argv[:1])
    theme.apply(app)
    app.setWindowIcon(app_icon())
    from . import archive
    from .imaging import load_image
    from .recompress import available_formats

    fenster = MainWindow()
    fenster.close()
    formate = [f.label for f in available_formats()]
    sieben = archive.sevenzip_binary()
    sag(f"Qt:          {qVersion()}")
    sag(f"Bildformate: {', '.join(formate)}")
    sag(f"7z:          {sieben or 'nicht gefunden (CBR/CB7 fallen aus)'}")
    sag(f"PDF:         {'ok' if _pdf_ok() else 'FEHLT'}")
    sag(f"Bildladen:   {'ok' if load_image(b'') is not None else 'FEHLT'}")
    fehlt = [name for name, da in (("PDF", _pdf_ok()),
                                   ("WebP", "WebP" in formate),
                                   ("7z", bool(sieben))) if not da]
    sag("Fehlt: " + ", ".join(fehlt) if fehlt else "Selbsttest bestanden.")
    try:
        Path("selftest.log").write_text("\n".join(zeilen) + "\n", "utf-8")
    except OSError:
        pass
    return 1 if fehlt else 0


def _pdf_ok() -> bool:
    try:
        import pymupdf  # noqa: F401
    except Exception:  # noqa: BLE001
        return False
    return True


def main() -> int:
    if "--selftest" in sys.argv:
        return selftest()
    qInstallMessageHandler(_quiet_libpng)
    app = QApplication(sys.argv)
    app.setApplicationName("ComicDesk")
    app.setOrganizationName("comicdesk")
    set_language(QSettings("comicdesk", "comicdesk").value("language", "auto"))
    theme.apply(app)
    app.setWindowIcon(app_icon())
    app.setDesktopFileName("comicdesk")
    win = MainWindow()
    if len(sys.argv) > 1:
        target = Path(sys.argv[1]).expanduser()
        if target.is_dir():
            win.set_directory(target)
        elif target.is_file():
            win.set_directory(target.parent)
            win.open_comic(target)
    win.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
