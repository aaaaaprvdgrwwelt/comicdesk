"""Startskript fuer die gepackten Fassungen.

comicdesk/__main__.py benutzt relative Importe. Als Startskript von
PyInstaller gehoert es zu keinem Paket - dann scheitert schon die erste
Zeile. Dieser Umweg importiert das Paket ganz normal.
"""
import multiprocessing
import sys

from comicdesk.__main__ import main

if __name__ == "__main__":
    # Ohne das oeffnet jeder Unterprozess unter Windows ein neues Fenster.
    multiprocessing.freeze_support()
    sys.exit(main())
