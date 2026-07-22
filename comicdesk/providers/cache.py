"""Antwort-Cache fuer Netz-Quellen: spart Kontingent und macht schnell."""
from __future__ import annotations

import json
import sqlite3
import threading
import time
from pathlib import Path


def cache_dir() -> Path:
    import os

    base = os.environ.get("XDG_CACHE_HOME") or (Path.home() / ".cache")
    path = Path(base) / "comicdesk"
    path.mkdir(parents=True, exist_ok=True)
    return path


class ResponseCache:
    def __init__(self, name: str, ttl_days: int = 30):
        self.ttl = ttl_days * 86400
        self._con = sqlite3.connect(str(cache_dir() / name), check_same_thread=False)
        self._lock = threading.Lock()
        with self._lock:
            self._con.execute(
                "CREATE TABLE IF NOT EXISTS cache "
                "(key TEXT PRIMARY KEY, ts REAL, body TEXT)")
            self._con.commit()

    def get(self, key: str):
        with self._lock:
            row = self._con.execute(
                "SELECT ts, body FROM cache WHERE key=?", (key,)).fetchone()
        if not row or time.time() - row[0] > self.ttl:
            return None
        try:
            return json.loads(row[1])
        except json.JSONDecodeError:
            return None

    def put(self, key: str, value) -> None:
        with self._lock:
            self._con.execute("INSERT OR REPLACE INTO cache VALUES (?,?,?)",
                              (key, time.time(), json.dumps(value)))
            self._con.commit()
