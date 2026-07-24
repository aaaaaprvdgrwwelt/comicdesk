"""Sprachumschaltung.

Die Quelltext-Strings sind zugleich die Schluessel. Sie sind ASCII-Deutsch
gehalten, damit sie robust als Schluessel taugen; die Tabelle liefert fuer
`de` das korrekt umlautete Deutsch und fuer `en` die Uebersetzung. Fehlt ein
Eintrag, wird der Schluessel selbst angezeigt - die App bleibt also immer
benutzbar, auch wenn eine Uebersetzung vergessen wurde.
"""
from __future__ import annotations

#: Code -> Anzeigename im Menue.
LANGUAGES = {"auto": "Automatisch", "de": "Deutsch", "en": "English"}

_current = "de"


def system_language() -> str:
    from PySide6.QtCore import QLocale

    code = QLocale.system().name().split("_")[0].lower()
    return code if code in ("de", "en") else "en"


def set_language(code: str) -> None:
    global _current
    _current = system_language() if code == "auto" else (
        code if code in ("de", "en") else "de")


def language() -> str:
    return _current


def _(text: str) -> str:
    """Uebersetzt `text` in die aktive Sprache."""
    return TABLE.get(_current, {}).get(text, text)


# ---------------------------------------------------------------------------
DE = {
    # Nur Eintraege, bei denen der ASCII-Schluessel Umlaute braucht.
    "Loeschen": "Löschen",
    "Einfuegen": "Einfügen",
    "Nach oben": "Nach oben",
    "◀ Zurueck": "◀ Zurück",
    "Naechstes Heft": "Nächstes Heft",
    "Zurueckrollen": "Zurückrollen",
    "Vergrössern": "Vergrößern",
    "Schliessen": "Schließen",
    "Metadaten-Quellen …": "Metadaten-Quellen …",
    "Keine Datei ausgewaehlt": "Keine Datei ausgewählt",
    "Waehlen …": "Wählen …",
    "Ordner hinzufuegen …": "Ordner hinzufügen …",
    "Ordner waehlen": "Ordner wählen",
    "GCD-SQLite-Dump waehlen": "GCD-SQLite-Dump wählen",
    "Bitte genau einen Eintrag waehlen.": "Bitte genau einen Eintrag wählen.",
    "Bitte mindestens eine Datei waehlen.": "Bitte mindestens eine Datei wählen.",
    "Diese Datei unveraendert lassen und mit der naechsten weitermachen.":
        "Diese Datei unverändert lassen und mit der nächsten weitermachen.",
    "Bitte mindestens einen Ordner hinzufuegen.":
        "Bitte mindestens einen Ordner hinzufügen.",
    "Keine konvertierbaren Dateien gewaehlt.":
        "Keine konvertierbaren Dateien gewählt.",
    "Umbenennen bestaetigen": "Umbenennen bestätigen",
    "Alles neu einlesen (sonst nur geaenderte Dateien)":
        "Alles neu einlesen (sonst nur geänderte Dateien)",
    "Einmalig ausfuehren - beschleunigt die Suche erheblich.":
        "Einmalig ausführen – beschleunigt die Suche erheblich.",
    "Laedt ...": "Lädt …",
    "Suche Dateien …": "Suche Dateien …",
    "Wird beendet …": "Wird beendet …",
    "Wird nach der laufenden Datei beendet …":
        "Wird nach der laufenden Datei beendet …",
    "uebersprungen": "übersprungen",
    "Hat bereits Tags.": "Hat bereits Tags.",
    "Format nicht beschreibbar - erst nach CBZ konvertieren.":
        "Format nicht beschreibbar – erst nach CBZ konvertieren.",
    "Serienname weder in Tags noch im Dateinamen erkennbar.":
        "Serienname weder in Tags noch im Dateinamen erkennbar.",
    "Kostenlos nach Registrierung. Limit 200 Anfragen/Stunde, deshalb wird "
    "gedrosselt und dauerhaft gecacht. Liefert Cover, damit ist die "
    "Bild-Verifikation moeglich.":
        "Kostenlos nach Registrierung. Limit 200 Anfragen/Stunde, deshalb wird "
        "gedrosselt und dauerhaft gecacht. Liefert Cover, damit ist die "
        "Bild-Verifikation möglich.",
    "SQLite3-Dump von comics.org/download (Account noetig, Daten CC-BY). "
    "Offline und ohne Limit, stark bei europaeischen Verlagen. Enthaelt keine "
    "Cover, daher kein Bildabgleich.":
        "SQLite3-Dump von comics.org/download (Account nötig, Daten CC-BY). "
        "Offline und ohne Limit, stark bei europäischen Verlagen. Enthält "
        "keine Cover, daher kein Bildabgleich.",
    "Nur Treffer ab diesem Wert werden geschrieben. Alles darunter landet als "
    "„unsicher“ im Protokoll, ohne die Datei zu aendern.":
        "Nur Treffer ab diesem Wert werden geschrieben. Alles darunter landet "
        "als „unsicher“ im Protokoll, ohne die Datei zu ändern.",
    "Es ist keine Quelle konfiguriert. Unter „Quellen …“ einen "
    "ComicVine-API-Key eintragen oder einen GCD-Dump auswaehlen.":
        "Es ist keine Quelle konfiguriert. Unter „Quellen …“ einen "
        "ComicVine-API-Key eintragen oder einen GCD-Dump auswählen.",
    "Schreiben in dieses Format ist nicht moeglich. Ueber „Nach CBZ "
    "konvertieren“ taggbar machen.":
        "Schreiben in dieses Format ist nicht möglich. Über „Nach CBZ "
        "konvertieren“ taggbar machen.",
    "Metadaten koennen in {suffix} nicht geschrieben werden. Datei zuerst "
    "nach CBZ konvertieren.":
        "Metadaten können in {suffix} nicht geschrieben werden. Datei zuerst "
        "nach CBZ konvertieren.",
    "Nicht unterstuetztes Format: {suffix}":
        "Nicht unterstütztes Format: {suffix}",
    "7z ist nicht installiert - CBR/CB7 koennen nicht gelesen werden.\n"
    "Installation: sudo apt install p7zip-full p7zip-rar":
        "7z ist nicht installiert – CBR/CB7 können nicht gelesen werden.\n"
        "Installation: sudo apt install p7zip-full p7zip-rar",
    "7z konnte {name} nicht entpacken:\n{error}":
        "7z konnte {name} nicht entpacken:\n{error}",
    "{count} Eintrag/Eintraege in den Papierkorb verschieben?\n\n{names}{more}":
        "{count} Einträge in den Papierkorb verschieben?\n\n{names}{more}",
    "Fertig: {updated} eingelesen, {skipped} unveraendert, {removed} "
    "verschwundene entfernt. {stats}":
        "Fertig: {updated} eingelesen, {skipped} unverändert, {removed} "
        "verschwundene entfernt. {stats}",
    "Schema – verfuegbar: {series} {issue} {title} {title_dash} {year} "
    "{month} {volume} {publisher}":
        "Schema – verfügbar: {series} {issue} {title} {title_dash} {year} "
        "{month} {volume} {publisher}",
    "Statt im aktuellen Ordner in der gesamten indizierten Sammlung suchen "
    "(Strg+F)":
        "Statt im aktuellen Ordner in der gesamten indizierten Sammlung "
        "suchen (Strg+F)",
    "Suchmodus – der Index ist noch leer. Erst „Sammlung indizieren …“ "
    "ausfuehren.":
        "Suchmodus – der Index ist noch leer. Erst „Sammlung indizieren …“ "
        "ausführen.",
    "Seiten koennen in {suffix} nicht bearbeitet werden. Datei zuerst nach "
    "CBZ konvertieren.":
        "Seiten können in {suffix} nicht bearbeitet werden. Datei zuerst nach "
        "CBZ konvertieren.",
    "Seiten loeschen": "Seiten löschen",
    "Rueckgaengig": "Rückgängig",
    "{count} werden geloescht": "{count} werden gelöscht",
    "Reihenfolge geaendert": "Reihenfolge geändert",
    "Diese Datei ist nicht bearbeitbar – erst nach CBZ konvertieren.":
        "Diese Datei ist nicht bearbeitbar – erst nach CBZ konvertieren.",
    "{count} Seite(n) werden dauerhaft aus der Datei entfernt. Fortfahren?":
        "{count} Seite(n) werden dauerhaft aus der Datei entfernt. Fortfahren?",
    "Seiten verwalten …": "Seiten verwalten …",
    "Zu Favoriten hinzufuegen": "Zu Favoriten hinzufügen",
    "Verschwundene Favoriten aufraeumen": "Verschwundene Favoriten aufräumen",
    "„{name}“ zu den Favoriten hinzugefuegt.":
        "„{name}“ zu den Favoriten hinzugefügt.",
    "Ordner hinzufuegen …": "Ordner hinzufügen …",
    "„{name}“ wird durchsucht …": "„{name}“ wird durchsucht …",
    "Sammlung loeschen": "Sammlung löschen",
    "Sammlung „{name}“ mit {count} indizierten Comics loeschen?\n\n"
    "Die Comic-Dateien selbst bleiben unangetastet.":
        "Sammlung „{name}“ mit {count} indizierten Comics löschen?\n\n"
        "Die Comic-Dateien selbst bleiben unangetastet.",
    "AniList als Ergaenzung benutzen": "AniList als Ergänzung benutzen",
    "ergaenzt durch {sources}": "ergänzt durch {sources}",
    "Wird abgebrochen …": "Wird abgebrochen …",
    "abgebrochen": "abgebrochen",
    "Oeffnen": "Öffnen",
    "Sammlungen …": "Sammlungen …",
    "Tags koennen aus {suffix} nicht entfernt werden.":
        "Tags können aus {suffix} nicht entfernt werden.",
    "Bitte genau einen Ordner waehlen.": "Bitte genau einen Ordner wählen.",
    "Von Hand": "Von Hand",
    "Quelle unbekannt": "Quelle unbekannt",
    "Nicht getaggt": "Nicht getaggt",
    "Cover-Aehnlichkeit {value}": "Cover-Ähnlichkeit {value}",
    "AniList-Limit erreicht, bitte spaeter erneut.":
        "AniList-Limit erreicht, bitte später erneut.",
    "ComicVine-Kontingent erschoepft (200 Anfragen/Stunde). Spaeter "
    "weitermachen - bereits geholte Daten sind gecacht.":
        "ComicVine-Kontingent erschöpft (200 Anfragen/Stunde). Später "
        "weitermachen – bereits geholte Daten sind gecacht.",
    "Baut einen Volltextindex ueber die Serientitel. Einmalig noetig, dauert "
    "etwa zehn Sekunden - ohne ihn dauert jede Suche im Dump mehrere "
    "Sekunden. Der Dump selbst wird nicht veraendert.":
        "Baut einen Volltextindex über die Serientitel. Einmalig nötig, dauert "
        "etwa zehn Sekunden – ohne ihn dauert jede Suche im Dump mehrere "
        "Sekunden. Der Dump selbst wird nicht verändert.",
    "Kennt Manga-Serien, aber keine einzelnen Baende einer deutschen Ausgabe. "
    "Bestimmt deshalb nie das Heft, sondern fuellt nur Luecken: Zeichner, "
    "Autor, Genre, Beschreibung, Leserichtung. Vorhandene Angaben bleiben "
    "unangetastet. Kein Schluessel noetig.":
        "Kennt Manga-Serien, aber keine einzelnen Bände einer deutschen "
        "Ausgabe. Bestimmt deshalb nie das Heft, sondern füllt nur Lücken: "
        "Zeichner, Autor, Genre, Beschreibung, Leserichtung. Vorhandene "
        "Angaben bleiben unangetastet. Kein Schlüssel nötig.",
    "Ueber ComicDesk": "Über ComicDesk",
    "Sprache": "Sprache",
    "Einstellungen …": "Einstellungen …",
    "ComicDesk – ein Dateimanager nur fuer Comics.\n\n"
    "Browsen, lesen, taggen und ordnen von CBZ, CBR, CB7, CBT und PDF. "
    "Tags werden als ComicInfo.xml geschrieben.\n\n"
    "Metadaten von ComicVine und der Grand Comics Database.":
        "ComicDesk – ein Dateimanager nur für Comics.\n\n"
        "Browsen, lesen, taggen und ordnen von CBZ, CBR, CB7, CBT und PDF. "
        "Tags werden als ComicInfo.xml geschrieben.\n\n"
        "Metadaten von ComicVine und der Grand Comics Database.",
    "Nichts umzubenennen ({count} ohne brauchbare Tags).":
        "Nichts umzubenennen ({count} ohne brauchbare Tags).",
    "Konnte nicht gelesen werden: {error}":
        "Konnte nicht gelesen werden: {error}",
}

