"""Seiten uebersetzen lassen - als Lesehilfe, ohne die Datei anzufassen.

Ein Bildmodell bekommt die Seite und liefert die Sprechblasen in Lesereihen-
folge zurueck, im Original und uebersetzt. Der eigentliche Comic bleibt
unveraendert; wer den Text im Bild ersetzen will, braucht Retusche und Satz -
das koennen fertige Werkzeuge wie comic-translate besser.

Die Antworten werden nach Bildinhalt zwischengespeichert, nicht nach Dateiname:
so kostet erneutes Lesen nichts, auch wenn die Datei umbenannt wurde.
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
from .providers.cache import ResponseCache

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
        original = str(item.get("original") or "").strip()
        translation = str(item.get("translation") or "").strip()
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


class Translator:
    def __init__(self, api_key: str, model: str = DEFAULT_MODEL,
                 language: str = "Deutsch"):
        self.api_key = (api_key or "").strip()
        self.model = model or DEFAULT_MODEL
        self.language = language or "Deutsch"
        self._cache = ResponseCache("translations.sqlite", ttl_days=3650)
        self._session = requests.Session()

    def available(self) -> tuple[bool, str]:
        if not self.api_key:
            return False, _("Kein OpenRouter-Schlüssel hinterlegt.")
        return True, ""

    def page(self, image: bytes, force: bool = False) -> list[Bubble]:
        digest = hashlib.sha1(image).hexdigest()
        key = f"{digest}|{self.model}|{self.language}"
        if not force:
            cached = self._cache.get(key)
            if cached is not None:
                return [Bubble(**item) for item in cached]

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
        bubbles = _parse(choices[0].get("message", {}).get("content") or "")
        self._cache.put(key, [b.__dict__ for b in bubbles])
        return bubbles
