"""Seiten uebersetzen lassen - als Lesehilfe, ohne die Datei anzufassen.

Ein Bildmodell bekommt die Seite und liefert die Sprechblasen in Lesereihen-
folge zurueck, im Original und uebersetzt. Der eigentliche Comic bleibt
unveraendert; wer den Text im Bild ersetzen will, braucht Retusche und Satz -
das koennen fertige Werkzeuge wie comic-translate besser.

Die Ergebnisse liegen beim Comic (bei CBZ im Archiv, sonst als Datei daneben),
nicht in einem lokalen Cache - so sind sie auf jedem Rechner da, der auf die
Sammlung zugreift. Geschluesselt wird nach Bildinhalt statt nach Seitennummer,
damit sie das Umsortieren oder Loeschen von Seiten ueberleben.
"""
from __future__ import annotations

import base64
import hashlib
import io
import json
import re
from dataclasses import dataclass

import requests

from .i18n import _
from .archive import TRANSLATIONS_NAME

API_URL = "https://openrouter.ai/api/v1/chat/completions"
DEFAULT_MODEL = "google/gemini-3.1-flash-lite"
#: Groessere Seiten kosten Token, ohne dass die Erkennung besser wird.
MAX_EDGE = 1400
TIMEOUT = 120

LANGUAGES = [
    ("Deutsch", "de"), ("English", "en"), ("Français", "fr"),
    ("Español", "es"), ("Italiano", "it"), ("Nederlands", "nl"),
]

KINDS = {
    "speech": _("Sprechblase"),
    "thought": _("Gedanke"),
    "caption": _("Textkasten"),
    "sfx": _("Geräusch"),
    "sign": _("Schild"),
}

PROMPT = """You are helping someone read a comic page in a language they do
not speak. Extract every piece of text on the page and translate it.

Return ONLY a JSON array, no prose, no code fences. One object per text
element, in natural reading order for this comic's language and layout:

[{{"order": 1, "kind": "speech", "speaker": "",
   "box": {{"left": 12.5, "top": 4.0, "right": 31.0, "bottom": 11.5}},
   "original": "...", "translation": "..."}}]

Rules:
- "kind" is one of: speech, thought, caption, sfx, sign
- "box" uses NAMED keys left/top/right/bottom, each a percentage of the page
  from 0 to 100, measured from the top-left corner. Do not use a plain array
  and do not use a 0-1000 scale.
- "original" is the text exactly as printed, keeping line breaks as spaces
- "translation" is that text in {language}, natural and idiomatic, keeping
  the tone (shouting stays shouting, slang stays slang)
- "speaker" only if the page makes it obvious, otherwise ""
- Include sound effects; translate them if there is a common equivalent,
  otherwise repeat the original
- If the page has no text at all, return []
- Answer with compact JSON on a single line. No pretty-printing, no comments.
"""


@dataclass
class Bubble:
    order: int
    kind: str
    original: str
    translation: str
    speaker: str = ""
    #: [links, oben, rechts, unten] in Prozent der Seite, oder None.
    box: list[float] | None = None

    @property
    def kind_label(self) -> str:
        return KINDS.get(self.kind, self.kind)

    @property
    def center(self) -> tuple[float, float] | None:
        if not self.box:
            return None
        x0, y0, x1, y1 = self.box
        return ((x0 + x1) / 2, (y0 + y1) / 2)


def _plausible(box: list[float]) -> bool:
    x0, y0, x1, y1 = box
    return (x1 > x0 and y1 > y0
            and all(-2 <= v <= 102 for v in box)
            and (x1 - x0) <= 98 and (y1 - y0) <= 98)


