"""Local filesystem backend for tests and offline dry development."""

from __future__ import annotations

import shutil
from pathlib import Path

from folderbackup.cloud.base import ConnectionTestResult, UploadResult
from folderbackup.core.scanner import win_long_path


class LocalFilesystemBackend:
    def __init__(self, root: str | Path):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    def test_connection(self) -> ConnectionTestResult:
        probe = self.root / ".folderbackup-probe"
        try:
            probe.write_text("ok", encoding="utf-8")
            probe.unlink()
            return ConnectionTestResult(True, f"Local backend writable: {self.root}", True)
        except OSError as exc:
            return ConnectionTestResult(False, str(exc), False)

    def upload_file(self, local_path: str, key: str, size: int) -> UploadResult:
        dest = self.root.joinpath(*key.split("/"))
        dest.parent.mkdir(parents=True, exist_ok=True)
        src = win_long_path(local_path)
        shutil.copyfile(src, dest)
        return UploadResult(key=key, etag=str(dest.stat().st_mtime_ns), bytes_sent=size)

    def list_prefix(self, max_keys: int = 1) -> list[str]:
        files = [p for p in self.root.rglob("*") if p.is_file()]
        rel = [str(p.relative_to(self.root)).replace("\\", "/") for p in files[:max_keys]]
        return rel
