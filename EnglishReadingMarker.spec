# -*- mode: python ; coding: utf-8 -*-

import os

from PyInstaller.utils.hooks import copy_metadata

root = os.path.abspath(SPECPATH)
assets = os.path.join(root, "assets")

datas = [
    (os.path.join(assets, "Online_Classes_原文.txt"), "assets"),
    (os.path.join(assets, "ECDICT-LICENSE.txt"), "assets"),
]
dictionary = os.path.join(assets, "dictionary.sqlite3")
if os.path.exists(dictionary):
    datas.append((dictionary, "assets"))
datas += copy_metadata("edge-tts")

a = Analysis(
    [os.path.join(root, "src", "main.py")],
    pathex=[],
    binaries=[],
    datas=datas,
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='EnglishReadingMarker',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='EnglishReadingMarker',
)
