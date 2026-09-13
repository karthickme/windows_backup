"""Storage backend protocol shared by S3, GCS, Azure, and the test fake."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


class RetryableCloudError(Exception):
    """Transient cloud failure (429/5xx/timeout) that should be retried."""


class FatalCloudError(Exception):
    """Permanent failure such as 403 or missing bucket."""


@dataclass(frozen=True)
class UploadResult:
    key: str
    etag: str | None = None
    bytes_sent: int = 0


@dataclass(frozen=True)
class ConnectionTestResult:
    ok: bool
    message: str
    probe_deleted: bool = True


class StorageBackend(Protocol):
    def test_connection(self) -> ConnectionTestResult: ...

    def upload_file(self, local_path: str, key: str, size: int) -> UploadResult: ...

    def list_prefix(self, max_keys: int = 1) -> list[str]: ...