def _clean_box(value) -> list[float] | None:
    """Rahmen vereinheitlichen.

    Benannte Schluessel sind eindeutig; kommt doch eine Liste, ist die
    Reihenfolge Auslegungssache - Gemini etwa liefert von sich aus
    [ymin, xmin, ymax, xmax] auf einer 0-1000-Skala. Deshalb wird die Skala
    aus der Groessenordnung erschlossen und beide Achsenreihenfolgen
    ausprobiert; passt keine, wird der Rahmen verworfen statt geraten.
    """
    numbers: list[float]
    if isinstance(value, dict):
        try:
            numbers = [float(value[k]) for k in ("left", "top", "right", "bottom")]
        except (KeyError, TypeError, ValueError):
            return None
        varianten = [numbers]
    elif isinstance(value, (list, tuple)) and len(value) == 4:
        try:
            numbers = [float(v) for v in value]
        except (TypeError, ValueError):
            return None
        varianten = [numbers, [numbers[1], numbers[0], numbers[3], numbers[2]]]
    else:
        return None

    faktor = 0.1 if max(abs(n) for n in numbers) > 100 else 1.0
    for kandidat in varianten:
        box = [round(n * faktor, 2) for n in kandidat]
        if box[2] < box[0]:
            box[0], box[2] = box[2], box[0]
        if box[3] < box[1]:
            box[1], box[3] = box[3], box[1]
        if _plausible(box):
            return [max(0.0, box[0]), max(0.0, box[1]),
                    min(100.0, box[2]), min(100.0, box[3])]
    return None


