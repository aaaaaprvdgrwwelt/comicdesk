"""Einheitliches Erscheinungsbild.

Bewusst zurueckhaltend: Farben und Schrift kommen weiterhin vom System, damit
ComicDesk sich in helle wie dunkle Themes einfuegt. Ergaenzt werden nur Abstaende,
Rundungen und eine Akzentfarbe - alles aus der Palette abgeleitet, nichts fest
verdrahtet.
"""
from __future__ import annotations

from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import QApplication


def is_dark(palette: QPalette) -> bool:
    return palette.color(QPalette.Window).lightness() < 128


def _mix(base: QColor, other: QColor, amount: float) -> QColor:
    """`amount` = 0 gibt `base`, 1 gibt `other`."""
    return QColor(
        round(base.red() + (other.red() - base.red()) * amount),
        round(base.green() + (other.green() - base.green()) * amount),
        round(base.blue() + (other.blue() - base.blue()) * amount),
    )


def build_stylesheet(palette: QPalette) -> str:
    dark = is_dark(palette)
    window = palette.color(QPalette.Window)
    text = palette.color(QPalette.WindowText)
    base = palette.color(QPalette.Base)
    accent = palette.color(QPalette.Highlight)
    contrast = QColor("white") if dark else QColor("black")

    # Abgestufte Flaechen, aus der Systemfarbe abgeleitet.
    raised = _mix(window, contrast, 0.05 if dark else 0.02)
    border = _mix(window, contrast, 0.16 if dark else 0.14)
    subtle = _mix(text, window, 0.45)
    field = _mix(base, contrast, 0.03 if dark else 0.0)

    ok_bg = _mix(window, QColor(46, 160, 90), 0.22)
    warn_bg = _mix(window, QColor(214, 154, 40), 0.22)

    return f"""
    QToolBar {{
        border: none;
        padding: 4px 6px;
        spacing: 2px;
        background: {raised.name()};
        border-bottom: 1px solid {border.name()};
    }}
    QToolButton {{ border: none; border-radius: 6px; padding: 5px 8px; }}
    QToolButton:hover {{ background: {_mix(raised, contrast, 0.08).name()}; }}
    QToolButton:pressed, QToolButton:checked {{
        background: {_mix(raised, accent, 0.35).name()};
    }}

    QMenuBar {{ background: {raised.name()}; padding: 2px 4px; }}
    QMenuBar::item {{ padding: 5px 10px; border-radius: 5px; background: transparent; }}
    QMenuBar::item:selected {{ background: {_mix(raised, accent, 0.30).name()}; }}
    QMenu {{
        background: {raised.name()};
        border: 1px solid {border.name()};
        border-radius: 8px;
        padding: 5px;
    }}
    QMenu::item {{ padding: 6px 22px 6px 12px; border-radius: 5px; }}
    QMenu::item:selected {{ background: {_mix(raised, accent, 0.35).name()}; }}
    QMenu::separator {{ height: 1px; background: {border.name()}; margin: 5px 8px; }}

    QLineEdit, QComboBox, QPlainTextEdit, QAbstractSpinBox {{
        background: {field.name()};
        border: 1px solid {border.name()};
        border-radius: 6px;
        padding: 5px 8px;
        selection-background-color: {accent.name()};
    }}
    QLineEdit:focus, QComboBox:focus, QPlainTextEdit:focus {{
        border: 1px solid {accent.name()};
    }}
    QLineEdit:disabled, QComboBox:disabled, QPlainTextEdit:disabled {{
        color: {subtle.name()};
        background: {_mix(field, window, 0.6).name()};
    }}

    QPushButton {{
        background: {raised.name()};
        border: 1px solid {border.name()};
        border-radius: 6px;
        padding: 6px 14px;
    }}
    QPushButton:hover {{ background: {_mix(raised, contrast, 0.07).name()}; }}
    QPushButton:pressed {{ background: {_mix(raised, accent, 0.28).name()}; }}
    QPushButton:default {{ border: 1px solid {accent.name()}; }}
    QPushButton:disabled {{ color: {subtle.name()}; border-color: {_mix(border, window, 0.5).name()}; }}

    QGroupBox {{
        border: 1px solid {border.name()};
        border-radius: 8px;
        margin-top: 12px;
        padding: 10px 8px 8px 8px;
    }}
    QGroupBox::title {{
        subcontrol-origin: margin;
        left: 10px;
        padding: 0 5px;
        color: {subtle.name()};
    }}

    QTreeView, QListView, QListWidget, QTableWidget {{
        background: {base.name()};
        border: 1px solid {border.name()};
        border-radius: 8px;
        outline: none;
    }}
    /* Wer ::item umstylt, muss die Auswahl selbst zeichnen - sonst bleibt
       nur die weisse Auswahlschrift uebrig und steht auf weissem Grund. */
    QListWidget::item {{ padding: 4px 6px; border-radius: 5px; }}
    QListWidget::item:hover {{ background: {_mix(base, contrast, 0.06).name()}; }}
    QListWidget::item:selected {{
        background: {accent.name()};
        color: {palette.color(QPalette.HighlightedText).name()};
    }}
    QListWidget::item:selected:!active {{
        background: {_mix(base, accent, 0.45).name()};
        color: {text.name()};
    }}

    QHeaderView::section {{
        background: {raised.name()};
        border: none;
        border-bottom: 1px solid {border.name()};
        padding: 6px 8px;
    }}

    QProgressBar {{
        border: none;
        border-radius: 6px;
        background: {_mix(window, contrast, 0.10).name()};
        height: 14px;
        text-align: center;
        color: {text.name()};
    }}
    QProgressBar::chunk {{ border-radius: 6px; background: {accent.name()}; }}

    QTabBar::tab {{
        padding: 7px 16px;
        border: none;
        border-radius: 6px;
        margin-right: 3px;
        color: {subtle.name()};
    }}
    QTabBar::tab:selected {{ background: {raised.name()}; color: {text.name()}; }}
    QTabWidget::pane {{ border: 1px solid {border.name()}; border-radius: 8px; top: -1px; }}

    QSplitter::handle {{ background: transparent; }}
    QStatusBar {{ border-top: 1px solid {border.name()}; }}
    QStatusBar::item {{ border: none; }}

    QLabel#resultBanner {{
        border-radius: 8px;
        padding: 10px 14px;
        font-weight: 600;
        background: {_mix(window, contrast, 0.06).name()};
    }}
    QLabel#resultBanner[state="ok"] {{ background: {ok_bg.name()}; }}
    QLabel#resultBanner[state="warn"] {{ background: {warn_bg.name()}; }}

    QScrollBar:vertical {{ background: transparent; width: 12px; margin: 2px; }}
    QScrollBar:horizontal {{ background: transparent; height: 12px; margin: 2px; }}
    QScrollBar::handle {{
        background: {_mix(window, contrast, 0.22).name()};
        border-radius: 5px;
        min-height: 28px;
        min-width: 28px;
    }}
    QScrollBar::handle:hover {{ background: {_mix(window, contrast, 0.34).name()}; }}
    QScrollBar::add-line, QScrollBar::sub-line {{ height: 0; width: 0; }}
    QScrollBar::add-page, QScrollBar::sub-page {{ background: transparent; }}
    """


def apply(app: QApplication) -> None:
    app.setStyleSheet(build_stylesheet(app.palette()))
