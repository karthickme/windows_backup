"""Generate PyInstaller VERSIONINFO and folderbackup._version for a Windows build."""

from __future__ import annotations

import argparse
from pathlib import Path


def _four_tuple(value: str) -> tuple[int, int, int, int]:
    digits: list[int] = []
    for part in value.replace("-", ".").replace("+", ".").split("."):
        if part.isdigit():
            digits.append(int(part))
        if len(digits) == 4:
            break
    while len(digits) < 4:
        digits.append(0)
    return digits[0], digits[1], digits[2], digits[3]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--semver", required=True)
    parser.add_argument("--assembly-version", default="")
    parser.add_argument("--informational-version", default="")
    args = parser.parse_args()

    semver = args.semver.strip() or "0.1.0"
    assembly = args.assembly_version.strip() or semver
    informational = args.informational_version.strip() or semver
    major, minor, patch, build = _four_tuple(assembly)

    version_info = f"""# UTF-8
VSVersionInfo(
  ffi=FixedFileInfo(
    filevers=({major}, {minor}, {patch}, {build}),
    prodvers=({major}, {minor}, {patch}, {build}),
    mask=0x3F,
    flags=0x0,
    OS=0x40004,
    fileType=0x1,
    subtype=0x0,
    date=(0, 0),
  ),
  kids=[
    StringFileInfo(
      [
        StringTable(
          '040904B0',
          [
            StringStruct('CompanyName', 'FolderBackup'),
            StringStruct('FileDescription', 'Folder Backup'),
            StringStruct('FileVersion', '{semver}'),
            StringStruct('InternalName', 'FolderBackup'),
            StringStruct('LegalCopyright', ''),
            StringStruct('OriginalFilename', 'FolderBackup.exe'),
            StringStruct('ProductName', 'Folder Backup'),
            StringStruct('ProductVersion', '{informational}'),
          ],
        )
      ]
    ),
    VarFileInfo([VarStruct('Translation', [1033, 1200])]),
  ],
)
"""
    version_file = args.root / "packaging" / "file_version_info.txt"
    version_file.parent.mkdir(parents=True, exist_ok=True)
    version_file.write_text(version_info, encoding="utf-8")

    version_py = args.root / "src" / "folderbackup" / "_version.py"
    version_py.write_text(
        f'"""Generated at pack time. Do not edit."""\n\n__version__ = {semver!r}\n__full_version__ = {informational!r}\n',
        encoding="utf-8",
    )
    print(f"Wrote {version_file}")
    print(f"Wrote {version_py}")


if __name__ == "__main__":
    main()
