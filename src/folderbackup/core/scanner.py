"""Walk source folders and yield backup jobs after filters."""

from __future__ import annotations

import os
import sys
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

from folderbackup.config.settings import AppSettings
from folderbackup.core.filters import (
    FILE_ATTRIBUTE_DIRECTORY,
    FILE_ATTRIBUTE_REPARSE_POINT,
    apply_file_filters,
    file_attributes,
    is_reparse_point,
    should_skip_dir_name,
)
from folderbackup.core.keys import local_path_to_key

LONG_PATH_LIMIT = 260


@dataclass(frozen=True)
class FileJob:
    local_path: str
    size: int
    mtime_ns: int
    remote_key: str


def win_long_path(path: str | Path) -> str:
    p = os.path.abspath(str(path))
    if sys.platform != "win32":
        return p
    if p.startswith("\\\\?\\"):
        return p
    if p.startswith("\\\\"):
        return "\\\\?\\UNC\\" + p[2:]
    return "\\\\?\\" + p


def display_path(path: str) -> str:
    for prefix in ("\\\\?\\UNC\\", "//?/UNC/"):
        if path.startswith(prefix):
            return "\\\\" + path[len(prefix) :]
    for prefix in ("\\\\?\\", "//?/"):
        if path.startswith(prefix):
            return path[len(prefix) :]
    return path


def _dir_is_junction(path: Path) -> bool:
    if not is_reparse_point(path):
        return False
    attrs = file_attributes(path)
    return bool(attrs & FILE_ATTRIBUTE_DIRECTORY) or path.is_dir()


def iter_source_files(settings: AppSettings) -> Iterator[FileJob]:
    prefix = settings.cloud.prefix
    follow = settings.filters.follow_junctions
    for folder in settings.folders:
        root = Path(folder)
        if not root.exists():
            continue
        yield from _walk(root, settings, prefix, follow)


def _walk(root: Path, settings: AppSettings, prefix: str, follow_junctions: bool) -> Iterator[FileJob]:
    try:
        scanner = os.scandir(win_long_path(root) if sys.platform == "win32" else root)
    except OSError:
        return

    with scanner as entries:
        for entry in entries:
            try:
                name = entry.name
                path = Path(display_path(entry.path))
                if entry.is_dir(follow_symlinks=False):
                    if should_skip_dir_name(name, settings.filters):
                        continue
                    if not follow_junctions:
                        try:
                            if entry.is_symlink() or _dir_is_junction(path):
                                continue
                        except OSError:
                            continue
                    yield from _walk(path, settings, prefix, follow_junctions)
                    continue

                if not entry.is_file(follow_symlinks=False):
                    continue

                try:
                    st = entry.stat(follow_symlinks=False)
                except OSError:
                    continue

                size = int(st.st_size)
                mtime_ns = _mtime_ns(st)
                attrs = file_attributes(path)
                if attrs & FILE_ATTRIBUTE_REPARSE_POINT and not follow_junctions:
                    # Skip symlink files unless following reparse points
                    if entry.is_symlink():
                        continue

                decision = apply_file_filters(path, size=size, settings=settings.filters, attrs=attrs)
                if not decision.include:
                    continue

                local = str(path)
                if sys.platform == "win32" and len(local) >= LONG_PATH_LIMIT:
                    local = display_path(win_long_path(local))

                yield FileJob(
                    local_path=str(Path(local)),
                    size=size,
                    mtime_ns=mtime_ns,
                    remote_key=local_path_to_key(local, prefix),
                )
            except OSError:
                continue


def _mtime_ns(st: os.stat_result) -> int:
    ns = getattr(st, "st_mtime_ns", None)
    if ns is not None:
        return int(ns)
    return int(st.st_mtime * 1_000_000_000)
