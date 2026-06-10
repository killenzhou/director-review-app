# -*- mode: python ; coding: utf-8 -*-

from PyInstaller.utils.hooks import collect_dynamic_libs, collect_submodules


binaries = []
binaries += collect_dynamic_libs("torch")
binaries += collect_dynamic_libs("torchaudio")

hiddenimports = [
    "torch",
    "torchaudio",
    "funasr",
    "modelscope",
    "addict",
    "yaml",
    "jieba",
    "sounddevice",
    "mss",
    "pytesseract",
    "PIL",
    "openpyxl",
    "websockets",
    "openai",
    "google.generativeai",
]
hiddenimports += collect_submodules("funasr")
hiddenimports += collect_submodules("modelscope")


a = Analysis(
    ["main_app.py"],
    pathex=[],
    binaries=binaries,
    datas=[
        ("external_files/ffmpeg.exe", "external_files"),
        ("Tesseract-OCR", "Tesseract-OCR"),
        ("style.qss", "."),
        ("style_dark.qss", "."),
        ("help_content.py", "."),
        ("web_viewer", "web_viewer"),
    ],
    hiddenimports=hiddenimports,
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
    [],
    [],
    name="协同审阅平台",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    runtime_tmpdir=None,
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
    upx=False,
    upx_exclude=[],
    name="协同审阅平台",
)
