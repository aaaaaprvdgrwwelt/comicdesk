# Pakete bauen

PyInstaller ist kein Cross-Compiler: ein Windows-Programm muss auf Windows
entstehen, ein Mac-Programm auf einem Mac. Deshalb baut
`.github/workflows/release.yml` beides auf GitHubs Rechnern.

## Der übliche Weg

```bash
git tag v0.2.0
git push origin v0.2.0
```

Das genügt. Der Workflow baut Windows, macOS (Apple Silicon) und macOS
(Intel), prüft jedes Paket mit `--selftest` und hängt die Ergebnisse an ein
neues Release.

Zum Ausprobieren ohne Veröffentlichung: **Actions → Pakete bauen → Run
workflow**. Dieselben Dateien liegen danach als Artefakt am Lauf.

## Von Hand, auf der jeweiligen Plattform

```bash
pip install -r requirements.txt pyinstaller
python packaging/make_icons.py packaging      # .ico und .iconset
iconutil -c icns packaging/comicdesk.iconset  # nur auf macOS
pyinstaller packaging/comicdesk.spec --noconfirm --clean
```

Das Ergebnis liegt in `dist/`. Für den Windows-Installer zusätzlich
[Inno Setup](https://jrsoftware.org/isinfo.php):

```
iscc /DVersion=0.2.0 packaging\comicdesk.iss
```

## Was mitgeliefert wird

* **7z** – CBR und CB7 gehen über das externe `7z`. Auf einem fremden
  Rechner ist nichts installiert, worauf man sich verlassen könnte, also
  legt der Workflow es nach `packaging/bin/`; die Spec nimmt alles aus
  diesem Ordner mit, `archive.sevenzip_binary()` sucht es dort zuerst.
  Baut man von Hand und lässt den Ordner leer, fallen CBR und CB7 aus –
  der Selbsttest sagt es.
* **AVIF und JPEG XL** stecken in Erweiterungen, die nur über ihren Namen
  importiert werden. Beide stehen deshalb als `hiddenimports` in der Spec.
* **comicapi** liest sein ComicInfo-Schema aus Dateien im Paket.

## Größe

Rund 330 MB entpackt, etwa 90 MB als Download. Den Löwenanteil haben Qt
(119 MB), pymupdf (53 MB) und die ICU-Daten (30 MB). Die Spec wirft
QtQuick, WebEngine und Ähnliches schon hinaus; mehr ginge nur mit
Handarbeit an den Qt-Bibliotheken, und die bricht erfahrungsgemäß
irgendwann still etwas ab.

## Signieren

Die Pakete sind **nicht signiert**. Ein Windows-Zertifikat kostet mehrere
hundert Euro im Jahr, Apples Developer ID 99 € – für ein kostenloses
Projekt zu viel. Folgen:

* **Windows** zeigt „Der Computer wurde geschützt“. Weiter über *Weitere
  Informationen → Trotzdem ausführen*. Selbst signieren hilft nicht:
  SmartScreen kennt das Zertifikat nicht und zeigt weiterhin „Unbekannter
  Herausgeber“. Der Installer verlangt bewusst keine Administratorrechte
  und installiert unter `%LOCALAPPDATA%`, das erspart die zusätzliche
  Nachfrage der Benutzerkontensteuerung.
* **macOS** verlangt beim ersten Start *Rechtsklick → Öffnen*; ein
  Doppelklick wird abgelehnt. Der Workflow signiert die App ad hoc
  (`codesign --sign -`) – das ersetzt kein Zertifikat, ist auf Apple
  Silicon aber nötig, damit sie überhaupt startet statt als „beschädigt“
  abgelehnt zu werden.

Wenn das Projekt einmal bekannter ist, lohnt ein Antrag bei der
[SignPath Foundation](https://signpath.io/solutions/open-source-community):
sie gibt Open-Source-Projekten kostenlose Zertifikate für Windows.
Verlangt werden eine OSI-Lizenz, ein öffentliches Repo, ein Build aus
einer CI – und eine gewisse Bekanntheit des Projekts.

Für macOS gibt es keinen kostenlosen Ersatz. Der übliche Ausweg wäre ein
**Homebrew-Cask**: Casks dürfen unsignierte Software ausliefern, und
`brew` nimmt die Quarantäne-Markierung selbst weg – der Nutzer sieht dann
keine Warnung.
