"""Lesen von Comic-Archiven (CBZ/CBR/CB7/CBT/PDF) und deren Metadaten.

Bewusst unabhaengig von comicapi's Archiv-Backends: comicapi braucht fuer RAR
das externe `unrar`, das nicht ueberall vorhanden ist. Hier wird stattdessen
`7z` verwendet, das RAR ebenfalls lesen kann. comicapi wird nur noch fuer das
ComicInfo.xml-Mapping benutzt.
"""
from __future__ import annotations

import os
import re
import shutil
import subprocess
import tarfile
import tempfile
import zipfile
from pathlib import Path

from comicapi.comicinfoxml import ComicInfoXml
from comicapi.genericmetadata import GenericMetadata

from .i18n import _

IMAGE_EXT = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp", ".avif", ".jxl"}
ARCHIVE_EXT = {".cbz", ".cbr", ".cb7", ".cbt", ".zip"}
COMIC_EXT = ARCHIVE_EXT | {".pdf"}

CIX_NAME = "ComicInfo.xml"

_num_re = re.compile(r"(\d+)")


def natural_key(s: str):
    return [int(p) if p.isdigit() else p.lower() for p in _num_re.split(s)]


def is_comic(path: Path) -> bool:
    return path.suffix.lower() in COMIC_EXT


def sevenzip_binary() -> str | None:
    for name in ("7z", "7zz", "7za"):
        found = shutil.which(name)
        if found:
            return found
    return None


class ComicError(Exception):
    pass


# --- freie Tags -----------------------------------------------------------
# comicapi 1.5.5 serialisiert GenericMetadata.tags nicht, ComicInfo v2.1 kennt
# aber ein <Tags>-Element. Deshalb hier von Hand ergaenzen bzw. auslesen.
def _tags_from_xml(raw: str) -> set[str]:
    import xml.etree.ElementTree as ET

    try:
        root = ET.fromstring(raw)
    except ET.ParseError:
        return set()
    node = root.find("Tags")
    if node is None or not node.text:
        return set()
    return {t.strip() for t in node.text.split(",") if t.strip()}


def metadata_to_xml(md: GenericMetadata) -> str:
    import xml.etree.ElementTree as ET

    raw = ComicInfoXml().string_from_metadata(md)
    if not md.tags:
        return raw
    root = ET.fromstring(raw)
    for old in root.findall("Tags"):
        root.remove(old)
    ET.SubElement(root, "Tags").text = ", ".join(sorted(md.tags))
    ET.indent(root)
    return ET.tostring(root, encoding="unicode", xml_declaration=True)


class ComicFile:
    """Gemeinsame Schnittstelle fuer alle Comic-Formate."""

    def __init__(self, path: Path):
        self.path = Path(path)

    # --- Seiten -------------------------------------------------------
    @property
    def page_count(self) -> int:
        raise NotImplementedError

    def page_bytes(self, index: int) -> bytes:
        """Rohdaten der Seite als Bilddatei-Bytes."""
        raise NotImplementedError

    def page_label(self, index: int) -> str:
        """Anzeigename der Seite - fuer die Seitenverwaltung."""
        return str(index + 1)

    # --- Seiten bearbeiten --------------------------------------------
    @property
    def can_edit_pages(self) -> bool:
        return False

    def save_page_order(self, order: list[int]) -> None:
        """Seiten neu anordnen bzw. loeschen.

        `order` enthaelt die urspruenglichen Seitenindizes in der gewuenschten
        Reihenfolge; was fehlt, wird geloescht.
        """
        raise ComicError(
            _("Seiten koennen in {suffix} nicht bearbeitet werden. Datei "
              "zuerst nach CBZ konvertieren.").format(
                suffix=self.path.suffix.upper()))

    # --- Metadaten ----------------------------------------------------
    def read_metadata(self) -> GenericMetadata:
        raw = self._read_cix()
        if not raw:
            return GenericMetadata()
        try:
            md = ComicInfoXml().metadata_from_string(raw)
        except Exception:
            return GenericMetadata()
        md.tags = _tags_from_xml(raw)
        return md

    def write_metadata(self, md: GenericMetadata) -> None:
        raise ComicError(
            _("Metadaten koennen in {suffix} nicht geschrieben werden. "
              "Datei zuerst nach CBZ konvertieren.").format(
                suffix=self.path.suffix.upper()))

    @property
    def writable(self) -> bool:
        return False

    def _read_cix(self) -> str | None:
        return None

    def close(self) -> None:
        pass


