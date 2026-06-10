# -*- mode: python ; coding: utf-8 -*-
# 协同审阅平台 完整版打包规格
# 与原 spec 区别: COLLECT.name = "协同审阅平台_完整版"，产物目录为 dist\协同审阅平台_完整版\
# 其余数据 (ffmpeg / Tesseract / 样式) 仍按原 spec 打包到 _internal\ 供主程序经 sys._MEIPASS 读取
# Qwen3-VL-8B / llama-cpp / FunASR-main / FunASR_models 这些大体量模型
# 不进入 _internal，而是在 build_all_in_one.bat 中拷贝到产物顶层目录，由主程序经
# resource_path(app_base_path) 定位。

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
    name="协同审阅平台_完整版",
)
