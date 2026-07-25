"""Seitenbilder eines Comics neu kodieren.

Alte Sammlungen bestehen meist aus JPEG-Scans; WebP und AVIF holen bei
gleichem Aussehen ein Drittel bis die Haelfte heraus. Das Ergebnis ist immer
ein CBZ - das einzige Archivformat, das hier auch geschrieben wird.

Zwei Regeln halten den Verlust klein: Seiten, die schon im Zielformat
vorliegen und nicht verkleinert werden, bleiben unangetastet (kein
Generationenverlust durch wiederholtes Kodieren), und ein Ergebnis, das
groesser ausfaellt als das Original, wird verworfen.
"""
from __future__ import annotations

import io
import zipfile
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path

from PIL import Image

from . import archive
from .archive import CIX_NAME, ComicError, open_comic
from .i18n import _

# Pillow laedt seine Kodierer erst bei Bedarf - ohne das fehlt AVIF in
# Image.SAVE, obwohl es einkompiliert ist.
Image.init()

try:                        # JPEG XL kommt nur mit Zusatzpaket
    import pillow_jxl       # noqa: F401
except ImportError:
    pass


@dataclass(frozen=True)
class Format:
    key: str            #: Pillow-Name
    suffix: str
    label: str
    #: Kann das Format Transparenz? Sonst wird auf weiss gelegt.
    alpha: bool
    lossless: bool      #: Ist verlustfreies Kodieren moeglich?


FORMATS = {
    "WEBP": Format("WEBP", ".webp", "WebP", True, True),
    "AVIF": Format("AVIF", ".avif", "AVIF", True, False),
    "JXL": Format("JXL", ".jxl", "JPEG XL", True, True),
    "JPEG": Format("JPEG", ".jpg", "JPEG", False, False),
    "PNG": Format("PNG", ".png", "PNG (verlustfrei)", True, True),
}


def available_formats() -> list[Format]:
    """Nur, was diese Pillow-Fassung auch schreiben kann.

    JPEG XL faellt weg, wenn `pillow-jxl-plugin` fehlt - es ist nicht
    ueberall als fertiges Paket zu haben.
    """
    return [f for f in FORMATS.values() if f.key in Image.SAVE]


@dataclass
class Options:
    format: str = "WEBP"
    quality: int = 80
    lossless: bool = False
    #: Laengere Seite begrenzen. 0 heisst: Groesse unveraendert lassen.
    max_edge: int = 0
    #: Ergebnis nur nehmen, wenn es kleiner ist als das Original.
    only_if_smaller: bool = True
    threads: int = 4

    @property
    def spec(self) -> Format:
        return FORMATS[self.format]


@dataclass
class Result:
    pages: int = 0
    converted: int = 0      #: neu kodiert
    kept: int = 0           #: Original behalten (schon passend oder groesser)
    failed: int = 0
    old_bytes: int = 0
    new_bytes: int = 0
    old_file: int = 0
    new_file: int = 0

    @property
    def saved(self) -> int:
        return max(0, self.old_file - self.new_file)

    @property
    def percent(self) -> int:
        """Ersparnis in Prozent - negativ, wenn die Datei gewachsen ist."""
        if not self.old_file:
            return 0
        return round((self.old_file - self.new_file) * 100 / self.old_file)


def _save_args(options: Options) -> dict:
    spec = options.spec
    if spec.key == "PNG":
        return {"optimize": True}
    if spec.key == "WEBP":
        if options.lossless:
            return {"lossless": True, "quality": 100, "method": 4}
        return {"quality": options.quality, "method": 4}
    if spec.key == "AVIF":
        # speed 6 ist der uebliche Kompromiss; darunter dauert eine Seite
        # mehrere Sekunden, ohne nennenswert kleiner zu werden.
        return {"quality": options.quality, "speed": 6}
    if spec.key == "JXL":
        if options.lossless:
            return {"lossless": True}
        return {"quality": options.quality, "effort": 7}
    return {"quality": options.quality, "optimize": True,
            "progressive": True}


def _repack_jpeg(data: bytes, bild: Image.Image) -> bytes | None:
    """JPEG bit-genau als JPEG XL verpacken.

    JPEG XL kann ein JPEG verlustfrei umpacken: die Bildpunkte bleiben
    identisch, die Datei wird rund ein Fuenftel kleiner. Fuer Sammlungen aus
    JPEG-Scans der beste Handel, den es gibt - es geht nichts verloren.
    """
    try:
        from pillow_jxl import Encoder

        encoder = Encoder(mode=bild.mode, lossless=True, quality=100,
                          effort=7, num_threads=1, decoding_speed=0,
                          use_container=True, use_original_profile=True)
        return bytes(encoder(data, bild.width, bild.height, jpeg_encode=True))
    except Exception:  # noqa: BLE001
        return None


def encode(data: bytes, options: Options) -> bytes | None:
    """Eine Seite umkodieren. None heisst: Original behalten."""
    spec = options.spec
    with Image.open(io.BytesIO(data)) as bild:
        bild.load()
        breite, hoehe = bild.size
        skalieren = bool(options.max_edge) and max(breite, hoehe) > options.max_edge
        if bild.format == spec.key and not skalieren and not options.lossless:
            return None         # schon im Zielformat - nicht neu kodieren
        if (spec.key == "JXL" and options.lossless and not skalieren
                and bild.format == "JPEG"):
            gepackt = _repack_jpeg(data, bild)
            if gepackt is not None:
                return gepackt if len(gepackt) < len(data) else None
        if skalieren:
            faktor = options.max_edge / max(breite, hoehe)
            bild = bild.resize((max(1, round(breite * faktor)),
                                max(1, round(hoehe * faktor))),
                               Image.LANCZOS)
        bild = _prepare(bild, spec)
        puffer = io.BytesIO()
        bild.save(puffer, spec.key, **_save_args(options))
    neu = puffer.getvalue()
    if options.only_if_smaller and len(neu) >= len(data) and not skalieren:
        return None
    return neu


