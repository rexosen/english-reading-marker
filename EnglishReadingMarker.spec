# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    ['D:/ChatGPT迁移/工作区产出/Documents-Codex/Project_04_英语阅读标记器/src/main.py'],
    pathex=[],
    binaries=[],
    datas=[('D:/ChatGPT迁移/工作区产出/Documents-Codex/Project_04_英语阅读标记器/assets/Online_Classes_原文.txt', 'assets'), ('D:/ChatGPT迁移/工作区产出/Documents-Codex/Project_04_英语阅读标记器/assets/dictionary.sqlite3', 'assets'), ('D:/ChatGPT迁移/工作区产出/Documents-Codex/Project_04_英语阅读标记器/assets/ECDICT-LICENSE.txt', 'assets')],
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
