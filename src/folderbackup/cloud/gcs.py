"""Google Cloud Storage destination."""

from __future__ import annotations

import tempfile
import uuid
from pathlib import Path

from folderbackup.cloud.base import (
    ConnectionTestResult,
    FatalCloudError,
    RetryableCloudError,
    UploadResult,
)
from folderbackup.cloud.retry import retry_call
from folderbackup.config.secrets import Secrets
from folderbackup.config.settings import CloudSettings
from folderbackup.core.keys import normalize_prefix
from folderbackup.core.scanner import win_long_path


def _classify(exc: Exception) -> Exception:
    status = getattr(exc, "code", None) or getattr(exc, "status_code", None)
    if status in (400, 401, 403, 404):
        return FatalCloudError(str(exc))
    if status in (429, 500, 502, 503, 504):
        return RetryableCloudError(str(exc))
    return RetryableCloudError(str(exc))


class GCSBackend:
    def __init__(self, settings: CloudSettings, secrets: Secrets, *, multipart_threshold: int = 8 * 1024 * 1024):
        from google.cloud import storage

        self.bucket_name = settings.bucket.strip()
        self.prefix = normalize_prefix(settings.prefix)
        creds = settings.gcs_credentials_path.strip()
        if creds:
            self.client = storage.Client.from_service_account_json(creds)
        else:
            self.client = storage.Client()
        self.bucket = self.client.bucket(self.bucket_name)
        self._threshold = multipart_threshold
        _ = secrets  # GCS uses ADC or JSON path, not keyring

    def list_prefix(self, max_keys: int = 1) -> list[str]:
        def _list():
            try:
                blobs = self.client.list_blobs(self.bucket_name, prefix=self.prefix, max_results=max_keys)
                return [b.name for b in blobs]
            except Exception as exc:
                raise _classify(exc) from exc

        return retry_call(_list)

    def upload_file(self, local_path: str, key: str, size: int) -> UploadResult:
        src = win_long_path(local_path)

        def _put():
            try:
                blob = self.bucket.blob(key)
                blob.upload_from_filename(src, timeout=300)
                return UploadResult(
                    key=key,
                    etag=getattr(blob, "etag", None) or getattr(blob, "generation", None),
                    bytes_sent=size,
                )
            except Exception as exc:
                raise _classify(exc) from exc

        return retry_call(_put)

    def test_connection(self) -> ConnectionTestResult:
        try:
            self.list_prefix(1)
        except Exception as exc:
            return ConnectionTestResult(False, f"Cannot list bucket: {exc}", True)

        probe_name = f".folderbackup-probe-{uuid.uuid4().hex}"
        key = "/".join(p for p in (self.prefix, probe_name) if p)
        try:
            with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False) as fh:
                fh.write("folderbackup-probe")
                tmp_path = fh.name
            blob = self.bucket.blob(key)
            try:
                blob.upload_from_filename(tmp_path)
            except Exception as exc:
                return ConnectionTestResult(False, f"Cannot upload probe: {exc}", True)
            try:
                blob.delete()
            except Exception as exc:
                return ConnectionTestResult(
                    True,
                    f"Read/write OK, but probe delete failed ({exc}). Backup can still run.",
                    False,
                )
            return ConnectionTestResult(True, f"GCS bucket '{self.bucket_name}' is reachable.", True)
        finally:
            try:
                Path(tmp_path).unlink(missing_ok=True)
            except Exception:
                pass