def _prepare(bild: Image.Image, spec: Format) -> Image.Image:
    """Farbmodus passend machen - JPEG kennt weder Palette noch Alpha."""
    if bild.mode == "P":
        bild = bild.convert("RGBA" if "transparency" in bild.info else "RGB")
    if bild.mode in ("RGBA", "LA") and not spec.alpha:
        # Transparenz auf Weiss legen; Comicseiten sind sonst stellenweise
        # schwarz, wo eigentlich Papier ist.
        grund = Image.new("RGB", bild.size, (255, 255, 255))
        grund.paste(bild, mask=bild.split()[-1])
        return grund
    if bild.mode == "CMYK" or (bild.mode not in ("RGB", "RGBA", "L")
                               and not spec.alpha):
        return bild.convert("RGB")
    if bild.mode not in ("RGB", "RGBA", "L", "LA"):
        return bild.convert("RGBA" if spec.alpha else "RGB")
    return bild


def sample(path: Path, options: Options, index: int | None = None
           ) -> tuple[int, int]:
    """Eine Seite probeweise kodieren: (alt, neu) in Bytes."""
    comic = open_comic(path)
    try:
        if comic.page_count == 0:
            raise ComicError(_("Keine Seiten gefunden."))
        # Die Mitte des Hefts ist aussagekraeftiger als das Cover, das oft
        # in anderer Qualitaet vorliegt.
        seite = comic.page_count // 2 if index is None else index
        alt = comic.page_bytes(seite)
        neu = encode(alt, options)
        return len(alt), len(neu if neu is not None else alt)
    finally:
        comic.close()


def _target_name(name: str, index: int, spec: Format) -> str:
    """Pfad im neuen Archiv: derselbe wie vorher, nur andere Endung.

    Der Pfad bestimmt die Seitenreihenfolge. Wird er umgeschrieben, kann
    ein `cover.jpg` aus dem Oberordner hinter die Seite 1 rutschen.
    """
    pfad = Path(name)
    if not pfad.stem:
        return f"{index + 1:04d}{spec.suffix}"
    return str(pfad.with_suffix(spec.suffix))


class Abort(Exception):
    """Der Lauf wurde abgebrochen - das halbe Ergebnis wird verworfen."""


def convert_archive(path: Path, dest: Path, options: Options,
                    progress=None, should_stop=None) -> Result:
    """Alle Seiten umkodieren und als CBZ nach `dest` schreiben.

    Verarbeitet wird in Haeppchen: ein 460-Seiten-Manga passt entpackt nicht
    sinnvoll in den Speicher, also werden immer nur so viele Seiten gelesen,
    wie gleichzeitig kodiert werden.
    """
    ergebnis = Result()
    comic = open_comic(path)
    spec = options.spec
    faeden = max(1, options.threads)
    try:
        ergebnis.pages = comic.page_count
        if ergebnis.pages == 0:
            raise ComicError(_("Keine Seiten gefunden."))
        cix = comic._read_cix()
        with ThreadPoolExecutor(max_workers=faeden) as pool, \
                zipfile.ZipFile(dest, "w", zipfile.ZIP_STORED) as zf:
            for start in range(0, ergebnis.pages, faeden):
                if should_stop is not None and should_stop():
                    raise Abort
                haeppchen = [
                    (i, comic.page_name(i), comic.page_bytes(i))
                    for i in range(start, min(start + faeden, ergebnis.pages))
                ]
                for index, label, roh, neu, fehler in pool.map(
                        lambda job: _encode_job(job, options), haeppchen):
                    daten = roh if neu is None else neu
                    name = (_target_name(label, index, spec) if neu is not None
                            else label or f"{index + 1:04d}.jpg")
                    zf.writestr(name, daten)
                    ergebnis.old_bytes += len(roh)
                    ergebnis.new_bytes += len(daten)
                    if fehler:
                        ergebnis.failed += 1
                    elif neu is not None:
                        ergebnis.converted += 1
                    else:
                        ergebnis.kept += 1
                if progress is not None:
                    progress(min(start + faeden, ergebnis.pages), ergebnis.pages)
            if cix:
                # Bilder sind bereits komprimiert, das XML nicht.
                zf.writestr(CIX_NAME, cix, zipfile.ZIP_DEFLATED)
    except BaseException:
        dest.unlink(missing_ok=True)
        raise
    finally:
        comic.close()
    ergebnis.old_file = path.stat().st_size
    ergebnis.new_file = dest.stat().st_size
    return ergebnis


def _encode_job(job, options: Options):
    index, label, roh = job
    try:
        return index, label, roh, encode(roh, options), False
    except Exception:  # noqa: BLE001
        return index, label, roh, None, True


def human(size: float) -> str:
    """Byte-Zahl kurz und lesbar."""
    for einheit in ("B", "KB", "MB", "GB"):
        if abs(size) < 1024 or einheit == "GB":
            return f"{size:.0f} {einheit}" if einheit in ("B", "KB") \
                else f"{size:.1f} {einheit}"
        size /= 1024
    return f"{size:.1f} GB"


def is_convertible(path: Path) -> bool:
    return path.is_file() and archive.is_comic(path)
