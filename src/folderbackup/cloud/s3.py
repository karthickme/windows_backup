"""Amazon S3 and S3-compatible destinations."""

from __future__ import annotations

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
    name = type(exc).__name__
    code = getattr(exc, "response", None)
    status = None
    if isinstance(code, dict):
        status = code.get("ResponseMetadata", {}).get("HTTPStatusCode")
        err = code.get("Error", {})
        if isinstance(err, dict) and err.get("Code") in {"AccessDenied", "403", "NoSuchBucket"}:
            return FatalCloudError(str(exc))
    if status in (400, 401, 403, 404):
        return FatalCloudError(str(exc))
    if status in (429, 500, 502, 503, 504) or name in {"EndpointConnectionError", "ConnectTimeoutError"}:
        return RetryableCloudError(str(exc))
    return RetryableCloudError(str(exc))


class S3Backend:
    def __init__(self, settings: CloudSettings, secrets: Secrets, *, multipart_threshold: int = 8 * 1024 * 1024):
        import boto3
        from boto3.s3.transfer import TransferConfig

        self.bucket = settings.bucket.strip()
        self.prefix = normalize_prefix(settings.prefix)
        kwargs: dict = {}
        if settings.region.strip():
            kwargs["region_name"] = settings.region.strip()
        if settings.endpoint.strip():
            kwargs["endpoint_url"] = settings.endpoint.strip()

        if secrets.s3_access_key_id and secrets.s3_secret_access_key:
            self.client = boto3.client(
                "s3",
                aws_access_key_id=secrets.s3_access_key_id,
                aws_secret_access_key=secrets.s3_secret_access_key,
                **kwargs,
            )
        elif settings.aws_profile.strip():
            session = boto3.Session(profile_name=settings.aws_profile.strip())
            self.client = session.client("s3", **kwargs)
        else:
            self.client = boto3.client("s3", **kwargs)

        self.transfer = TransferConfig(
            multipart_threshold=multipart_threshold,
            multipart_chunksize=max(multipart_threshold, 8 * 1024 * 1024),
            max_concurrency=4,
        )

    def list_prefix(self, max_keys: int = 1) -> list[str]:
        def _list():
            try:
                resp = self.client.list_objects_v2(
                    Bucket=self.bucket,
                    Prefix=self.prefix + ("/" if self.prefix else ""),
                    MaxKeys=max_keys,
                )
            except Exception as exc:
                raise _classify(exc) from exc
            return [obj["Key"] for obj in resp.get("Contents") or []]

        return retry_call(_list)

    def upload_file(self, local_path: str, key: str, size: int) -> UploadResult:
        src = win_long_path(local_path)

        def _put():
            try:
                self.client.upload_file(src, self.bucket, key, Config=self.transfer)
            except Exception as exc:
                raise _classify(exc) from exc
            try:
                head = self.client.head_object(Bucket=self.bucket, Key=key)
                etag = head.get("ETag", "").strip('"')
            except Exception:
                etag = None
            return UploadResult(key=key, etag=etag, bytes_sent=size)

        return retry_call(_put)

    def test_connection(self) -> ConnectionTestResult:
        try:
            self.list_prefix(1)
        except FatalCloudError as exc:
            return ConnectionTestResult(False, f"Cannot list bucket: {exc}", True)
        except Exception as exc:
            return ConnectionTestResult(False, f"Cannot list bucket: {exc}", True)

        probe_name = f".folderbackup-probe-{uuid.uuid4().hex}"
        key = "/".join(p for p in (self.prefix, probe_name) if p)
        import tempfile

        probe_deleted = True
        try:
            with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False) as fh:
                fh.write("folderbackup-probe")
                tmp_path = fh.name
            try:
                self.client.upload_file(tmp_path, self.bucket, key)
            except Exception as exc:
                return ConnectionTestResult(False, f"Cannot upload probe: {exc}", True)
            try:
                self.client.delete_object(Bucket=self.bucket, Key=key)
            except Exception as exc:
                probe_deleted = False
                return ConnectionTestResult(
                    True,
                    f"Read/write OK, but probe delete failed ({exc}). Backup can still run.",
                    False,
                )
            return ConnectionTestResult(True, f"S3 bucket '{self.bucket}' is reachable.", probe_deleted)
        finally:
            try:
                Path(tmp_path).unlink(missing_ok=True)
            except Exception:
                pass
