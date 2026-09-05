"""Hilfe: was comicdesk kann und wie man an die noetigen API-Keys kommt."""
from __future__ import annotations

from deskkit.helpdialog import HelpDialog as _HelpDialog

from .i18n import _

HELP_HTML = """
<h2>Erste Schritte</h2>
<ol>
<li>Ordner mit Comics ueber die Pfadleiste oder <b>Sammlungen …</b> anlegen -
    eine Sammlung kann mehrere Ordner haben.</li>
<li><b>Sammlung indizieren …</b> liest die Ordner ein und macht die
    Volltextsuche moeglich.</li>
<li>Unter <b>Quellen …</b> mindestens einen API-Key hinterlegen (siehe unten) -
    ComicVine allein reicht schon fuer die meisten Serien.</li>
<li><b>Automatisch taggen</b> sucht Metadaten. Unsichere oder fehlgeschlagene
    Treffer bleiben markiert und lassen sich per <i>Treffer waehlen …</i>
    von Hand nachtragen.</li>
</ol>

<h2>Welche Quelle wofuer?</h2>
<p>Alle Quellen sind optional und lassen sich einzeln unter
<b>Quellen …</b> ein- und ausschalten.</p>

<h3>ComicVine - empfohlen, deckt die meisten Serien ab</h3>
<p>Kostenlos nach Registrierung. Limit 200 Anfragen/Stunde, deshalb wird
gedrosselt und dauerhaft gecacht. Liefert Cover, damit ist die
Bild-Verifikation moeglich.</p>
<ol>
<li>Kostenloses Konto auf <a href="https://comicvine.gamespot.com/api/">comicvine.gamespot.com/api</a>
    anlegen.</li>
<li>Den API-Key von dort in <b>Quellen … &rarr; ComicVine</b> eintragen.</li>
</ol>

<h3>Grand Comics Database (lokaler Dump) - stark bei europaeischen Verlagen</h3>
<p>SQLite3-Dump von comics.org/download (Account noetig, Daten CC-BY). Offline
und ohne Limit. Enthaelt keine Cover, daher kein Bildabgleich.</p>
<ol>
<li>Account auf <a href="https://comics.org">comics.org</a> anlegen und den
    SQLite3-Dump herunterladen.</li>
<li>Pfad zur Datei in <b>Quellen … &rarr; GCD</b> eintragen.</li>
<li>Einmalig <b>Indizes anlegen</b> ausfuehren - beschleunigt die Suche
    erheblich.</li>
</ol>

<h3>AniList - ergaenzt Manga-Serien, kein Key noetig</h3>
<p>Kennt Manga-Serien, aber keine einzelnen Baende einer deutschen Ausgabe.
Bestimmt deshalb nie das Heft, sondern fuellt nur Luecken: Zeichner, Autor,
Genre, Beschreibung, Leserichtung. Vorhandene Angaben bleiben unangetastet.</p>

<h2>Tastenkuerzel</h2>
<table cellpadding="4">
<tr><td><b>Strg+F</b></td><td>Suchen</td></tr>
<tr><td><b>Strg+T</b></td><td>Automatisch taggen</td></tr>
<tr><td><b>Strg+R</b></td><td>Nach Tags benennen</td></tr>
<tr><td><b>F2</b></td><td>Umbenennen</td></tr>
<tr><td><b>Entf</b></td><td>Loeschen (Papierkorb)</td></tr>
<tr><td><b>Strg+Umschalt+T</b></td><td>Treffer waehlen …</td></tr>
<tr><td><b>Strg+P</b></td><td>Seiten verwalten …</td></tr>
<tr><td><b>Strg+D</b></td><td>Zu Favoriten hinzufuegen</td></tr>
<tr><td><b>Strg+Umschalt+M</b></td><td>Sammlungen …</td></tr>
<tr><td><b>Strg+,</b></td><td>Einstellungen …</td></tr>
<tr><td><b>F5</b></td><td>Aktualisieren</td></tr>
</table>

<h2>Loeschen</h2>
<p>Verschiebt Dateien in den Papierkorb, nichts wird endgueltig geloescht.</p>

<h2>Wo Daten liegen</h2>
<table cellpadding="4">
<tr><td>Einstellungen</td><td><code>~/.config/comicdesk/comicdesk.conf</code></td></tr>
<tr><td>Sammlungsindex, Favoriten, Listen</td><td><code>~/.local/share/comicdesk/</code></td></tr>
<tr><td>Antwort-Cache, Cover-Thumbnails</td><td><code>~/.cache/comicdesk/</code></td></tr>
</table>
<p>Anders als bei moviedesk steckt die Wahrheit ueber Metadaten hier direkt in
der Datei selbst (<code>ComicInfo.xml</code> im Archiv) - der Sammlungsindex
ist nur eine durchsuchbare Kopie davon, kein eigenes Format.</p>
"""


class HelpDialog(_HelpDialog):
    def __init__(self, parent=None):
        super().__init__(HELP_HTML, _("Hilfe"), parent)
