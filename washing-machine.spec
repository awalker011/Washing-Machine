# -*- mode: python ; coding: utf-8 -*-
from pathlib import Path

project_root = Path.cwd()


datas = [
    (str(project_root / "schemas"), "schemas"),
    (str(project_root / "mappings"), "mappings"),
    (str(project_root / "README.md"), "."),
]

hiddenimports = [
    "openpyxl",
    "yaml",
    "tkinter",
    "tkinter.filedialog",
    "tkinter.messagebox",
    "tkinter.scrolledtext",
    "tkinter.simpledialog",
    "tkinter.ttk",
]


a = Analysis(
    ["washing_machine.py"],
    pathex=[str(project_root), str(project_root / "src")],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="WashingMachine",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
)