EN = {
    # --- Werkzeugleiste, Aktionen
    "Automatisch": "Automatic",
    "Nach oben": "Up",
    "Aktualisieren": "Refresh",
    "Suchen": "Search",
    "Ordner anzeigen": "Show folder",
    "Lesen": "Read",
    "Umbenennen": "Rename",
    "Nach Tags benennen": "Rename from tags",
    "Automatisch taggen": "Auto-tag",
    "Kopieren": "Copy",
    "Ausschneiden": "Cut",
    "Einfuegen": "Paste",
    "Loeschen": "Delete",
    "Neuer Ordner": "New folder",
    "Nach CBZ konvertieren": "Convert to CBZ",
    "Sammlung indizieren …": "Index collection …",
    "Metadaten-Quellen …": "Metadata sources …",
    "Aktionen": "Actions",
    "Sammlung": "Collection",
    "Ordner:": "Folder:",
    "Bereit": "Ready",
    "Bereit.": "Ready.",
    "Sprache": "Language",
    "Einstellungen": "Settings",
    "Einstellungen …": "Settings …",
    "&Datei": "&File",
    "&Bearbeiten": "&Edit",
    "&Ansicht": "&View",
    "E&xtras": "&Tools",
    "&Hilfe": "&Help",
    "Beenden": "Quit",
    "In der Sammlung suchen": "Search the collection",
    "Allgemein": "General",
    "Metadaten-Quellen": "Metadata sources",
    "„Automatisch“ folgt der Systemsprache. Die Umstellung greift sofort, "
    "das Fenster wird dabei neu aufgebaut.":
        "“Automatic” follows the system language. The change takes effect "
        "immediately; the window is rebuilt.",
    "ComicDesk – ein Dateimanager nur fuer Comics.\n\n"
    "Browsen, lesen, taggen und ordnen von CBZ, CBR, CB7, CBT und PDF. "
    "Tags werden als ComicInfo.xml geschrieben.\n\n"
    "Metadaten von ComicVine und der Grand Comics Database.":
        "ComicDesk – a file manager just for comics.\n\n"
        "Browse, read, tag and organise CBZ, CBR, CB7, CBT and PDF. Tags are "
        "written as ComicInfo.xml.\n\n"
        "Metadata from ComicVine and the Grand Comics Database.",
    "Ueber ComicDesk": "About ComicDesk",

    # --- Seiten verwalten
    "Seiten verwalten": "Manage pages",
    "Seiten verwalten …": "Manage pages …",
    "Seiten verwalten – {name}": "Manage pages – {name}",
    "Seiten loeschen": "Delete pages",
    "Nach vorne": "Move earlier",
    "Nach hinten": "Move later",
    "An den Anfang": "Move to start",
    "Ans Ende": "Move to end",
    "Rueckgaengig": "Undo",
    "Speichern": "Save",
    "Seiten speichern": "Save pages",
    "Seiten gespeichert.": "Pages saved.",
    "{count} Seiten": "{count} pages",
    "{count} werden geloescht": "{count} to be deleted",
    "Reihenfolge geaendert": "order changed",
    "Diese Datei ist nicht bearbeitbar – erst nach CBZ konvertieren.":
        "This file cannot be edited – convert to CBZ first.",
    "{count} Seite(n) werden dauerhaft aus der Datei entfernt. Fortfahren?":
        "{count} page(s) will be permanently removed from the file. Continue?",
    "Neue Seitenreihenfolge in die Datei schreiben?":
        "Write the new page order to the file?",
    "Ein Comic braucht mindestens eine Seite.":
        "A comic needs at least one page.",
    "Seiten koennen in {suffix} nicht bearbeitet werden. Datei zuerst nach "
    "CBZ konvertieren.":
        "Pages cannot be edited in {suffix}. Convert the file to CBZ first.",

    # --- AniList
    "AniList (Manga)": "AniList (manga)",
    "AniList als Ergaenzung benutzen": "Use AniList as a supplement",
    "AniList ist abgeschaltet.": "AniList is switched off.",
    "AniList-Limit erreicht, bitte spaeter erneut.":
        "AniList rate limit reached, please try again later.",
    "Kennt Manga-Serien, aber keine einzelnen Baende einer deutschen Ausgabe. "
    "Bestimmt deshalb nie das Heft, sondern fuellt nur Luecken: Zeichner, "
    "Autor, Genre, Beschreibung, Leserichtung. Vorhandene Angaben bleiben "
    "unangetastet. Kein Schluessel noetig.":
        "Knows manga series, but not the individual volumes of a local "
        "edition. It therefore never decides which issue a file is; it only "
        "fills gaps: artist, author, genre, description, reading direction. "
        "Existing values are left untouched. No key required.",
    "ergaenzt durch {sources}": "supplemented by {sources}",

    # --- GCD-Volltextindex
    "Suche vorbereiten": "Prepare search",
    "Baut einen Volltextindex ueber die Serientitel. Einmalig noetig, dauert "
    "etwa zehn Sekunden - ohne ihn dauert jede Suche im Dump mehrere "
    "Sekunden. Der Dump selbst wird nicht veraendert.":
        "Builds a full-text index over the series titles. Needed once, takes "
        "about ten seconds - without it every lookup in the dump takes "
        "several seconds. The dump itself is not modified.",
    "Suche ist vorbereitet.": "Search is prepared.",
    "Die Datenbank liegt auf einem Netzlaufwerk – Abfragen dauern dadurch ein "
    "Vielfaches. Eine lokale Kopie ist deutlich schneller.":
        "The database is on a network share, which makes queries many times "
        "slower. A local copy is considerably faster.",
    "Suche noch nicht vorbereitet – jede Abfrage dauert sonst mehrere "
    "Sekunden.":
        "Search not prepared yet - otherwise every query takes several "
        "seconds.",
    "Serientitel werden gelesen …": "Reading series titles …",
    "Volltextindex wird aufgebaut …": "Building full-text index …",
    "Fertig: {count} Serien durchsuchbar.":
        "Done: {count} series searchable.",
    "Vorbereiten fehlgeschlagen:\n{error}": "Preparation failed:\n{error}",

    # --- Ordner verschieben
    "In Sammlung verschieben …": "Move to collection …",
    "In Sammlung verschieben": "Move to collection",
    "Bitte genau einen Ordner waehlen.": "Please select exactly one folder.",
    "Es gibt keine andere Sammlung mit einem gültigen Ordner.":
        "There is no other collection with a valid folder.",
    "„{folder}“ verschieben nach:": "Move “{folder}” to:",
    "„{folder}“ nach „{collection}“ verschieben?\n\n{source}\n→ {target}":
        "Move “{folder}” to “{collection}”?\n\n{source}\n→ {target}",
    "Nach „{collection}“ verschoben, {count} Einträge im Index angepasst.":
        "Moved to “{collection}”, {count} index entries updated.",

    # --- Tags loeschen
    "Tags löschen": "Delete tags",
    "Aus {count} Datei(en) alle Tags entfernen?\n\n{names}{more}\n\nDas lässt "
    "sich nicht rückgängig machen.":
        "Remove all tags from {count} file(s)?\n\n{names}{more}\n\nThis cannot "
        "be undone.",
    "Tags aus {count} Datei(en) entfernt.": "Tags removed from {count} file(s).",
    "Tags koennen aus {suffix} nicht entfernt werden.":
        "Tags cannot be removed from {suffix}.",
    "Vorhandene Tags dabei ersetzen statt ergänzen":
        "Replace existing tags instead of merging",
    "Ohne Haken bleiben Felder stehen, welche die Quelle nicht füllt, und "
    "deine eigenen freien Tags. Mit Haken wird alles verworfen und neu "
    "geschrieben.":
        "Unchecked, fields the source does not fill and your own free tags "
        "stay. Checked, everything is discarded and written fresh.",

    # --- Treffer waehlen
    "Treffer wählen …": "Choose match …",
    "Treffer wählen – {name}": "Choose match – {name}",
    "Treffer wählen – {name} ({pos} von {count})":
        "Choose match – {name} ({pos} of {count})",
    "Überspringen": "Skip",
    "Diese Datei unveraendert lassen und mit der naechsten weitermachen.":
        "Leave this file unchanged and continue with the next one.",
    "Bitte mindestens eine Datei waehlen.": "Please select at least one file.",
    "Die Begriffe stammen aus den Tags oder dem Dateinamen. Passt der Treffer "
    "nicht, liegt es meist daran – korrigieren und erneut suchen. Gibt es einen "
    "Serienname mehrfach, hilft der Bandtitel am ehesten weiter.":
        "The terms come from the tags or the file name. If the match is wrong, "
        "that is usually why - correct them and search again. When a series "
        "name exists several times, the album title helps most.",
    "z. B. Gefährliche Heimkehr": "e.g. Dangerous Homecoming",
    "Nach Serie benennen …": "Name after series …",
    "Nach Serie benennen": "Name after series",
    "Neuer Ordnername:": "New folder name:",
    "Unter {name} sind keine getaggten Comics im Index. Erst taggen oder die "
    "Sammlung neu einlesen.":
        "There are no tagged comics under {name} in the index. Tag them first "
        "or re-index the collection.",
    "{n} von {gesamt} Comics gehören zu „{serie}“, daneben noch {rest} "
    "weitere Reihe(n): {liste}":
        "{n} of {gesamt} comics belong to \u201c{serie}\u201d, plus {rest} "
        "further series: {liste}",
    "Alle {n} getaggten Comics gehören zu „{serie}“.":
        "All {n} tagged comics belong to \u201c{serie}\u201d.",
    "Erneut suchen": "Search again",
    "Im Browser ansehen": "Open in browser",
    "Öffnet die Seite der Quelle zu diesem Treffer - zum Nachsehen, ob es "
    "wirklich dasselbe Heft ist.":
        "Opens the source's page for this match - to check whether it really "
        "is the same issue.",
    "Doppelklick übernimmt den Treffer. „Im Browser ansehen“ zeigt die Seite "
    "der Quelle.":
        "Double-click applies the match. “Open in browser” shows the source's "
        "page.",
    "Wird gesucht …": "Searching …",
    "Wird übernommen …": "Applying …",
    "{count} Vorschläge": "{count} suggestions",
    "Bitte einen Seriennamen eingeben.": "Please enter a series name.",
    "Doppelklick: Vorschläge ansehen und selbst wählen":
        "Double-click: view suggestions and choose yourself",
    "von Hand gewählt": "chosen by hand",
    "Nr.": "No.",

    # --- Sammlungen
    "Sammlungen": "Collections",
    "Sammlungen verwalten …": "Manage collections …",
    "Sammlungen …": "Collections …",
    "Sammlung:": "Collection:",
    "Waehlt die Sammlung: springt in ihren Ordner und begrenzt die Suche "
    "darauf.":
        "Picks the collection: jumps to its folder and limits the search to "
        "it.",
    "Alle Sammlungen": "All collections",
    "In welcher Sammlung gesucht wird": "Which collection is searched",
    "Jede Sammlung hat eigene Ordner. Beim Indizieren werden sie rekursiv "
    "nach Comics durchsucht.":
        "Each collection has its own folders. Indexing scans them recursively "
        "for comics.",
    "Neu …": "New …",
    "Umbenennen …": "Rename …",
    "Neue Sammlung": "New collection",
    "Sammlung umbenennen": "Rename collection",
    "Sammlung loeschen": "Delete collection",
    "Name der Sammlung:": "Collection name:",
    "„{name}“ gibt es schon.": "“{name}” already exists.",
    "Sammlung „{name}“ mit {count} indizierten Comics loeschen?\n\n"
    "Die Comic-Dateien selbst bleiben unangetastet.":
        "Delete collection “{name}” with {count} indexed comics?\n\n"
        "The comic files themselves are left untouched.",
    "Ordner der Sammlung": "Collection folders",
    "Ordner in „{name}“": "Folders in “{name}”",
    "Diese Sammlung indizieren": "Index this collection",
    "Alle indizieren": "Index all",
    "Noch keine Sammlung angelegt.": "No collection created yet.",
    "„{name}“: {count} Comics · insgesamt {total}":
        "“{name}”: {count} comics · {total} in total",
    "„{name}“ wird durchsucht …": "Scanning “{name}” …",

    "Ungetaggte anzeigen": "Show untagged",
    "{count} ohne Tags": "{count} without tags",

    # --- Reihen
    "Reihen": "Series",
    "Reihen …": "Series …",
    "Reihe": "Series",
    "Verlag": "Publisher",
    "Hefte": "Issues",
    "Spanne": "Range",
    "Lücken": "Gaps",
    "Laut Quelle": "Per source",
    "Nur Reihen mit Lücken": "Only series with gaps",
    "Reihen mit nur einem Heft ausblenden": "Hide single-issue series",
    "Diese Reihe prüfen": "Check this series",
    "Alle ungeprüften prüfen": "Check all unchecked",
    "uneinheitlich": "inconsistent",
    "vollständig": "complete",
    "{count} fehlen": "{count} missing",
    "{shown} von {total} Reihen angezeigt · {checked} gegen eine Quelle "
    "geprüft":
        "{shown} of {total} series shown · {checked} checked against a source",
    "{count} Hefte, {span}": "{count} issues, {span}",
    "{count} Hefte": "{count} issues",
    "Anzeige auf {shown} von {found} begrenzt – Suche eingrenzen":
        "Showing {shown} of {found} - narrow the search",
    "{series} Reihen und {hits} Ausgaben von {total} indizierten Comics":
        "{series} series and {hits} issues out of {total} indexed comics",
    "Die Heftnummern dieser Reihe sind uneinheitlich (etwa fortlaufend und "
    "nach Datum gemischt). Deshalb wird hier keine Lücke behauptet.":
        "The issue numbers in this series are inconsistent (sequential and "
        "date-based mixed, for example). No gap is claimed here.",
    "Lücken im eigenen Bestand ({count}):": "Gaps in your own holdings ({count}):",
    "Das folgt allein aus den vorhandenen Heften und braucht keine Quelle.":
        "This follows from the issues you own and needs no source.",
    "Keine Lücken zwischen dem niedrigsten und dem höchsten vorhandenen Heft.":
        "No gaps between your lowest and highest issue.",
    "Noch nicht gegen eine Quelle geprüft – ob die Reihe über dein höchstes "
    "Heft hinaus weiterging, ist damit offen.":
        "Not yet checked against a source - whether the series continued "
        "beyond your highest issue is therefore open.",
    "Laut {source}: {count} Hefte{names}":
        "Per {source}: {count} issues{names}",
    "Dort verzeichnet, bei dir nicht vorhanden ({count}):":
        "Listed there, missing from your collection ({count}):",
    "Davon nach deinem höchsten Heft: {numbers}":
        "Of those, after your highest issue: {numbers}",
    "Deine Sammlung enthält alles, was die Quelle kennt.":
        "Your collection contains everything the source knows about.",
    "Das ist eine Angabe der Quelle, keine Gewissheit.":
        "This is what the source claims, not a certainty.",
    "Nichts zu prüfen – alles bereits geprüft oder ohne Quell-Kennung.":
        "Nothing to check - all done already or without a source ID.",
    "Keine Quelle konfiguriert.": "No source configured.",
    "Fertig: {done} geprüft, {empty} ohne Ergebnis.":
        "Done: {done} checked, {empty} without result.",

    "Keine Quell-Kennung in den Tags – diese Reihe lässt sich nicht sicher "
    "zuordnen. Falls die Hefte getaggt sind, hilft ein neuer Indexlauf.":
        "No source ID in the tags - this series cannot be matched reliably. "
        "If the issues are tagged, a fresh index run helps.",

    "Reihe von Hand festlegen": "Define series by hand",
    "Reihe von Hand festlegen …": "Define series by hand …",
    "Festlegung ändern …": "Change definition …",
    "Festlegung aufheben": "Remove definition",
    "Auf vorhandene Hefte setzen": "Set to owned issues",
    "Übernehmen": "Apply",
    "von Hand": "by hand",
    "Welche Nummern gibt es in dieser Reihe wirklich? Bereiche mit Bindestrich, "
    "mehrere durch Komma getrennt – etwa „1-3, 12-20“. Diese Angabe schlägt "
    "jede Quelle: Nummern, die hier nicht stehen, gelten nicht mehr als Lücke.":
        "Which numbers does this series actually have? Ranges with a hyphen, "
        "separated by commas - for example \u201c1-3, 12-20\u201d. This "
        "overrides every source: numbers not listed here no longer count as "
        "gaps.",
    "{total} Hefte in der Reihe · {owned} davon vorhanden · {missing} fehlen":
        "{total} issues in the series · {owned} of them owned · {missing} missing",
    "Von Hand festgelegt: {ranges}": "Defined by hand: {ranges}",
    "Davon fehlen dir ({count}):": "Of those you are missing ({count}):",
    "Du hast alle festgelegten Nummern.": "You have every number defined.",
    "Diese Angabe schlägt jede Quelle.": "This overrides every source.",
    "Vorhanden, aber nicht festgelegt ({count}): {numbers}":
        "Owned but not defined ({count}): {numbers}",
    "Entweder fehlt das in der Festlegung, oder das Heft ist falsch getaggt.":
        "Either the definition is incomplete, or the issue is tagged wrongly.",
    "Vorhanden, aber der Quelle unbekannt ({count}): {numbers}":
        "Owned but unknown to the source ({count}): {numbers}",

    # --- Herkunft der Tags
    "Grand Comics Database": "Grand Comics Database",
    "Von Hand": "Entered by hand",
    "Quelle unbekannt": "Source unknown",
    "Nicht getaggt": "Not tagged",
    "Quelle: {source}": "Source: {source}",
    "Quelle: {source} (Heft-ID {id})": "Source: {source} (issue ID {id})",

    "Ordner mit Cover anzeigen": "Show folders with cover",
    "Ganzes Dateisystem": "Whole file system",
    "Oeffnen": "Open",
    "Hier automatisch taggen": "Auto-tag this folder",
    "Neuer Ordner …": "New folder …",

    # --- Favoriten
    "Favoriten": "Favourites",
    "Zu Favoriten hinzufuegen": "Add to favourites",
    "Aus Favoriten entfernen": "Remove from favourites",
    "Favorit umbenennen": "Rename favourite",
    "Verschwundene Favoriten aufraeumen": "Clean up missing favourites",
    "Anzeigename:": "Display name:",
    "„{name}“ zu den Favoriten hinzugefuegt.":
        "“{name}” added to favourites.",
    "„{name}“ aus den Favoriten entfernt.":
        "“{name}” removed from favourites.",
    "{count} verschwundene Favoriten entfernt.":
        "{count} missing favourites removed.",

    # --- Reader
    "Reader": "Reader",
    "◀ Zurueck": "◀ Back",
    "Weiter ▶": "Next ▶",
    "Ganze Seite": "Whole page",
    "Breite": "Fit width",
    "100 %": "100 %",
    "Vollbild": "Fullscreen",
    "Schliessen": "Close",
    "Erste Seite": "First page",
    "Letzte Seite": "Last page",
    "Laedt ...": "Loading …",
    "Keine Seiten gefunden.": "No pages found.",
    "Bild konnte nicht dekodiert werden.": "Could not decode image.",
    "Seite {index} / {total}  –  {name}": "Page {index} / {total}  –  {name}",
    "Seite {index} konnte nicht geladen werden:\n{error}":
        "Page {index} could not be loaded:\n{error}",
    "Ansicht": "View",
    "Navigation": "Navigation",
    "Lesezeichen": "Bookmarks",
    "Seiten": "Pages",
    "Hintergrund": "Background",
    "Gehe zu Seite …": "Go to page …",
    "Gehe zu Seite": "Go to page",
    "Seite:": "Page:",
    "Seite {page}": "Page {page}",
    "Weiterrollen": "Scroll on",
    "Zurueckrollen": "Scroll back",
    "Naechstes Heft": "Next issue",
    "Voriges Heft": "Previous issue",
    "Höhe": "Fit height",
    "Vergrössern": "Zoom in",
    "Verkleinern": "Zoom out",
    "Zoom zurücksetzen": "Reset zoom",
    "Doppelseite": "Two pages",
    "Titelseite einzeln": "Cover on its own",
    "Mangamodus (rechts nach links)": "Manga mode (right to left)",
    "Nach rechts drehen": "Rotate right",
    "Nach links drehen": "Rotate left",
    "Lupe": "Magnifier",
    "Lupe stärker": "Stronger magnifier",
    "Lupe schwächer": "Weaker magnifier",
    "Lupe {factor}×": "Magnifier {factor}×",
    "Miniaturen": "Thumbnails",
    "Lesezeichen setzen": "Set bookmark",
    "Lesezeichen …": "Bookmarks …",
    "Lesezeichen auf Seite {page} gesetzt.": "Bookmark set on page {page}.",
    "Lesezeichen auf Seite {page} entfernt.": "Bookmark removed from page {page}.",
    "Keine Lesezeichen in diesem Heft.": "No bookmarks in this issue.",
    "Dunkel": "Dark",
    "Schwarz": "Black",
    "Grau": "Grey",
    "Hell": "Light",
    "Manga": "Manga",
    "Seite {index} / {total}": "Page {index} / {total}",
    "{first}–{second}": "{first}–{second}",
    "Seite {index} konnte nicht geladen werden: {error}":
        "Page {index} could not be loaded: {error}",
    "Weiter auf Seite {page}.": "Continuing on page {page}.",
    "Letzte Seite.": "Last page.",
    "Kein weiteres Heft in diesem Ordner.":
        "No further issue in this folder.",
    "Ende – nochmal blättern öffnet „{name}“.":
        "End – turning again opens “{name}”.",

    # --- Metadaten-Panel
    "Heft": "Issue",
    "Mitwirkende (mehrere mit Komma)": "Credits (separate with commas)",
    "Listen (Komma-getrennt)": "Lists (comma separated)",
    "Beschreibung": "Summary",
    "Tags speichern": "Save tags",
    "Verwerfen": "Discard",
    "Keine Datei ausgewaehlt": "No file selected",
    "Tags": "Tags",
    "Serie": "Series",
    "Nummer": "Number",
    "Titel": "Title",
    "Volume": "Volume",
    "Anzahl Hefte": "Issue count",
    "Jahr": "Year",
    "Monat": "Month",
    "Tag": "Day",
    "Verlag": "Publisher",
    "Imprint": "Imprint",
    "Genre": "Genre",
    "Sprache (ISO)": "Language (ISO)",
    "Format": "Format",
    "Story Arc": "Story arc",
    "Serien-Gruppe": "Series group",
    "Altersfreigabe": "Age rating",
    "Web-Link": "Web link",
    "Scan-Info": "Scan info",
    "Charaktere": "Characters",
    "Teams": "Teams",
    "Orte": "Locations",
    "Autor": "Writer",
    "Zeichner": "Penciller",
    "Tusche": "Inker",
    "Farben": "Colorist",
    "Lettering": "Letterer",
    "Cover": "Cover artist",
    "Redaktion": "Editor",
    "Tags gespeichert.": "Tags saved.",
    "{name}\n{pages} Seiten": "{name}\n{pages} pages",
    "Konnte nicht gelesen werden: {error}": "Could not be read: {error}",
    "PDF: Tags landen in einer ComicInfo.xml-Datei daneben.":
        "PDF: tags are stored in a ComicInfo.xml file next to it.",
    "Schreiben in dieses Format ist nicht moeglich. Ueber „Nach CBZ "
    "konvertieren“ taggbar machen.":
        "This format cannot be written. Use “Convert to CBZ” to make it "
        "taggable.",
    "Fehlgeschlagen:\n{error}": "Failed:\n{error}",

    # --- Dateioperationen
    "Neuer Name:": "New name:",
    "Name:": "Name:",
    "Ordner": "Folder",
    "Nicht gefunden: {path}": "Not found: {path}",
    "{name} existiert bereits.": "{name} already exists.",
    "Bitte genau einen Eintrag waehlen.": "Please select exactly one entry.",
    "{count} kopiert.": "{count} copied.",
    "{count} ausgeschnitten.": "{count} cut.",
    "{count} Eintrag/Eintraege in den Papierkorb verschieben?\n\n{names}{more}":
        "Move {count} item(s) to the trash?\n\n{names}{more}",
    "{count} Datei(en) umbenennen?\n\n{preview}{more}":
        "Rename {count} file(s)?\n\n{preview}{more}",
    "Nichts umzubenennen ({count} ohne brauchbare Tags).":
        "Nothing to rename ({count} without usable tags).",
    "Schema – verfuegbar: {series} {issue} {title} {title_dash} {year} "
    "{month} {volume} {publisher}":
        "Pattern – available: {series} {issue} {title} {title_dash} {year} "
        "{month} {volume} {publisher}",
    "Umbenennen bestaetigen": "Confirm rename",
    "Keine konvertierbaren Dateien gewaehlt.": "No convertible files selected.",
    "{count} Datei(en) nach CBZ konvertieren? Die Originale bleiben erhalten.":
        "Convert {count} file(s) to CBZ? The originals are kept.",
    "Konvertieren": "Convert",
    "und {count} weitere": "and {count} more",
    "{comics} Comics, {dirs} Ordner in {path}":
        "{comics} comics, {dirs} folders in {path}",
    "Keine Comics zum Taggen.": "No comics to tag.",

    # --- Suche / Index
    "Filter (Dateiname) …": "Filter (file name) …",
    "Sammlung durchsuchen – z. B. serie:batman jahr:1990-1999 joker":
        "Search collection – e.g. series:batman year:1990-1999 joker",
    "Statt im aktuellen Ordner in der gesamten indizierten Sammlung suchen "
    "(Strg+F)":
        "Search the whole indexed collection instead of the current folder "
        "(Ctrl+F)",
    "{hits} Treffer von {total} indizierten Comics":
        "{hits} hits out of {total} indexed comics",
    "Suche fehlgeschlagen: {error}": "Search failed: {error}",
    "Suchmodus – {total} Comics im Index. Felder: {fields}":
        "Search mode – {total} comics indexed. Fields: {fields}",
    "Suchmodus – der Index ist noch leer. Erst „Sammlung indizieren …“ "
    "ausfuehren.":
        "Search mode – the index is still empty. Run “Index collection …” "
        "first.",
    "Sammlung indizieren": "Index collection",
    "Diese Ordner werden rekursiv nach Comics durchsucht und ihre Tags in den "
    "Suchindex geschrieben.":
        "These folders are scanned recursively for comics and their tags are "
        "written to the search index.",
    "Ordner hinzufuegen …": "Add folder …",
    "Entfernen": "Remove",
    "Alles neu einlesen (sonst nur geaenderte Dateien)":
        "Re-read everything (otherwise only changed files)",
    "{count} Comics im Index.": "{count} comics indexed.",
    "Ordner waehlen": "Choose folder",
    "Kein Ordner": "No folder",
    "Bitte mindestens einen Ordner hinzufuegen.":
        "Please add at least one folder.",
    "Indizieren": "Index",
    "Suche Dateien …": "Looking for files …",
    "Wird beendet …": "Stopping …",
    "Fertig: {updated} eingelesen, {skipped} unveraendert, {removed} "
    "verschwundene entfernt. {stats}":
        "Done: {updated} read, {skipped} unchanged, {removed} missing "
        "removed. {stats}",

    # --- Auto-Tagging
    "Automatisch taggen – {count} Datei(en)": "Auto-tag – {count} file(s)",
    "Datei": "File",
    "Status": "Status",
    "Score": "Score",
    "Quelle": "Source",
    "Treffer": "Match",
    "Anmerkung": "Note",
    "Quellen …": "Sources …",
    "Starten": "Start",
    "Abbrechen": "Cancel",
    "Wird nach der laufenden Datei beendet …":
        "Stopping after the current file …",
    "Fertig. {summary}": "Done. {summary}",
    "Wird abgebrochen …": "Cancelling …",
    "Abbruch – die laufende Datei wird noch beendet.":
        "Cancelling - the current file is still being finished.",
    "({seconds} s …)": "({seconds} s …)",
    "abgebrochen": "cancelled",
    "Fertig – {count} getaggt": "Done – {count} tagged",
    "Fertig – nichts geändert": "Done – nothing changed",
    "Fertig.": "Done.",
    "[{done}/{total}] {name}": "[{done}/{total}] {name}",
    "getaggt": "tagged",
    "unsicher": "uncertain",
    "kein Treffer": "no match",
    "uebersprungen": "skipped",
    "Fehler": "Error",
    "Hat bereits Tags.": "Already has tags.",
    "Format nicht beschreibbar - erst nach CBZ konvertieren.":
        "Format is not writable – convert to CBZ first.",
    "Serienname weder in Tags noch im Dateinamen erkennbar.":
        "No series name found in tags or file name.",
    "unter Schwellwert {threshold}. {notes}":
        "below threshold {threshold}. {notes}",
    "Cover-Aehnlichkeit {value}": "cover similarity {value}",
    "Keine Quelle": "No source",
    "Keine Quelle nutzbar": "No usable source",
    "Es ist keine Quelle konfiguriert. Unter „Quellen …“ einen "
    "ComicVine-API-Key eintragen oder einen GCD-Dump auswaehlen.":
        "No source is configured. Enter a ComicVine API key or select a GCD "
        "dump under “Sources …”.",

    # --- Quellen-Dialog
    "Metadaten-Quellen": "Metadata sources",
    "ComicVine": "ComicVine",
    "ComicVine benutzen": "Use ComicVine",
    "API-Key": "API key",
    "API-Key von comicvine.gamespot.com/api":
        "API key from comicvine.gamespot.com/api",
    "Kostenlos nach Registrierung. Limit 200 Anfragen/Stunde, deshalb wird "
    "gedrosselt und dauerhaft gecacht. Liefert Cover, damit ist die "
    "Bild-Verifikation moeglich.":
        "Free after registration. Limited to 200 requests per hour, so "
        "requests are throttled and cached permanently. Provides covers, "
        "which enables image verification.",
    "Grand Comics Database (lokaler Dump)":
        "Grand Comics Database (local dump)",
    "GCD benutzen": "Use GCD",
    "Datenbank": "Database",
    "Pfad zur SQLite-Datei aus dem GCD-Dump":
        "Path to the SQLite file from the GCD dump",
    "Waehlen …": "Choose …",
    "Indizes anlegen": "Create indexes",
    "Einmalig ausfuehren - beschleunigt die Suche erheblich.":
        "Run once – speeds up searching considerably.",
    "Indizes sind angelegt.": "Indexes created.",
    "Indizes fehlgeschlagen:\n{error}": "Creating indexes failed:\n{error}",
    "Nur Sprache": "Language only",
    "SQLite3-Dump von comics.org/download (Account noetig, Daten CC-BY). "
    "Offline und ohne Limit, stark bei europaeischen Verlagen. Enthaelt keine "
    "Cover, daher kein Bildabgleich.":
        "SQLite3 dump from comics.org/download (account required, data "
        "CC-BY). Offline and unlimited, strong on European publishers. "
        "Contains no covers, so no image comparison.",
    "Automatik": "Automation",
    "Schwellwert": "Threshold",
    "Treffer per Cover-Bildvergleich absichern (nur ComicVine, langsamer)":
        "Verify matches by comparing covers (ComicVine only, slower)",
    "Auch Dateien anfassen, die schon Tags haben":
        "Also touch files that already have tags",
    "Nur Treffer ab diesem Wert werden geschrieben. Alles darunter landet als "
    "„unsicher“ im Protokoll, ohne die Datei zu aendern.":
        "Only matches at or above this value are written. Anything below is "
        "logged as “uncertain” without changing the file.",
    "GCD": "GCD",
    "GCD-SQLite-Dump waehlen": "Choose GCD SQLite dump",
    "SQLite-Datenbank (*.db *.sqlite *.sqlite3 *.gcd);;Alle Dateien (*)":
        "SQLite database (*.db *.sqlite *.sqlite3 *.gcd);;All files (*)",
    "Alle Sprachen": "All languages",
    "Deutsch": "German",
    "Englisch": "English",
    "Franzoesisch": "French",
    "Italienisch": "Italian",
    "Spanisch": "Spanish",
    "Niederlaendisch": "Dutch",
    "Kein ComicVine-API-Key hinterlegt.": "No ComicVine API key configured.",
    "Kein Pfad zum GCD-Dump hinterlegt.": "No path to a GCD dump configured.",
    "GCD-Dump nicht gefunden: {path}": "GCD dump not found: {path}",
    "GCD-Dump nicht lesbar: {error}": "GCD dump not readable: {error}",

    # --- Archiv-Fehler
    "Metadaten koennen in {suffix} nicht geschrieben werden. Datei zuerst "
    "nach CBZ konvertieren.":
        "Metadata cannot be written to {suffix}. Convert the file to CBZ "
        "first.",
    "Nicht unterstuetztes Format: {suffix}": "Unsupported format: {suffix}",
    "7z ist nicht installiert - CBR/CB7 koennen nicht gelesen werden.\n"
    "Installation: sudo apt install p7zip-full p7zip-rar":
        "7z is not installed – CBR/CB7 cannot be read.\n"
        "Install with: sudo apt install p7zip-full p7zip-rar",
    "7z konnte {name} nicht entpacken:\n{error}":
        "7z could not extract {name}:\n{error}",
    "{name} existiert bereits.": "{name} already exists.",
    "ComicVine-Kontingent erschoepft (200 Anfragen/Stunde). Spaeter "
    "weitermachen - bereits geholte Daten sind gecacht.":
        "ComicVine quota exhausted (200 requests per hour). Continue later – "
        "data already fetched is cached.",
}

TABLE = {"de": DE, "en": EN}
