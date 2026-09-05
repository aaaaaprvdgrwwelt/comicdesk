"""Antwort-Cache fuer Netz-Quellen: spart Kontingent und macht schnell.

Mechanismus in deskkit.cache - hier nur das App-eigene Cache-Verzeichnis.
"""
from __future__ import annotations

from functools import partial

from deskkit.cache import ResponseCache as _ResponseCache
from deskkit.cache import cache_dir as _cache_dir

cache_dir = partial(_cache_dir, "comicdesk")


class ResponseCache(_ResponseCache):
    def __init__(self, name: str, ttl_days: int = 30):
        super().__init__("comicdesk", name, ttl_days)
