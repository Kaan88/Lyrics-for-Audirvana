# -*- mode: python ; coding: utf-8 -*-
# Build with:  pyinstaller lyrics.spec

import sys
from PyInstaller.utils.hooks import collect_data_files

# CustomTkinter ships JSON theme files that must be bundled explicitly.
ctk_datas = collect_data_files("customtkinter", include_py_files=False)

a = Analysis(
    ["lyrics.pyw"],
    pathex=[],
    binaries=[],
    datas=[
        ("icon.ico", "."),
        *ctk_datas,
    ],
    hiddenimports=[
        # pylast / Last.fm
        "pylast",
        # lyricsgenius uses bs4 at runtime
        "bs4",
        # requests / TLS stack
        "requests",
        "certifi",
        "charset_normalizer",
        "idna",
        "urllib3",
        # Windows UI Automation (Audirvāna position reading)
        "uiautomation",
        # Pillow — used for artist/album thumbnails and hover previews
        "PIL",
        "PIL.Image",
        "PIL.ImageTk",
        "PIL.ImageDraw",
    ],
    excludes=[
        # GUI toolkits we don't use
        "PyQt5", "PyQt6", "PySide2", "PySide6",
        "wx", "gi", "gtk",
        # Scientific stack — not used, but sometimes dragged in
        "matplotlib", "numpy", "pandas", "scipy",
        # Dev / notebook tools
        "IPython", "jupyter", "notebook",
        "setuptools", "pkg_resources",
        # Stdlib modules we never touch
        "unittest", "doctest", "pdb", "lib2to3",
        "ftplib", "imaplib", "smtplib", "poplib", "nntplib",
        "telnetlib", "xmlrpc", "multiprocessing",
        "sqlite3", "curses", "cProfile",
        "tkinter.test",
    ],
    noarchive=False,
    optimize=2,   # strips docstrings + assert statements (~5 % size reduction)
)

pyz = PYZ(a.pure, a.zipped_data)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="Lyrics",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,   # True only on Linux/Mac — breaks on Windows
    upx=True,      # requires UPX on PATH; safe to leave True, ignored if absent
    upx_exclude=[
        # UPX can corrupt these — exclude them
        "vcruntime140.dll",
        "python3*.dll",
        "_tkinter*.pyd",
    ],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    icon="icon.ico",
)
