# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller-Bauplan fuer Windows und macOS.

Aufruf aus dem Projektordner:

    pyinstaller packaging/comicdesk.spec --noconfirm

Zwei Dinge, die PyInstaller allein nicht findet:

* comicapi liest sein ComicInfo-Schema aus Dateien im Paket - ohne die
  Datenmitnahme faellt das Schreiben von Tags aus.
* 7z ist ein eigenes Programm, kein Modul. Liegt es in packaging/bin/,
  wandert es mit ins Paket; archive.sevenzip_binary() sucht es dort
  zuerst. Ohne 7z lassen sich CBR und CB7 nicht oeffnen.
"""
import sys
from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files, collect_submodules

HIER = Path(SPECPATH).resolve()
WURZEL = HIER.parent

datas = [(str(WURZEL / "comicdesk" / "assets"), "comicdesk/assets")]
datas += collect_data_files("comicapi")
datas += collect_data_files("comictaggerlib", includes=["**/*.png", "**/*.ui"])

# 7z mitnehmen, falls vorhanden. Der Workflow legt es dorthin.
for binary in sorted((HIER / "bin").glob("*")) if (HIER / "bin").is_dir() else []:
    if binary.is_file():
        datas.append((str(binary), "bin"))

hiddenimports = [
    "PIL._avif",              # AVIF steckt in einer Erweiterung, nicht im Code
    "pillow_jxl",             # nur ueber den Namen importiert
]
hiddenimports += collect_submodules("comicapi")
hiddenimports += collect_submodules("comicdesk")

block_cipher = None

a = Analysis(
    [str(HIER / "entry.py")],
    pathex=[str(WURZEL)],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    runtime_hooks=[],
    # Qt bringt viel mit, was ein Comic-Verwalter nie braucht. Das spart
    # rund 100 MB im fertigen Paket.
    excludes=[
        "PySide6.QtQml", "PySide6.QtQuick", "PySide6.QtQuick3D",
        "PySide6.QtWebEngineCore", "PySide6.QtWebEngineWidgets",
        "PySide6.Qt3DCore", "PySide6.QtCharts", "PySide6.QtDataVisualization",
        "PySide6.QtMultimedia", "PySide6.QtBluetooth", "PySide6.QtSensors",
        "PySide6.QtDesigner", "PySide6.QtTest",
        "tkinter", "unittest", "pydoc_data",
    ],
    noarchive=False,
    cipher=block_cipher,
)
pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="ComicDesk",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,           # kein Konsolenfenster beim Start
    icon=str(HIER / "comicdesk.ico") if sys.platform == "win32" else None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name="ComicDesk",
)

if sys.platform == "darwin":
    app = BUNDLE(
        coll,
        name="ComicDesk.app",
        icon=str(HIER / "comicdesk.icns"),
        bundle_identifier="de.comicdesk.ComicDesk",
        info_plist={
            "CFBundleName": "ComicDesk",
            "CFBundleDisplayName": "ComicDesk",
            "NSHighResolutionCapable": True,
            # Ohne das startet die App auf Deutsch nur zufaellig richtig.
            "CFBundleDevelopmentRegion": "de",
            "CFBundleDocumentTypes": [{
                "CFBundleTypeName": "Comic-Archiv",
                "CFBundleTypeRole": "Viewer",
                "LSItemContentTypes": ["public.archive"],
                "CFBundleTypeExtensions": ["cbz", "cbr", "cb7", "cbt", "pdf"],
            }],
        },
    )
