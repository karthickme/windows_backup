"""Azure Blob Storage destination."""

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
    status = getattr(exc, "status_code", None)
    if status is None:
        resp = getattr(exc, "response", None)
        status = getattr(resp, "status_code", None)
    if status in (400, 401, 403, 404):
        return FatalCloudError(str(exc))
    if status in (429, 500, 502, 503, 504):
        return RetryableCloudError(str(exc))
    return RetryableCloudError(str(exc))


class AzureBlobBackend:
    def __init__(self, settings: CloudSettings, secrets: Secrets, *, multipart_threshold: int = 8 * 1024 * 1024):
        from azure.storage.blob import BlobServiceClient, ContentSettings

        self.container = settings.bucket.strip()
        self.prefix = normalize_prefix(settings.prefix)
        self._threshold = multipart_threshold
        _ = ContentSettings
        if secrets.azure_connection_string.strip():
            self.service = BlobServiceClient.from_connection_string(secrets.azure_connection_string.strip())
        else:
            account = settings.azure_account_name.strip()
            key = secrets.azure_account_key.strip()
            if not account or not key:
                raise FatalCloudError("Azure requires a connection string or account name + key.")
            url = f"https://{account}.blob.core.windows.net"
            self.service = BlobServiceClient(account_url=url, credential=key)
        self.client = self.service.get_container_client(self.container)

    def list_prefix(self, max_keys: int = 1) -> list[str]:
        def _list():
            try:
                names = []
                prefix = self.prefix + ("/" if self.prefix else "")
                for blob in self.client.list_blobs(name_starts_with=prefix):
                    names.append(blob.name)
                    if len(names) >= max_keys:
                        break
                return names
            except Exception as exc:
                raise _classify(exc) from exc

        return retry_call(_list)

    def upload_file(self, local_path: str, key: str, size: int) -> UploadResult:
        src = win_long_path(local_path)
        blob = self.client.get_blob_client(key)

        def _put():
            try:
                with open(src, "rb") as fh:
                    result = blob.upload_blob(fh, overwrite=True, max_concurrency=4)
                etag = getattr(result, "etag", None) or getattr(result, "version_id", None)
                return UploadResult(key=key, etag=etag, bytes_sent=size)
            except Exception as exc:
                raise _classify(exc) from exc

        return retry_call(_put)

    def test_connection(self) -> ConnectionTestResult:
        try:
            self.list_prefix(1)
        except Exception as exc:
            return ConnectionTestResult(False, f"Cannot list container: {exc}", True)

        probe_name = f".folderbackup-probe-{uuid.uuid4().hex}"
        key = "/".join(p for p in (self.prefix, probe_name) if p)
        try:
            with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False) as fh:
                fh.write("folderbackup-probe")
                tmp_path = fh.name
            blob = self.client.get_blob_client(key)
            try:
                with open(tmp_path, "rb") as fh:
                    blob.upload_blob(fh, overwrite=True)
            except Exception as exc:
                return ConnectionTestResult(False, f"Cannot upload probe: {exc}", True)
            try:
                blob.delete_blob()
            except Exception as exc:
                return ConnectionTestResult(
                    True,
                    f"Read/write OK, but probe delete failed ({exc}). Backup can still run.",
                    False,
                )
            return ConnectionTestResult(True, f"Azure container '{self.container}' is reachable.", True)
        finally:
            try:
                Path(tmp_path).unlink(missing_ok=True)
            except Exception:
                pass