# ---------------------------------------------------------------------------
# ZIP / CBZ
# ---------------------------------------------------------------------------
class ZipComic(ComicFile):
    def __init__(self, path: Path):
        super().__init__(path)
        self._zf = zipfile.ZipFile(self.path)
        self._names = sorted(
            (n for n in self._zf.namelist()
             if not n.endswith("/") and Path(n).suffix.lower() in IMAGE_EXT
             and not Path(n).name.startswith(".")),
            key=natural_key,
        )

    @property
    def page_count(self) -> int:
        return len(self._names)

    def page_bytes(self, index: int) -> bytes:
        return self._zf.read(self._names[index])

    def _read_cix(self) -> str | None:
        for name in self._zf.namelist():
            if Path(name).name.lower() == CIX_NAME.lower():
                return self._zf.read(name).decode("utf-8", "replace")
        return None

    @property
    def writable(self) -> bool:
        return os.access(self.path, os.W_OK)

    def write_metadata(self, md: GenericMetadata) -> None:
        md.set_default_page_list(self.page_count)
        md.page_count = self.page_count
        xml = metadata_to_xml(md)
        _zip_replace_member(self.path, CIX_NAME, xml.encode("utf-8"))
        self._reopen()

    def page_label(self, index: int) -> str:
        return Path(self._names[index]).name

    @property
    def can_edit_pages(self) -> bool:
        return os.access(self.path, os.W_OK)

    def save_page_order(self, order: list[int]) -> None:
        if not order:
            raise ComicError(_("Ein Comic braucht mindestens eine Seite."))
        metadata = self.read_metadata()
        width = max(3, len(str(len(order))))
        tmp = _temp_beside(self.path, ".cbz")
        try:
            with zipfile.ZipFile(self.path) as src, zipfile.ZipFile(
                tmp, "w", zipfile.ZIP_DEFLATED
            ) as dst:
                for position, old_index in enumerate(order, 1):
                    name = self._names[old_index]
                    suffix = Path(name).suffix.lower()
                    dst.writestr(f"{position:0{width}d}{suffix}", src.read(name))
                # Alles, was kein Bild ist, bleibt erhalten (ausser ComicInfo).
                for item in src.infolist():
                    keep = (Path(item.filename).suffix.lower() not in IMAGE_EXT
                            and Path(item.filename).name.lower() != CIX_NAME.lower()
                            and not item.is_dir())
                    if keep:
                        dst.writestr(item, src.read(item.filename))
                if not metadata.is_empty:
                    metadata.pages = []
                    metadata.set_default_page_list(len(order))
                    metadata.page_count = len(order)
                    dst.writestr(CIX_NAME, metadata_to_xml(metadata).encode("utf-8"))
            shutil.copystat(self.path, tmp)
            self._zf.close()
            os.replace(tmp, self.path)
        except Exception:
            tmp.unlink(missing_ok=True)
            raise
        finally:
            self._reopen()

    def _reopen(self) -> None:
        try:
            self._zf.close()
        except Exception:  # noqa: BLE001
            pass
        self._zf = zipfile.ZipFile(self.path)
        self._names = sorted(
            (n for n in self._zf.namelist()
             if not n.endswith("/") and Path(n).suffix.lower() in IMAGE_EXT
             and not Path(n).name.startswith(".")),
            key=natural_key,
        )

    def close(self) -> None:
        self._zf.close()


def _temp_beside(path: Path, suffix: str) -> Path:
    """Temp-Datei im selben Verzeichnis - damit os.replace atomar bleibt."""
    fd, name = tempfile.mkstemp(dir=str(path.parent), suffix=".tmp" + suffix)
    os.close(fd)
    return Path(name)


