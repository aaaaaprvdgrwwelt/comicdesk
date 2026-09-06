# Changelog

Format nach [Keep a Changelog](https://keepachangelog.com/de/1.1.0/).
Noch kein Release getaggt — alles bislang unter „Unreleased“.

## [Unreleased]

### Added

- Browsen, lesen, taggen (`ComicInfo.xml`), umbenennen, kopieren,
  verschieben, löschen für CBZ/CBR/CB7/CBT/PDF.
- Ordnerbaum ausgehend von benannten Sammlungen, mit Cover-Vorschau.
- Favoriten mit eigenem Anzeigenamen, ziehbarer Reihenfolge, automatischer
  Nachführung bei Umbenennung/Verschiebung.
- Automatisches Taggen gegen ComicVine und/oder einen lokalen Dump der
  Grand Comics Database, ergänzt durch AniList für Manga.
- Herkunfts-Anzeige der Tags (ComicVine/GCD/von Hand/unbekannt) je Kachel.
- Reihen-Ansicht: Lücken im eigenen Bestand getrennt von „laut Quelle noch
  ausstehend“, Zuordnung über die Heft-ID statt den Serientitel, manuelle
  Bestandsfestlegung per Bereichsschreibweise.
- Sammlungsindex (SQLite + FTS5) mit Feldsuche
  (`serie:` `jahr:` `autor:` `tag:` `quelle:` `getaggt:` …), Treffer als
  Reihen und einzelne Ausgaben.
- Intelligente Listen: gespeicherte Suchen, die sich selbst aktualisieren.
- Reader mit Doppelseite, Manga-Leserichtung, Lupe, Miniaturen, Lesestand,
  Vollbild-HUD.
- Seiten verwalten: löschen/umsortieren mit Rückgängig, erst auf Befehl
  geschrieben.
- Bilder umkodieren (WebP/AVIF/JPEG/PNG/JPEG XL), Qualitätsvergleich vor
  dem Löschen.
- Windows-Installer und macOS-Pakete (PyInstaller + Inno Setup) über
  GitHub Actions.
- `.desktop`-Eintrag samt Icon-Cache-Aktualisierung für Quellinstallationen
  unter Linux.
- Projektseite unter `aaaaaprvdgrwwelt.github.io/comicdesk`.
- Testsuite (pytest) für `series.py`.
- CI (GitHub Actions): Tests bei jedem Push/PR.

### Changed

- Gemeinsame Bausteine (Sprachumschaltung, Theme, Icons, Programmsymbol,
  Thumbnails, Antwort-Cache, Titel-Ähnlichkeit, Menü-Mechanismus) nach
  [deskkit](https://github.com/aaaaaprvdgrwwelt/deskkit) ausgelagert —
  geteilt mit MovieDesk, BookDesk und AudioDesk.
- `import fitz` durch das nicht mehr deprecated `import pymupdf` ersetzt.

### Fixed

- Verschiedene Abstürze bei Menü-Aktionen während eines laufenden
  Hintergrund-Threads (Verschieben, Umbenennen, Tagging-Fenster).
- deskkit fehlte im PyInstaller-Paket seit dessen Auslagerung — Release-
  Build war dadurch kaputt, ohne dass es auffiel.

### Security

- ComicVine-API-Schlüssel landet im System-Schlüsselbund statt im
  Klartext in der Konfigurationsdatei.

[Unreleased]: https://github.com/aaaaaprvdgrwwelt/comicdesk/commits/main
