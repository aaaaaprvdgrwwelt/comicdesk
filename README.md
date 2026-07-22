# ComicDesk

Ein Dateimanager, der nur Comics kennt: browsen, lesen, taggen, umbenennen,
kopieren, verschieben, löschen. Python + Qt (PySide6), läuft unter Linux,
Windows und macOS. Oberfläche auf Deutsch und Englisch.

Tags werden als `ComicInfo.xml` ins Archiv geschrieben — dasselbe Format, das
ComicTagger, Komga, Kavita und ComicRack lesen. Automatisches Taggen gegen
ComicVine oder einen lokalen Dump der Grand Comics Database.

> Status: nutzbar, aber jung. Entwickelt und getestet unter Linux; Windows und
> macOS sollten funktionieren (reines Qt/Python), sind aber ungetestet. Es gibt
> noch keine automatisierte Testsuite — siehe [Bekannte Grenzen](#bekannte-grenzen).

## Installation

Voraussetzung ist Python 3.10 oder neuer.

```bash
git clone https://github.com/aaaaaprvdgrwwelt/comicdesk.git
cd comicdesk
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

Für CBR und CB7 wird zusätzlich `7z` gebraucht:

```bash
sudo apt install p7zip-full p7zip-rar   # Debian/Ubuntu
```

## Starten

```bash
./comicdesk.sh            # oder: .venv/bin/python -m comicdesk
./comicdesk.sh ~/Comics   # direkt in einem Ordner starten
./install-desktop.sh      # Eintrag im Anwendungsmenü und Symbole anlegen
```

Unter Windows und macOS entsprechend `.venv/bin/python -m comicdesk` bzw.
`.venv\Scripts\python -m comicdesk`.

## Wo Daten liegen

| Was | Wo |
|---|---|
| Einstellungen, zuletzt besuchter Ordner | `~/.config/comicdesk/comicdesk.conf` |
| Favoriten | `~/.local/share/comicdesk/favorites.json` |
| Suchindex | `~/.local/share/comicdesk/index.sqlite` |
| Cover-Thumbnails, ComicVine-Cache | `~/.cache/comicdesk/` |

Alles davon ist entbehrlich und wird bei Bedarf neu aufgebaut. Die Wahrheit
über einen Comic steht immer im `ComicInfo.xml` in der Datei selbst.

## Funktionen

**Favoriten** — links oben. `Strg+D` legt den markierten Comic ab, oder den
aktuellen Ordner wenn nichts markiert ist; derselbe Befehl entfernt ihn wieder
(der Stern in der Werkzeugleiste zeigt den Zustand). Einfacher Klick springt
hin, Doppelklick auf einen Comic öffnet ihn. Reihenfolge per Ziehen. Über das
Rechtsklickmenü lassen sich Favoriten umbenennen (ein eigener Anzeigename statt
des Dateinamens) und verschwundene aufräumen — fehlende stehen bis dahin grau
und kursiv da. Umbenannte oder verschobene Dateien zieht ComicDesk automatisch
nach. Gespeichert wird in `~/.local/share/comicdesk/favorites.json`.

**Sitzung** — zuletzt besuchtes Verzeichnis, Fenstergröße und Teilerpositionen
werden beim Beenden gemerkt. Ein Pfad als Startargument (`./comicdesk.sh ~/X`)
hat Vorrang und überschreibt das gemerkte Verzeichnis für diesen Start.

**Browsen** — der Ordnerbaum links beginnt bei deinen **Sammlungen**, nicht bei
`/`; das ganze Dateisystem hängt als letzter Eintrag darunter. Unterordner
werden erst beim Aufklappen gelesen. Mit Maus **und** Tastatur bedienbar
(Pfeiltasten wechseln das Verzeichnis sofort mit). Rechtsklick im Baum bietet Öffnen, zu den
Favoriten hinzufügen, hier automatisch taggen, neuer Unterordner. Ordner zeigen
das Cover ihres ersten Comics mit kleinem Ordner-Abzeichen; abschaltbar unter
*Ansicht → Ordner mit Cover anzeigen*, dann wird die Ansicht kompakter.
Weiterhin: Cover-Kacheln in der Mitte. Thumbnails werden
im Hintergrund erzeugt und in `~/.cache/comicdesk/thumbs` zwischengespeichert.
Filterfeld oben rechts filtert nach Dateiname.

**Lesen** — Doppelklick oder Enter öffnet den Reader.

| Taste | Funktion |
|---|---|
| ←/Bild↑/Rücktaste | zurück |
| →/Bild↓/Leertaste | weiter |
| Pos1 / Ende | erste / letzte Seite |
| 1 / 2 / 3 | ganze Seite / Breite / 100 % |
| F11 | Vollbild |
| Esc | schließen |

**Seiten verwalten** (`Strg+P`) — *Extras → Seiten verwalten …*, oder direkt aus
dem Reader. Zeigt alle Seiten als Raster: mit der Maus ziehen zum Umsortieren,
`Entf` zum Löschen, `Strg+Z` macht rückgängig. Geschrieben wird erst mit
`Strg+S` nach Rückfrage — bis dahin bleibt die Datei unangetastet. Die Seiten
werden dabei fortlaufend neu nummeriert; `ComicInfo.xml`, freie Tags und
sonstige Dateien im Archiv bleiben erhalten, `PageCount` wird angepasst.

Das geht bei **CBZ** und **PDF**. CBR/CB7/CBT sind schreibgeschützt — erst
„Nach CBZ konvertieren".

**Taggen** — rechte Seitenleiste, schreibt `ComicInfo.xml` ins Archiv
(Standardformat, das auch Komet, Kavita, Komga, ComicRack und ComicTagger lesen).
Freie Tags landen im `<Tags>`-Element. `Strg+S` speichert.

**Sammlung durchsuchen** (`Strg+F`) — Umschalter „Sammlung" neben dem
Filterfeld, daneben die Auswahl der aktiven Sammlung. Sucht über alle
indizierten Ordner hinweg, nicht nur im aktuellen. Siehe unten. `Strg+G`
springt vom Suchtreffer in dessen Ordner.

**Herkunft der Tags** — jede Kachel trägt oben rechts einen Punkt: blau für
ComicVine, grün für GCD, dunkelgrau für in ComicDesk von Hand eingetragen,
hellgrau für getaggt ohne erkennbare Quelle, orange mit Ausrufezeichen für
ungetaggt. Im Metadaten-Panel steht die Quelle im Klartext,
bei automatisch getaggten Dateien mit der Heft-ID. Erkannt wird das am
`Notes`-Feld; Dateien, die ComicTagger getaggt hat, werden ebenfalls erkannt.
Für vorhandene Dateien wird nichts geschrieben, die Erkennung liest nur.
Speicherst du selbst im Tag-Editor, hinterlässt ComicDesk die Marke
`[ComicDesk: von Hand]` im `Notes`-Feld — vorhandene Notizen bleiben erhalten,
eine schon erkannte Quelle wird nicht überschrieben. Tags ohne jeden Hinweis
gelten als „Quelle unbekannt"; „von Hand" wird nur behauptet, wo es belegt
ist.

**Ungetaggte finden** — *Ansicht → Ungetaggte anzeigen* (`Strg+U`), oder die
Suche `getaggt:nein`. Die Statuszeile zeigt beim Browsen nebenbei, wie viele
Comics im aktuellen Ordner noch keine Tags haben.

**Einstellungen** (`Strg+,`) — unter *Extras → Einstellungen …*. Zwei Reiter:
**Metadaten-Quellen** (ComicVine-API-Key, GCD-Dump, Schwellwert) und
**Allgemein** (Sprache: Deutsch, English, Automatisch). Die Sprachumstellung
greift sofort.

**Bedienung** — Menüleiste mit allen Befehlen (Datei, Bearbeiten, Ansicht,
Extras, Hilfe); die Werkzeugleiste zeigt nur die sechs ständig gebrauchten
Aktionen. Rechtsklick auf eine Datei bietet alle Dateibefehle.

**Automatisch taggen** (`Strg+T`) — gleicht die Auswahl (oder den ganzen Ordner,
wenn nichts ausgewählt ist) gegen ComicVine und/oder die lokale GCD ab. Siehe
unten.

**Umbenennen nach Tags** (`Strg+R`) — Massen-Umbenennung nach Schema, z. B.
`{series} #{issue} ({year}){title_dash}`. Platzhalter: `{series} {issue}
{title} {title_dash} {year} {month} {volume} {publisher}`. Vorschau vor
dem Ausführen, das Schema wird gemerkt.

**Dateioperationen** — `F2` umbenennen, `Strg+C`/`Strg+X`/`Strg+V`,
`Entf` (in den Papierkorb), `Strg+Umschalt+N` neuer Ordner. Die Kürzel gelten
nur im Dateibereich, in den Metadatenfeldern funktionieren sie normal.

## Formate

| Format | Lesen | Tags schreiben | Seiten bearbeiten |
|---|---|---|---|
| CBZ / ZIP | ja | ja (ComicInfo.xml im Archiv) | ja |
| CBR / CB7 | ja, via `7z` | nein → „Nach CBZ konvertieren“ | nein |
| CBT | ja | nein → „Nach CBZ konvertieren“ | nein |
| PDF | ja, via PyMuPDF | ja (`datei.pdf.ComicInfo.xml` daneben) | ja |

„Nach CBZ konvertieren“ erzeugt eine CBZ-Kopie und lässt das Original liegen.

Für CBR/CB7 wird das `7z`-Kommando gebraucht:
`sudo apt install p7zip-full p7zip-rar`.

## Sammlungen

Die Sammlung wählst du oben in der Leiste oder im Ordnerbaum — beides ist
gekoppelt: Wer in „Kinder" blättert, sucht auch in „Kinder". Außerhalb aller
Sammlungen stellt sich der Bereich auf „Alle Sammlungen" zurück, damit die
Anzeige keine Einschränkung behauptet, die zum Ort nicht passt. Der
letzte Eintrag der Liste führt zur Verwaltung, ebenso *Extras → Sammlungen …*
(`Strg+Umschalt+M`).

Dort legst du beliebig viele benannte Sammlungen an,
jede mit eigenen Ordnern — etwa „US-Comics" und „Kinderkram". Die Auswahl oben
bestimmt, worin gesucht wird; „Alle Sammlungen" sucht überall. Umbenennen und
Löschen einer Sammlung lässt die Comic-Dateien selbst unangetastet, entfernt
nur die Index-Einträge.

**Ordner zwischen Sammlungen verschieben** — Rechtsklick im Ordnerbaum oder
*Extras → In Sammlung verschieben …*. Der Ordner wandert dabei auch auf der
Platte in das Verzeichnis der Zielsammlung. Der Index wird direkt
umgeschrieben statt neu eingelesen (bei tausenden Heften über ein Netzlaufwerk
der Unterschied zwischen Millisekunden und Minuten); Favoriten ziehen mit,
und die Ansicht folgt, wenn du gerade darin stehst.

Gemessen an 300 CBZ in 25 verschachtelten Ordnern: **415 Comics/s** beim
Erstlauf (10.000 Stück in ~25 Sekunden), ein zweiter Lauf ist 21× schneller,
weil nur geänderte Dateien neu gelesen werden. Der Index braucht ~830 Byte pro
Comic. CBR und CB7 sind rund 10× langsamer als CBZ, weil zum Einlesen das
ganze Archiv entpackt werden muss.

Sinnvolle Reihenfolge bei einer neuen Sammlung: erst automatisch taggen
(`Strg+T`), dann indizieren — der Index liest nur, was schon in den Dateien
steht.

## Sammlung durchsuchen

Erst unter *Extras → Sammlungen* die Ordner festlegen und
einlesen lassen. Der Index liegt in `~/.local/share/comicdesk/index.sqlite` und
ist reiner Cache — er lässt sich jederzeit neu aufbauen, Quelle der Wahrheit
bleibt das ComicInfo.xml in der Datei. Ein zweiter Lauf liest nur geänderte
Dateien neu; verschwundene Einträge fliegen raus. Tag-Änderungen im Panel und
Auto-Tag-Läufe aktualisieren den Index sofort, ohne neuen Scan.

Suchsyntax — Feldsuchen und freier Text lassen sich mischen:

| Beispiel | Wirkung |
|---|---|
| `joker` | Volltext über alle Felder |
| `serie:batman` | Serienname enthält „batman" |
| `jahr:1975` / `jahr:1990-1999` | Jahr exakt oder Zeitraum |
| `verlag:ehapa` | Verlag |
| `tag:gotham` | freies Tag |
| `autor:gottfredson` | beliebige mitwirkende Person |
| `figur:joker` `team:` `ort:` | Charaktere, Teams, Orte |
| `titel:"der grosse fall"` | Anführungszeichen für Mehrwortsuche |
| `getaggt:nein` | alles ohne Tags |
| `quelle:comicvine` | woher die Tags stammen (`comicvine`, `gcd`, `manual`) |
| `serie:batman jahr:2019 joker` | alles kombinierbar (UND) |

Treffer erscheinen zweistufig: erst die **Reihen** (Ordner mit mindestens zwei
Treffern) mit Cover und Heftzahl, darunter die einzelnen Ausgaben. Ein Klick
auf eine Reihe springt in den Ordner.

Weitere Präfixe: `nummer:` `genre:` `sprache:` `imprint:` `arc:` `datei:`.
Die englischen Namen (`series:` `year:` `publisher:` …) funktionieren ebenso.

## Reihen: was fehlt mir?

*Ansicht → Reihen …* (`Strg+E`). Zwei Aussagen, bewusst nie vermischt:

**Lücke** — zwischen zwei Heften, die du hast, fehlt eine Nummer. Folgt allein
aus dem eigenen Bestand, braucht keine Quelle, ist nicht bestreitbar.

**Laut Quelle** — dass eine Reihe über dein höchstes Heft hinaus weiterging,
weiß nur eine externe Quelle. Wird mit Quellenangabe geführt und als Angabe
gekennzeichnet, nicht als Gewissheit.

Die Zuordnung zur Quell-Reihe läuft über die **in den Tags gespeicherte
Heft-ID**, nicht über den Serientitel. Das ist der entscheidende Punkt: Eine
Namenssuche nach „Die Rächer" greift bei GCD die Condor-Auflage von 1979 mit
47 Heften, obwohl die eigene Reihe eine andere ist. Über die Heft-ID gibt es
keine Fehlzuordnung. Voraussetzung ist ein Indexlauf, der die IDs eingelesen
hat; ohne ID sagt der Dialog das offen.

Weil eine lokale Reihe oft mehrere Reihen der Quelle abdeckt (andere Auflage,
anderer Verlag), werden Hefte vom Anfang **und** vom Ende der Spanne abgefragt
und die Ergebnisse zusammengeführt.

Nicht jede Reihe ist fortlaufend nummeriert: Magazine wie *Zack* oder *Zorro*
nummerieren nach Datum (`198303` = März 1983). Wo die Nummerierung uneinheitlich
ist, wird **keine** Lücke behauptet.

**Von Hand festlegen** — wenn du es besser weißt als jede Quelle. Etwa weil
eine Reihe nur die Nummern 1–3 und 12–20 hat: Bereichsschreibweise
`1-3, 12-20` eintragen, fertig. Diese Angabe schlägt jede Quelle, Nummern die
nicht darin stehen gelten nicht mehr als Lücke. Jederzeit änder- und aufhebbar.

Umgekehrt meldet ComicDesk auch, wenn du ein Heft besitzt, das laut Festlegung
oder Quelle gar nicht existiert — dann stimmt entweder die Festlegung nicht
oder das Heft ist falsch getaggt.

ComicVine erlaubt 200 Anfragen pro Stunde; „Alle ungeprüften prüfen" läuft
deshalb lange, ist abbrechbar, wiederaufnehmbar und dauerhaft gecacht.

## Automatisches Taggen

Konfiguration unter „Metadaten-Quellen …“. Beide Quellen können gleichzeitig
aktiv sein; bewertet wird quellenübergreifend, der beste Treffer gewinnt.

### ComicVine

API-Key kostenlos nach Registrierung auf comicvine.gamespot.com/api. Limit sind
200 Anfragen pro Stunde, deshalb wird auf ~1 Anfrage/Sekunde gedrosselt und
jede Antwort dauerhaft in `~/.cache/comicdesk/comicvine.sqlite` gecacht (30 Tage).
Liefert Cover-URLs — nur damit ist die Bild-Verifikation möglich.

### GCD (lokal)

Die Grand Comics Database hat keine öffentliche API, stellt aber alle zwei
Wochen **SQLite3-Dumps** bereit: <https://www.comics.org/download/> (Account
nötig, Daten unter CC-BY). Datei herunterladen, im Dialog auswählen, einmal
**„Suche vorbereiten"** drücken.

Das ist nicht optional. Der Dump bringt zwar Indizes mit, aber `LIKE '%…%'`
kann keinen davon nutzen — SQLite scannt alle ~231.000 Serien. Gemessen an
einem echten Dump (6,2 GB, Stand Juli 2026):

| Serie suchen | Dauer |
|---|---|
| ohne Vorbereitung | 15.900 ms |
| mit Volltextindex | **0,2 ms** |

Der Aufbau dauert ~10 Sekunden und legt eine eigene 7-MB-Datei unter
`~/.local/share/comicdesk/` an; der Dump selbst wird **nicht** verändert. Wird
ein neuer Dump eingelegt, merkt ComicDesk das an Größe und Datum und der alte
Index verfällt.

**Den Dump auf eine lokale Platte legen.** Auf einer SMB-Freigabe war
dieselbe Abfrage 15× langsamer, das Nachladen der Details sogar 5× — SQLite
macht viele kleine wahlfreie Zugriffe, und genau das ist über Netz teuer.
ComicDesk warnt im Einstellungsdialog, wenn der Pfad auf einem Netzlaufwerk
liegt. Auf Netzlaufwerken wird die Datenbank mit `immutable=1` geöffnet, weil
SQLite-Sperren über CIFS und NFS nicht zuverlässig funktionieren.

Offline, kein Limit, und deutlich besser bei europäischen Verlagen (Ehapa,
Carlsen, Splitter, Bastei), die ComicVine kaum erfasst. Über „Nur Sprache“
lassen sich z. B. ausschließlich deutsche Ausgaben berücksichtigen. Der Dump
enthält keine Cover-URLs, hier gibt es also keinen Bildabgleich.

### AniList (Manga)

Kein Schlüssel nötig, Limit 90 Anfragen/Minute, gedrosselt und gecacht.

AniList kennt Manga-**Serien**, aber keine einzelnen Bände einer deutschen
Ausgabe — Verlag, Jahr und Bandtitel stehen in der GCD. Deshalb läuft AniList
als **Ergänzungsquelle**: sie bestimmt nie, welches Heft eine Datei ist, und
gewinnt nie eine Bewertung. Sie füllt nur Felder, die sonst leer blieben —
Zeichner, Autor, Genre, Beschreibung, Leserichtung, Bandzahl. Vorhandene
Angaben werden nie überschrieben, und eine Rolle, die schon besetzt ist,
bleibt unangetastet.

Der Serienname muss zu mindestens 75 % passen, sonst wird nichts ergänzt.
Bei einer Ergänzung ist eine Fehlzuordnung teuer und schwer zu bemerken, daher
lieber nichts als das Falsche. Praktische Folge: deutsche Titel, die nichts mit
dem Originaltitel zu tun haben („Pokémon Schwert und Schild" vs. „Pocket
Monsters: Sword & Shield"), werden nicht erkannt.

### Neu anfangen

*Extras → Tags löschen* entfernt die `ComicInfo.xml` aus den gewählten Dateien
(bei PDF die Sidecar-Datei) — für den Fall, dass die vorhandenen Tags aus einer
falschen Zuordnung stammen. Die Seiten bleiben unberührt.

Beim Auto-Taggen gibt es dazu **„Vorhandene Tags dabei ersetzen statt
ergänzen"**. Ohne Haken bleiben Felder stehen, welche die Quelle nicht füllt,
und deine eigenen freien Tags; mit Haken wird alles verworfen und neu
geschrieben. Die Option greift nur zusammen mit „Auch Dateien anfassen, die
schon Tags haben" und ist sonst ausgegraut.

### Treffer von Hand wählen

Was unterhalb des Schwellwerts landet, bleibt liegen — mit `Strg+Umschalt+T`
oder per Doppelklick auf eine Zeile im Auto-Tag-Protokoll siehst du **alle**
Vorschläge samt Bewertung, Quelle und Cover neben dem Cover deines Hefts und
wählst selbst.

Serie, Nummer und Jahr sind dort änderbar. Das ist meist der eigentliche
Hebel: Ein niedriger Score kommt fast immer daher, dass der Dateiname falsch
gelesen wurde — Begriff korrigieren, erneut suchen, fertig.

### Bewertung

Aus Dateiname und vorhandenen Tags wird eine Anfrage gebaut (Tags schlagen
Dateinamen). Jeder Kandidat bekommt einen Score aus gewichteten Signalen:

| Signal | Gewicht | Anmerkung |
|---|---|---|
| Serienname | 45 | Ähnlichkeit, nicht Gleichheit |
| Heftnummer | 20 | Abweichung disqualifiziert sofort |
| Jahr | 25 | ±1 Jahr zählt teilweise |
| Verlag | 10 | |
| Cover-Bildvergleich | 40 | nur ComicVine |

Signale, für die Daten fehlen, fallen samt Gewicht heraus — ein Treffer ohne
Cover steht dadurch nicht automatisch schlechter da. Geschrieben wird nur ab
dem eingestellten Schwellwert (Standard 80), alles darunter erscheint als
„unsicher“ im Protokoll, **ohne die Datei anzufassen**. Dateien, die schon Tags
haben, werden standardmäßig übersprungen.

Neue Werte werden über die vorhandenen gelegt, nicht ersetzt: Felder, die die
Quelle nicht füllt, und deine eigenen freien Tags bleiben erhalten.

## Aufbau

- `comicdesk/archive.py` – Archiv- und Metadaten-Ebene (bewusst ohne comicapi's
  RAR-Backend, das `unrar` bräuchte; ComicInfo-Mapping kommt von `comicapi`)
- `comicdesk/thumbs.py` – Cover-Thumbnails im Threadpool, Platten-Cache
- `comicdesk/mainwindow.py` – Browser, Kachel-Delegate, Dateioperationen
- `comicdesk/dirtree.py` – Ordnerbaum mit den Sammlungen als Wurzeln
- `comicdesk/reader.py` – Lesefenster
- `comicdesk/metapanel.py` – Tag-Editor
- `comicdesk/pageeditor.py` – Seiten löschen und umsortieren
- `comicdesk/favorites.py` – Favoritenliste (JSON)
- `comicdesk/provenance.py` – erkennt, woher die Tags einer Datei stammen
- `comicdesk/providers/` – Metadaten-Quellen hinter einer gemeinsamen
  Schnittstelle (`base.py`), aktuell `comicvine.py`, `gcd.py` und
  `anilist.py`; `cache.py` hält Netzantworten vor
- `comicdesk/autotag.py` – Bewertung und Batch-Lauf im Hintergrund-Thread
- `comicdesk/autotagdialog.py` – Quellen-Einstellungen und Lauf-Protokoll
- `comicdesk/index.py` – Sammlungs-Index (SQLite + FTS5) und Suchsyntax
- `comicdesk/series.py` – Reihen bündeln, Nummerierung erkennen, Lücken finden
- `comicdesk/seriescheck.py` – Vollständigkeit über die Quell-Heft-ID
- `comicdesk/seriesdialog.py` – Reihen-Ansicht
- `comicdesk/indexdialog.py` – Sammlungsverwaltung und Scan-Fortschritt
- `comicdesk/i18n.py` – Übersetzungstabellen
- `comicdesk/theme.py` – Stylesheet, aus der Systempalette abgeleitet
- `comicdesk/icons.py` – selbst gezeichnete SVG-Icons (Theme-unabhängig)
- `comicdesk/appicon.py`, `comicdesk/assets/` – Programmsymbol; unter 32 px
  wird eine vereinfachte Zeichnung benutzt, weil die ausführliche dort
  zerfällt. `install-desktop.sh` legt die PNGs samt `index.theme` im
  hicolor-Thema ab — unter Wayland kann eine Anwendung ihr Fenstersymbol nicht
  selbst setzen, der Compositor sucht es über die `app_id` in der
  `.desktop`-Datei

Neue Sprache: in `i18n.py` ein Dict nach dem Muster von `EN` anlegen und in
`LANGUAGES` und `TABLE` eintragen. Schlüssel sind die deutschen Quelltext-
Strings; fehlt ein Eintrag, erscheint der Schlüssel — die App bleibt nutzbar.

Eine weitere Quelle anzubinden heißt: `MetadataProvider` ableiten, `available`,
`search` und `enrich` implementieren, in `config.py` eintragen.

## Bekannte Grenzen

- **Keine automatisierte Testsuite.** Alles wurde manuell und mit
  Wegwerf-Skripten geprüft.
- **ComicVine ist nie live gelaufen** — nur gegen nachgebaute API-Antworten.
  Feldnamen und Rollen-Mapping stimmen, das reale Verhalten unter Rate-Limit
  ist ungeprüft.
- **GCD ist nie gegen einen echten Dump gelaufen**, nur gegen eine
  synthetische Datenbank mit dem echten Schema. Die Seriensuche nutzt
  `LIKE '%…%'` und dürfte bei ~150.000 Serien zu langsam sein; nötig wäre eine
  FTS5-Volltexttabelle.
- **Nur unter Linux getestet.**
- Reader ohne Lesefortschritt, Doppelseiten und Manga-Leserichtung.
- Tags nur einzeln editierbar, kein Batch-Editor.
- Kein Drag & Drop aus anderen Dateimanagern.

## Lizenz

[MIT](LICENSE).

Verwendet [PySide6](https://doc.qt.io/qtforpython/) (LGPL),
[comicapi/ComicTagger](https://github.com/comictagger/comictagger) (Apache-2.0),
[PyMuPDF](https://pymupdf.readthedocs.io/) (AGPL/kommerziell) und
[Send2Trash](https://github.com/arsenetar/send2trash) (BSD).
Metadaten stammen von [ComicVine](https://comicvine.gamespot.com/api/) und der
[Grand Comics Database](https://www.comics.org/) (Daten CC-BY).