def _zip_replace_member(path: Path, member: str, data: bytes) -> None:
    """Ersetzt bzw. ergaenzt einen Eintrag im ZIP (via Neuschreiben)."""
    tmp = _temp_beside(path, ".cbz")
    try:
        with zipfile.ZipFile(path) as src, zipfile.ZipFile(
            tmp, "w", zipfile.ZIP_DEFLATED
        ) as dst:
            for item in src.infolist():
                if Path(item.filename).name.lower() == member.lower():
                    continue
                dst.writestr(item, src.read(item.filename))
            dst.writestr(member, data)
        shutil.copystat(path, tmp)
        os.replace(tmp, path)
    except Exception:
        tmp.unlink(missing_ok=True)
        raise


# ---------------------------------------------------------------------------
# RAR / 7z / TAR - per 7z bzw. tarfile in ein Temp-Verzeichnis entpackt
# ---------------------------------------------------------------------------
class ExtractedComic(ComicFile):
    """Archive, die einmalig in ein Temp-Verzeichnis entpackt werden."""

    def __init__(self, path: Path):
        super().__init__(path)
        self._dir: Path | None = None
        self._names: list[Path] = []

    def _ensure(self) -> None:
        if self._dir is not None:
            return
        self._dir = Path(tempfile.mkdtemp(prefix="comicdesk-"))
        self._extract(self._dir)
        self._names = sorted(
            (p for p in self._dir.rglob("*")
             if p.is_file() and p.suffix.lower() in IMAGE_EXT
             and not p.name.startswith(".")),
            key=lambda p: natural_key(str(p.relative_to(self._dir))),
        )

    def _extract(self, dest: Path) -> None:
        raise NotImplementedError

    @property
    def page_count(self) -> int:
        self._ensure()
        return len(self._names)

    def page_bytes(self, index: int) -> bytes:
        self._ensure()
        return self._names[index].read_bytes()

    def _read_cix(self) -> str | None:
        self._ensure()
        assert self._dir is not None
        for p in self._dir.rglob("*"):
            if p.is_file() and p.name.lower() == CIX_NAME.lower():
                return p.read_text("utf-8", "replace")
        return None

    def close(self) -> None:
        if self._dir is not None:
            shutil.rmtree(self._dir, ignore_errors=True)
            self._dir = None


class SevenZipComic(ExtractedComic):
    def _extract(self, dest: Path) -> None:
        exe = sevenzip_binary()
        if not exe:
            raise ComicError(_(
                "7z ist nicht installiert - CBR/CB7 koennen nicht gelesen "
                "werden.\nInstallation: sudo apt install p7zip-full p7zip-rar"
            ))
        res = subprocess.run(
            [exe, "x", "-y", f"-o{dest}", str(self.path)],
            capture_output=True, text=True,
        )
        if res.returncode != 0:
            raise ComicError(
                _("7z konnte {name} nicht entpacken:\n{error}").format(
                    name=self.path.name, error=res.stderr.strip()))


class TarComic(ExtractedComic):
    def _extract(self, dest: Path) -> None:
        with tarfile.open(self.path) as tf:
            tf.extractall(dest)


# ---------------------------------------------------------------------------
# PDF
# ---------------------------------------------------------------------------
class PdfComic(ComicFile):
    """PDF via PyMuPDF. Metadaten liegen in einem ComicInfo.xml-Sidecar."""

    RENDER_DPI = 160

    def __init__(self, path: Path):
        super().__init__(path)
        import fitz

        self._doc = fitz.open(str(self.path))

    @property
    def sidecar(self) -> Path:
        return self.path.with_suffix(self.path.suffix + ".ComicInfo.xml")

    @property
    def page_count(self) -> int:
        return self._doc.page_count

    def page_bytes(self, index: int) -> bytes:
        import fitz

        page = self._doc.load_page(index)
        zoom = self.RENDER_DPI / 72.0
        pix = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom), alpha=False)
        return pix.tobytes("png")

    def _read_cix(self) -> str | None:
        if self.sidecar.exists():
            return self.sidecar.read_text("utf-8", "replace")
        return None

    @property
    def writable(self) -> bool:
        return os.access(self.path.parent, os.W_OK)

    def write_metadata(self, md: GenericMetadata) -> None:
        md.set_default_page_list(self.page_count)
        md.page_count = self.page_count
        self.sidecar.write_text(metadata_to_xml(md), "utf-8")

    @property
    def can_edit_pages(self) -> bool:
        return os.access(self.path, os.W_OK)

    def save_page_order(self, order: list[int]) -> None:
        if not order:
            raise ComicError(_("Ein Comic braucht mindestens eine Seite."))
        import fitz

        tmp = _temp_beside(self.path, ".pdf")
        try:
            self._doc.select(order)
            self._doc.save(str(tmp), garbage=3, deflate=True)
            self._doc.close()
            shutil.copystat(self.path, tmp)
            os.replace(tmp, self.path)
        except Exception:
            tmp.unlink(missing_ok=True)
            raise
        finally:
            self._doc = fitz.open(str(self.path))

    def close(self) -> None:
        self._doc.close()


