"""ComicDesk - Dateimanager fuer Comics."""
from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtCore import QSettings, QtMsgType, qInstallMessageHandler
from PySide6.QtWidgets import QApplication

from .appicon import icon as app_icon
from .i18n import set_language
from .mainwindow import MainWindow
from . import theme


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


def main() -> int:
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
