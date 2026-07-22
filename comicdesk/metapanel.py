"""Metadaten-Panel: ComicInfo.xml lesen und schreiben."""
from __future__ import annotations

from pathlib import Path

from comicapi.genericmetadata import GenericMetadata
from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QFormLayout, QGroupBox, QHBoxLayout, QLabel, QLineEdit, QMessageBox,
    QPlainTextEdit, QPushButton, QScrollArea, QVBoxLayout, QWidget,
)

from .archive import ComicError, ComicFile, open_comic
from .i18n import _
from . import provenance

CREDIT_ROLES = [
    ("Autor", "Writer"),
    ("Zeichner", "Penciller"),
    ("Tusche", "Inker"),
    ("Farben", "Colorist"),
    ("Lettering", "Letterer"),
    ("Cover", "CoverArtist"),
    ("Redaktion", "Editor"),
]

# (Attribut, Label, ist Zahl)
TEXT_FIELDS = [
    ("series", "Serie", False),
    ("issue", "Nummer", False),
    ("title", "Titel", False),
    ("volume", "Volume", True),
    ("issue_count", "Anzahl Hefte", True),
    ("year", "Jahr", True),
    ("month", "Monat", True),
    ("day", "Tag", True),
    ("publisher", "Verlag", False),
    ("imprint", "Imprint", False),
    ("genre", "Genre", False),
    ("language", "Sprache (ISO)", False),
    ("format", "Format", False),
    ("story_arc", "Story Arc", False),
    ("series_group", "Serien-Gruppe", False),
    ("maturity_rating", "Altersfreigabe", False),
    ("web_link", "Web-Link", False),
    ("scan_info", "Scan-Info", False),
]

LIST_FIELDS = [
    ("characters", "Charaktere"),
    ("teams", "Teams"),
    ("locations", "Orte"),
]


