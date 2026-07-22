"""ComicDesk - Dateimanager fuer Comics."""
from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtWidgets import QApplication

from PySide6.QtCore import QSettings

from .i18n import set_language
from .mainwindow import MainWindow


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("ComicDesk")
    app.setOrganizationName("comicdesk")
    set_language(QSettings("comicdesk", "comicdesk").value("language", "auto"))
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