def reading_order(bubbles: list[Bubble], right_to_left: bool = False
                  ) -> list[Bubble]:
    """Nach Lage sortieren statt der Nummerierung des Modells zu vertrauen.

    Zeilenweise von oben nach unten, innerhalb einer Zeile von links nach
    rechts - bei Manga umgekehrt. Fehlt auch nur ein Rahmen, bleibt die
    Reihenfolge des Modells stehen; halb geraten waere schlechter als gar
    nicht.
    """
    if not bubbles or any(b.box is None for b in bubbles):
        return bubbles
    hoehen = sorted(b.box[3] - b.box[1] for b in bubbles)
    toleranz = max(3.0, hoehen[len(hoehen) // 2] * 0.7)

    rest = sorted(bubbles, key=lambda b: b.box[1])
    zeilen: list[list[Bubble]] = []
    for bubble in rest:
        oben = bubble.box[1]
        for zeile in zeilen:
            if abs(oben - zeile[0].box[1]) <= toleranz:
                zeile.append(bubble)
                break
        else:
            zeilen.append([bubble])

    sortiert: list[Bubble] = []
    for zeile in zeilen:
        zeile.sort(key=lambda b: b.box[0], reverse=right_to_left)
        sortiert += zeile
    for position, bubble in enumerate(sortiert, 1):
        bubble.order = position
    return sortiert


class TranslationError(RuntimeError):
    pass


def _shrink(data: bytes) -> tuple[bytes, str]:
    """Seite verkleinern - spart Token, ohne der Erkennung zu schaden."""
    try:
        from PIL import Image

        image = Image.open(io.BytesIO(data))
        if max(image.size) > MAX_EDGE:
            ratio = MAX_EDGE / max(image.size)
            image = image.resize(
                (max(1, round(image.width * ratio)),
                 max(1, round(image.height * ratio))), Image.LANCZOS)
        if image.mode not in ("RGB", "L"):
            image = image.convert("RGB")
        buffer = io.BytesIO()
        image.save(buffer, "JPEG", quality=80)
        return buffer.getvalue(), "image/jpeg"
    except Exception:  # noqa: BLE001
        return data, "image/jpeg"


def _flatten(value) -> str:
    """Zeilenumbrueche aus dem Bild zu Leerzeichen - im Panel sonst zerrissen."""
    return re.sub(r"\s+", " ", str(value or "")).strip()


def _objects(text: str):
    """Vollstaendige {...}-Bloecke herausziehen, Zeichenketten respektierend.

    Rettet den brauchbaren Teil, wenn die Antwort mittendrin abbricht oder in
    Prosa eingebettet ist - besser elf von zwoelf Blasen als eine Fehlermeldung.
    """
    depth = 0
    start = None
    in_string = False
    escaped = False
    for position, char in enumerate(text):
        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
            continue
        if char == '"':
            in_string = True
        elif char == "{":
            if depth == 0:
                start = position
            depth += 1
        elif char == "}":
            depth = max(0, depth - 1)
            if depth == 0 and start is not None:
                yield text[start:position + 1]
                start = None


def _strip_fence(text: str) -> str:
    cleaned = text.strip()
    fence = re.search(r"```(?:json)?\s*(.+?)```", cleaned, re.S)
    if fence:
        return fence.group(1).strip()
    # Zaun ohne Abschluss - kommt vor, wenn die Antwort abbricht.
    return re.sub(r"^```(?:json)?\s*", "", cleaned)


def _parse(text: str) -> list[Bubble]:
    """Antwort in Blasen verwandeln - Modelle verpacken JSON gern in Prosa."""
    cleaned = _strip_fence(text)
    raw: list = []
    gelesen = False
    start, end = cleaned.find("["), cleaned.rfind("]")
    if start >= 0 and end > start:
        try:
            candidate = json.loads(cleaned[start:end + 1])
        except json.JSONDecodeError:
            candidate = None
        if isinstance(candidate, list):
            raw, gelesen = candidate, True   # [] heisst: kein Text, kein Fehler
    if not gelesen:
        # Abgebrochen oder verziert: Block fuer Block bergen.
        for block in _objects(cleaned):
            try:
                item = json.loads(block)
            except json.JSONDecodeError:
                continue
            if isinstance(item, dict) and ("original" in item or "translation" in item):
                raw.append(item)
                gelesen = True
    if not gelesen:
        raise TranslationError(
            _("Antwort des Modells war kein gültiges JSON."))

    bubbles: list[Bubble] = []
    for position, item in enumerate(raw, 1):
        if not isinstance(item, dict):
            continue
        original = _flatten(item.get("original"))
        translation = _flatten(item.get("translation"))
        if not original and not translation:
            continue
        try:
            order = int(item.get("order") or position)
        except (TypeError, ValueError):
            order = position
        bubbles.append(Bubble(
            order=order,
            kind=str(item.get("kind") or "speech").lower(),
            original=original,
            translation=translation,
            speaker=str(item.get("speaker") or "").strip(),
            box=_clean_box(item.get("box")),
        ))
    bubbles.sort(key=lambda b: b.order)
    return bubbles


class PageStore:
    """Uebersetzungen liegen beim Comic, nicht im lokalen Cache.

    Geschluesselt wird nach Bildinhalt, nicht nach Seitennummer: so ueberleben
    sie das Loeschen oder Umsortieren von Seiten.
    """

    VERSION = 1

    def __init__(self, comic):
        self.comic = comic
        self._data: dict = {"version": self.VERSION, "pages": {}}
        self._dirty = False
        raw = None
        try:
            raw = comic.read_extra(TRANSLATIONS_NAME)
        except Exception:  # noqa: BLE001
            raw = None
        if raw:
            try:
                loaded = json.loads(raw.decode("utf-8"))
                if isinstance(loaded.get("pages"), dict):
                    self._data = loaded
            except (json.JSONDecodeError, AttributeError, UnicodeDecodeError):
                pass

    @staticmethod
    def key(image: bytes) -> str:
        return hashlib.sha1(image).hexdigest()

    def get(self, image: bytes, language: str) -> list[Bubble] | None:
        entry = self._data["pages"].get(self.key(image), {}).get(language)
        if entry is None:
            return None
        return [Bubble(**item) for item in entry]

    def put(self, image: bytes, language: str, bubbles: list[Bubble]) -> None:
        page = self._data["pages"].setdefault(self.key(image), {})
        page[language] = [b.__dict__ for b in bubbles]
        self._dirty = True

    @property
    def dirty(self) -> bool:
        return self._dirty

    @property
    def count(self) -> int:
        return len(self._data["pages"])

    def save(self) -> bool:
        """Beim Schliessen schreiben - nicht pro Seite, das Archiv wird dabei
        neu geschrieben."""
        if not self._dirty:
            return False
        payload = json.dumps(self._data, ensure_ascii=False,
                             separators=(",", ":")).encode("utf-8")
        self.comic.write_extra(TRANSLATIONS_NAME, payload)
        self._dirty = False
        return True


class Translator:
    def __init__(self, api_key: str, model: str = DEFAULT_MODEL,
                 language: str = "Deutsch", right_to_left: bool = False):
        self.api_key = (api_key or "").strip()
        self.model = model or DEFAULT_MODEL
        self.language = language or "Deutsch"
        self.right_to_left = right_to_left
        self._session = requests.Session()

    def available(self) -> tuple[bool, str]:
        if not self.api_key:
            return False, _("Kein OpenRouter-Schlüssel hinterlegt.")
        return True, ""

    def page(self, image: bytes, attempts: int = 2,
             best_of: int = 1) -> list[Bubble]:
        """Eine Seite uebersetzen.

        Die Modelle antworten nicht deterministisch und uebersehen mal eine
        Blase: an einer Testseite lieferte dasselbe Modell 2, 14, 14 und 14
        Stellen. `attempts` faengt Fehlschlaege ab, `best_of` laesst mehrfach
        laufen und nimmt den vollstaendigsten Lauf - das kostet entsprechend
        mehr und wird deshalb nur auf Wunsch gemacht.
        """
        bester: list[Bubble] | None = None
        letzter: Exception | None = None
        for _durchgang in range(max(1, best_of)):
            for _versuch in range(max(1, attempts)):
                try:
                    ergebnis = self._once(image)
                except TranslationError as exc:
                    letzter = exc
                    if "JSON" not in str(exc) and "abgebrochen" not in str(exc):
                        raise
                    continue
                if bester is None or len(ergebnis) > len(bester):
                    bester = ergebnis
                break
        if bester is None:
            raise letzter or TranslationError(
                _("Antwort des Modells war kein gültiges JSON."))
        return bester

    def _once(self, image: bytes) -> list[Bubble]:
        payload, mime = _shrink(image)
        encoded = base64.b64encode(payload).decode()
        body = {
            "model": self.model,
            "messages": [{
                "role": "user",
                "content": [
                    {"type": "text",
                     "text": PROMPT.format(language=self.language)},
                    {"type": "image_url",
                     "image_url": {"url": f"data:{mime};base64,{encoded}"}},
                ],
            }],
            "temperature": 0,
        }
        response = self._session.post(
            API_URL, json=body, timeout=TIMEOUT,
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "HTTP-Referer": "https://github.com/aaaaaprvdgrwwelt/comicdesk",
                "X-Title": "ComicDesk",
            })
        if response.status_code == 401:
            raise TranslationError(_("OpenRouter lehnt den Schlüssel ab."))
        if response.status_code == 429:
            raise TranslationError(
                _("OpenRouter drosselt gerade – später erneut versuchen."))
        if not response.ok:
            raise TranslationError(
                _("OpenRouter antwortete mit {code}: {text}").format(
                    code=response.status_code, text=response.text[:200]))
        data = response.json()
        choices = data.get("choices") or []
        if not choices:
            raise TranslationError(
                _("OpenRouter lieferte keine Antwort: {error}").format(
                    error=str(data.get("error") or "")[:200]))
        choice = choices[0]
        content = (choice.get("message") or {}).get("content") or ""
        reason = choice.get("finish_reason")
        try:
            bubbles = _parse(content)
        except TranslationError:
            if reason and reason not in ("stop", "end_turn"):
                raise TranslationError(
                    _("Das Modell hat die Antwort abgebrochen ({reason}). "
                      "Noch einmal versuchen.").format(reason=reason)) from None
            raise
        return reading_order(bubbles, self.right_to_left)
