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
DEFAULT_MODEL = "google/gemini-2.5-flash-lite"
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

[{{"order": 1, "kind": "speech", "speaker": "", "original": "...",
   "translation": "..."}}]

Rules:
- "kind" is one of: speech, thought, caption, sfx, sign
- "original" is the text exactly as printed, keeping line breaks as spaces
- "translation" is that text in {language}, natural and idiomatic, keeping
  the tone (shouting stays shouting, slang stays slang)
- "speaker" only if the page makes it obvious, otherwise ""
- Include sound effects; translate them if there is a common equivalent,
  otherwise repeat the original
- If the page has no text at all, return []
"""


@dataclass
class Bubble:
    order: int
    kind: str
    original: str
    translation: str
    speaker: str = ""

    @property
    def kind_label(self) -> str:
        return KINDS.get(self.kind, self.kind)


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


def _parse(text: str) -> list[Bubble]:
    """Antwort in Blasen verwandeln - Modelle verpacken JSON gern in Prosa."""
    cleaned = text.strip()
    fence = re.search(r"```(?:json)?\s*(.+?)```", cleaned, re.S)
    if fence:
        cleaned = fence.group(1).strip()
    if not cleaned.startswith("["):
        start, end = cleaned.find("["), cleaned.rfind("]")
        if start >= 0 and end > start:
            cleaned = cleaned[start:end + 1]
    try:
        raw = json.loads(cleaned)
    except json.JSONDecodeError as exc:
        raise TranslationError(
            _("Antwort des Modells war kein gültiges JSON.")) from exc
    if not isinstance(raw, list):
        raise TranslationError(_("Antwort des Modells war kein gültiges JSON."))

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
                 language: str = "Deutsch"):
        self.api_key = (api_key or "").strip()
        self.model = model or DEFAULT_MODEL
        self.language = language or "Deutsch"
        self._session = requests.Session()

    def available(self) -> tuple[bool, str]:
        if not self.api_key:
            return False, _("Kein OpenRouter-Schlüssel hinterlegt.")
        return True, ""

    def page(self, image: bytes) -> list[Bubble]:
        """Eine Seite uebersetzen. Was schon uebersetzt ist, holt der Aufrufer
        aus dem PageStore beim Comic - hier wird nichts zwischengespeichert."""
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
            "temperature": 0.2,
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
        return _parse(choices[0].get("message", {}).get("content") or "")
