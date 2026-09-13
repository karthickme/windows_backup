"""File selection rules: extensions, size, hidden/system, exclude directories."""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from pathlib import Path

from folderbackup.config.settings import FilterSettings

BUILTIN_EXCLUDE_DIRS = frozenset(
    {
        ".git",
        "node_modules",
        "__pycache__",
        ".venv",
        "venv",
        "$Recycle.Bin",
        "System Volume Information",
    }
)

BUILTIN_EXCLUDE_FILES = frozenset({"Thumbs.db", "desktop.ini"})

FILE_ATTRIBUTE_READONLY = 0x1
FILE_ATTRIBUTE_HIDDEN = 0x2
FILE_ATTRIBUTE_SYSTEM = 0x4
FILE_ATTRIBUTE_DIRECTORY = 0x10
FILE_ATTRIBUTE_REPARSE_POINT = 0x400
FILE_ATTRIBUTE_RECALL_ON_OPEN = 0x00040000
FILE_ATTRIBUTE_RECALL_ON_DATA_ACCESS = 0x00400000

MB = 1024 * 1024


@dataclass(frozen=True)
class FilterDecision:
    include: bool
    reason: str


def normalize_ext(ext: str) -> str:
    ext = ext.strip().lower()
    if not ext:
        return ""
    if not ext.startswith("."):
        ext = "." + ext
    return ext


def parse_ext_list(value: str | list[str] | None) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        parts = [p for p in value.replace(";", ",").split(",")]
        return [normalize_ext(p) for p in parts if p.strip()]
    return [normalize_ext(p) for p in value if str(p).strip()]


def should_skip_dir_name(name: str, settings: FilterSettings) -> bool:
    if settings.use_builtin_excludes and name in BUILTIN_EXCLUDE_DIRS:
        return True
    extras = {n.strip() for n in settings.extra_exclude_dirs if n.strip()}
    return name in extras


def file_attributes(path: Path) -> int:
    if sys.platform != "win32":
        return 0
    try:
        st = os.lstat(path)
        return int(getattr(st, "st_file_attributes", 0) or 0)
    except OSError:
        return 0


def is_hidden_or_system(path: Path, attrs: int | None = None) -> tuple[bool, bool]:
    if sys.platform != "win32":
        hidden = path.name.startswith(".")
        return hidden, False
    attrs = file_attributes(path) if attrs is None else attrs
    return bool(attrs & FILE_ATTRIBUTE_HIDDEN), bool(attrs & FILE_ATTRIBUTE_SYSTEM)


def is_reparse_point(path: Path, attrs: int | None = None) -> bool:
    attrs = file_attributes(path) if attrs is None else attrs
    return bool(attrs & FILE_ATTRIBUTE_REPARSE_POINT)


def is_online_only(path: Path, attrs: int | None = None) -> bool:
    attrs = file_attributes(path) if attrs is None else attrs
    recall = FILE_ATTRIBUTE_RECALL_ON_DATA_ACCESS | FILE_ATTRIBUTE_RECALL_ON_OPEN
    return bool(attrs & recall)


def is_sharing_violation(exc: BaseException) -> bool:
    winerror = getattr(exc, "winerror", None)
    if winerror == 32:
        return True
    if isinstance(exc, PermissionError):
        return True
    return False


def apply_file_filters(
    path: Path,
    *,
    size: int,
    settings: FilterSettings,
    attrs: int | None = None,
) -> FilterDecision:
    name = path.name
    if settings.use_builtin_excludes and name in BUILTIN_EXCLUDE_FILES:
        return FilterDecision(False, "builtin-exclude-file")

    hidden, system = is_hidden_or_system(path, attrs)
    if settings.skip_hidden and hidden:
        return FilterDecision(False, "hidden")
    if settings.skip_system and system:
        return FilterDecision(False, "system")

    if settings.skip_online_only and is_online_only(path, attrs):
        return FilterDecision(False, "online-only")

    ext = path.suffix.lower()
    include = parse_ext_list(settings.include_extensions)
    exclude = parse_ext_list(settings.exclude_extensions)
    if exclude and ext in exclude:
        return FilterDecision(False, "exclude-extension")
    if include and ext not in include:
        return FilterDecision(False, "not-included-extension")

    min_bytes = int(settings.min_size_mb * MB) if settings.min_size_mb is not None else None
    max_bytes = int(settings.max_size_mb * MB) if settings.max_size_mb is not None else None
    if min_bytes is not None and size < min_bytes:
        return FilterDecision(False, "below-min-size")
    if max_bytes is not None and size > max_bytes:
        return FilterDecision(False, "above-max-size")

    return FilterDecision(True, "ok")
