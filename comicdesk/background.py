"""Hintergrundlaeufe abbrechen, ohne die Oberflaeche einzufrieren.

Regel fuer alle Dialoge: Schliessen ist immer moeglich. Laeuft noch etwas,
wird abgebrochen und der Thread ausgeklinkt - auf ihn zu warten wuerde das
Fenster einfrieren, und genau daraus wird sonst ein Fenster, das sich nicht
mehr schliessen laesst.
"""
from __future__ import annotations

from PySide6.QtCore import QObject, QThread

#: So lange wird hoechstens gewartet. Danach laeuft der Thread weiter und
#: raeumt sich selbst auf; das Fenster ist sofort weg.
GRACE_MS = 400


def stop_and_detach(dialog, thread: QThread | None, worker: QObject | None,
                    wait_ms: int = GRACE_MS) -> None:
    """Lauf beenden und den Thread beim Elternfenster parken, falls noetig."""
    if thread is None or not thread.isRunning():
        return
    if worker is not None and hasattr(worker, "stop"):
        worker.stop()
    thread.quit()
    if thread.wait(wait_ms):
        return
    parent = dialog.parent() if dialog is not None else None
    if parent is None:
        # Ohne Elternfenster bleibt nur warten - sonst raeumt Qt den noch
        # laufenden Thread ab und stuerzt.
        thread.wait(5000)
        return
    pending = getattr(parent, "_pending_threads", None)
    if pending is None:
        pending = parent._pending_threads = []
    pending.append((thread, worker))
    thread.finished.connect(
        lambda t=thread, w=worker: pending.remove((t, w))
        if (t, w) in pending else None)
