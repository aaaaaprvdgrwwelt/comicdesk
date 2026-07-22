"""ComicDesk - Dateimanager fuer Comics."""
from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtCore import QSettings, QtMsgType, qInstallMessageHandler
from PySide6.QtWidgets import QApplication

from .i18n import set_language
from .mainwindow import MainWindow
from . import theme


#: Scanner schreiben gern fehlerhafte PNG-Schluesselwoerter ("EPSON  sRGB" -
#: Leerzeichen sind dort nicht erlaubt). Qt laedt das Bild trotzdem korrekt,
#: meldet es aber pro Datei. Nur diese eine Sorte Meldung wird geschluckt.
def _quiet_libpng(mode, context, message: str) -> None:
    if "libpng warning" in message:
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
