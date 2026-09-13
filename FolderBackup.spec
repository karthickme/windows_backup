# -*- mode: python ; coding: utf-8 -*-
"""One-folder Windows build for Folder Backup (CustomTkinter + cloud SDKs)."""

from pathlib import Path

from PyInstaller.utils.hooks import collect_all, collect_data_files

spec_root = Path(SPECPATH).resolve()
src = spec_root / "src"
version_file = spec_root / "packaging" / "file_version_info.txt"

datas = collect_data_files("customtkinter")
binaries: list = []
hiddenimports = [
    "customtkinter",
    "PIL",
    "PIL._tkinter_finder",
    "pystray",
    "pystray._win32",
    "boto3",
    "botocore",
    "google",
    "google.auth",
    "google.cloud",
    "google.cloud.storage",
    "azure",
    "azure.storage",
    "azure.storage.blob",
    "keyring",
    "keyring.backends",
    "keyring.backends.Windows",
    "yaml",
    "apscheduler",
    "platformdirs",
    "folderbackup._version",
]

for pkg in ("customtkinter", "pystray", "keyring", "certifi"):
    pkg_datas, pkg_binaries, pkg_hidden = collect_all(pkg)
    datas += pkg_datas
    binaries += pkg_binaries
    hiddenimports += pkg_hidden

a = Analysis(
    [str(src / "folderbackup" / "__main__.py")],
    pathex=[str(src)],
    binaries=binaries,
    datas=datas,
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
    exclude_binaries=True,
    name="FolderBackup",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    version=str(version_file) if version_file.exists() else None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="FolderBackup",
)