class MetaPanel(QWidget):
    """Rechte Seitenleiste zum Ansehen und Bearbeiten der Tags."""

    saved = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.path: Path | None = None
        self._md = GenericMetadata()
        self._edits: dict[str, QLineEdit] = {}
        self._credit_edits: dict[str, QLineEdit] = {}

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)

        self.header = QLabel(_("Keine Datei ausgewaehlt"))
        self.header.setWordWrap(True)
        self.header.setStyleSheet("font-weight:600; padding:6px;")
        root.addWidget(self.header)

        self.source_label = QLabel()
        self.source_label.setWordWrap(True)
        self.source_label.setStyleSheet("color:gray; padding:0 6px 6px 6px;")
        root.addWidget(self.source_label)

        area = QScrollArea()
        area.setWidgetResizable(True)
        inner = QWidget()
        area.setWidget(inner)
        v = QVBoxLayout(inner)
        root.addWidget(area, 1)

        box = QGroupBox(_("Heft"))
        form = QFormLayout(box)
        for attr, label, _num in TEXT_FIELDS:
            e = QLineEdit()
            self._edits[attr] = e
            form.addRow(_(label), e)
        v.addWidget(box)

        cbox = QGroupBox(_("Mitwirkende (mehrere mit Komma)"))
        cform = QFormLayout(cbox)
        for label, role in CREDIT_ROLES:
            e = QLineEdit()
            self._credit_edits[role] = e
            cform.addRow(_(label), e)
        v.addWidget(cbox)

        lbox = QGroupBox(_("Listen (Komma-getrennt)"))
        lform = QFormLayout(lbox)
        for attr, label in LIST_FIELDS:
            e = QLineEdit()
            self._edits[attr] = e
            lform.addRow(_(label), e)
        self.tags_edit = QLineEdit()
        lform.addRow(_("Tags"), self.tags_edit)
        v.addWidget(lbox)

        nbox = QGroupBox(_("Beschreibung"))
        nlay = QVBoxLayout(nbox)
        self.comments = QPlainTextEdit()
        self.comments.setMinimumHeight(120)
        nlay.addWidget(self.comments)
        v.addWidget(nbox)
        v.addStretch(1)

        btns = QHBoxLayout()
        self.btn_save = QPushButton(_("Tags speichern"))
        self.btn_save.setShortcut("Ctrl+S")
        self.btn_save.clicked.connect(self.save)
        self.btn_reload = QPushButton(_("Verwerfen"))
        self.btn_reload.clicked.connect(lambda: self.load(self.path))
        btns.addWidget(self.btn_save)
        btns.addWidget(self.btn_reload)
        root.addLayout(btns)

        self.hint = QLabel()
        self.hint.setWordWrap(True)
        self.hint.setStyleSheet("color:#c07000; padding:4px;")
        root.addWidget(self.hint)
        self.set_enabled(False)

    # ------------------------------------------------------------------
    def set_enabled(self, on: bool) -> None:
        for e in list(self._edits.values()) + list(self._credit_edits.values()):
            e.setEnabled(on)
        self.tags_edit.setEnabled(on)
        self.comments.setEnabled(on)
        self.btn_save.setEnabled(on)
        self.btn_reload.setEnabled(on)

    def clear(self) -> None:
        self.path = None
        self._md = GenericMetadata()
        self._fill(self._md)
        self.source_label.setText(provenance.describe(self._md))
        self.header.setText(_("Keine Datei ausgewaehlt"))
        self.source_label.clear()
        self.hint.clear()
        self.set_enabled(False)

    def load(self, path: Path | None) -> None:
        if path is None:
            self.clear()
            return
        self.path = Path(path)
        comic = None
        try:
            comic = open_comic(self.path)
            self._md = comic.read_metadata()
            writable = comic.writable
            pages = comic.page_count
        except Exception as exc:  # noqa: BLE001
            self.header.setText(self.path.name)
            self.hint.setText(
                _("Konnte nicht gelesen werden: {error}").format(error=exc))
            self._fill(GenericMetadata())
            self.set_enabled(False)
            return
        finally:
            if comic is not None:
                comic.close()

        self._fill(self._md)
        self.source_label.setText(provenance.describe(self._md))
        self.header.setText(
            _("{name}\n{pages} Seiten").format(name=self.path.name, pages=pages))
        self.set_enabled(True)
        if not writable:
            self.btn_save.setEnabled(False)
            self.hint.setText(_(
                "Schreiben in dieses Format ist nicht moeglich. "
                "Ueber „Nach CBZ konvertieren“ taggbar machen."
            ))
        elif isinstance(self.path.suffix, str) and self.path.suffix.lower() == ".pdf":
            self.hint.setText(
                _("PDF: Tags landen in einer ComicInfo.xml-Datei daneben."))
        else:
            self.hint.clear()

    # ------------------------------------------------------------------
    def _fill(self, md: GenericMetadata) -> None:
        for attr, _label, _num in TEXT_FIELDS:
            val = getattr(md, attr, None)
            self._edits[attr].setText("" if val is None else str(val))
        for attr, _label in LIST_FIELDS:
            val = getattr(md, attr, None)
            self._edits[attr].setText(val or "")
        self.tags_edit.setText(", ".join(sorted(md.tags or [])))
        self.comments.setPlainText(md.comments or "")
        by_role: dict[str, list[str]] = {}
        for c in md.credits or []:
            role = (c.get("role") or "").replace(" ", "").lower()
            by_role.setdefault(role, []).append(c.get("person") or "")
        for _label, role in CREDIT_ROLES:
            names = by_role.get(role.lower(), [])
            self._credit_edits[role].setText(", ".join(n for n in names if n))

    def _collect(self) -> GenericMetadata:
        md = GenericMetadata()
        # unbekannte Felder aus dem Original uebernehmen
        md.pages = self._md.pages
        md.notes = self._md.notes
        md.identifier = self._md.identifier
        md.black_and_white = self._md.black_and_white
        md.manga = self._md.manga

        for attr, _label, num in TEXT_FIELDS:
            txt = self._edits[attr].text().strip()
            if not txt:
                setattr(md, attr, None)
            elif num:
                try:
                    setattr(md, attr, int(txt))
                except ValueError:
                    setattr(md, attr, None)
            else:
                setattr(md, attr, txt)
        for attr, _label in LIST_FIELDS:
            txt = self._edits[attr].text().strip()
            setattr(md, attr, txt or None)
        tags = {t.strip() for t in self.tags_edit.text().split(",") if t.strip()}
        md.tags = tags
        md.comments = self.comments.toPlainText().strip() or None
        for _label, role in CREDIT_ROLES:
            for name in self._credit_edits[role].text().split(","):
                name = name.strip()
                if name:
                    md.add_credit(name, role)
        md.is_empty = False
        provenance.stamp_manual(md)
        return md

    def save(self) -> None:
        if not self.path:
            return
        comic: ComicFile | None = None
        try:
            comic = open_comic(self.path)
            comic.write_metadata(self._collect())
        except ComicError as exc:
            QMessageBox.warning(self, _("Tags speichern"), str(exc))
            return
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(self, _("Tags speichern"),
                                 _("Fehlgeschlagen:\n{error}").format(error=exc))
            return
        finally:
            if comic is not None:
                comic.close()
        self.saved.emit(str(self.path))
        self.load(self.path)

    # ------------------------------------------------------------------
    def current_metadata(self) -> GenericMetadata:
        return self._collect()
