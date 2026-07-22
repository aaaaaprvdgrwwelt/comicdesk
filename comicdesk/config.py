"""Einstellungen fuer die Metadaten-Quellen, gehalten in QSettings."""
from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtCore import QSettings

from .autotag import DEFAULT_THRESHOLD, AutoTagConfig
from .providers.base import MetadataProvider
from .providers.anilist import AniListProvider
from .providers.comicvine import ComicVineProvider
from .providers.gcd import GcdProvider


def _bool(value, default: bool) -> bool:
    if value is None:
        return default
    return str(value).lower() in ("1", "true", "yes")


@dataclass
class TaggerSettings:
    comicvine_key: str = ""
    use_comicvine: bool = True
    gcd_path: str = ""
    gcd_language: str = ""
    use_gcd: bool = True
    use_anilist: bool = True
    threshold: int = DEFAULT_THRESHOLD
    use_cover_match: bool = True
    overwrite_existing: bool = False

    @classmethod
    def load(cls, settings: QSettings) -> TaggerSettings:
        settings.beginGroup("tagger")
        obj = cls(
            comicvine_key=settings.value("comicvine_key", "") or "",
            use_comicvine=_bool(settings.value("use_comicvine"), True),
            gcd_path=settings.value("gcd_path", "") or "",
            gcd_language=settings.value("gcd_language", "") or "",
            use_gcd=_bool(settings.value("use_gcd"), True),
            use_anilist=_bool(settings.value("use_anilist"), True),
            threshold=int(settings.value("threshold", DEFAULT_THRESHOLD)),
            use_cover_match=_bool(settings.value("use_cover_match"), True),
            overwrite_existing=_bool(settings.value("overwrite_existing"), False),
        )
        settings.endGroup()
        return obj

    def save(self, settings: QSettings) -> None:
        settings.beginGroup("tagger")
        for key, value in self.__dict__.items():
            settings.setValue(key, value)
        settings.endGroup()
        settings.sync()

    # ------------------------------------------------------------------
    def build_providers(self) -> list[MetadataProvider]:
        """Reihenfolge egal - bewertet wird quellenuebergreifend."""
        providers: list[MetadataProvider] = []
        if self.use_comicvine and self.comicvine_key.strip():
            providers.append(ComicVineProvider(self.comicvine_key))
        if self.use_gcd and self.gcd_path.strip():
            providers.append(GcdProvider(self.gcd_path, self.gcd_language))
        if self.use_anilist:
            providers.append(AniListProvider())
        return providers

    def build_config(self) -> AutoTagConfig:
        return AutoTagConfig(
            threshold=self.threshold,
            use_cover_match=self.use_cover_match,
            overwrite_existing=self.overwrite_existing,
            providers=self.build_providers(),
        )