# ---------------------------------------------------------------------------
def open_comic(path: Path) -> ComicFile:
    path = Path(path)
    ext = path.suffix.lower()
    if ext == ".pdf":
        return PdfComic(path)
    if ext == ".cbt":
        return TarComic(path)
    if ext in (".cbz", ".zip"):
        if zipfile.is_zipfile(path):
            return ZipComic(path)
        return SevenZipComic(path)
    if ext in (".cbr", ".cb7"):
        # Viele "CBR" sind in Wahrheit ZIPs.
        if zipfile.is_zipfile(path):
            return ZipComic(path)
        return SevenZipComic(path)
    raise ComicError(
        _("Nicht unterstuetztes Format: {suffix}").format(suffix=path.suffix))


def first_comic_in(folder: Path, max_depth: int = 2) -> Path | None:
    """Erstes Comic in einem Ordner - fuer die Ordnervorschau.

    Steigt begrenzt in Unterordner ab, weil Sammlungen oft
    Serie/Staffel/Heft.cbz verschachtelt sind. Bricht beim ersten Treffer ab,
    damit das auch auf Netzlaufwerken bezahlbar bleibt.
    """
    try:
        entries = sorted(folder.iterdir(), key=lambda p: natural_key(p.name))
    except OSError:
        return None
    for entry in entries:
        if entry.is_file() and is_comic(entry):
            return entry
    if max_depth <= 1:
        return None
    for entry in entries:
        if entry.is_dir() and not entry.name.startswith("."):
            found = first_comic_in(entry, max_depth - 1)
            if found is not None:
                return found
    return None


def cover_bytes(path: Path) -> bytes | None:
    """Erste Seite als Bild-Bytes - fuer Thumbnails."""
    if path.is_dir():
        inner = first_comic_in(path)
        if inner is None:
            return None
        path = inner
    comic = None
    try:
        comic = open_comic(path)
        if comic.page_count == 0:
            return None
        return comic.page_bytes(0)
    except Exception:
        return None
    finally:
        if comic is not None:
            comic.close()


def convert_to_cbz(path: Path, dest: Path | None = None) -> Path:
    """Wandelt ein beliebiges Comic-Archiv in ein CBZ um (Original bleibt)."""
    src = open_comic(path)
    dest = dest or path.with_suffix(".cbz")
    if dest.exists():
        raise ComicError(_("{name} existiert bereits.").format(name=dest.name))
    try:
        cix = src._read_cix()
        with zipfile.ZipFile(dest, "w", zipfile.ZIP_DEFLATED) as zf:
            for i in range(src.page_count):
                data = src.page_bytes(i)
                ext = ".png" if isinstance(src, PdfComic) else _guess_ext(data)
                zf.writestr(f"{i + 1:04d}{ext}", data)
            if cix:
                zf.writestr(CIX_NAME, cix)
    except Exception:
        dest.unlink(missing_ok=True)
        raise
    finally:
        src.close()
    return dest


def _guess_ext(data: bytes) -> str:
    if data[:3] == b"\xff\xd8\xff":
        return ".jpg"
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return ".png"
    if data[:6] in (b"GIF87a", b"GIF89a"):
        return ".gif"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return ".webp"
    return ".jpg"
