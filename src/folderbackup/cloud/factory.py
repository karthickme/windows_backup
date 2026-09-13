"""Build the active StorageBackend from settings + secrets."""

from __future__ import annotations

from folderbackup.cloud.azure import AzureBlobBackend
from folderbackup.cloud.base import StorageBackend
from folderbackup.cloud.gcs import GCSBackend
from folderbackup.cloud.s3 import S3Backend
from folderbackup.config.secrets import Secrets
from folderbackup.config.settings import AppSettings


def create_backend(settings: AppSettings, secrets: Secrets) -> StorageBackend:
    provider = settings.cloud.provider.lower().strip()
    threshold = int(settings.engine.multipart_threshold_mb * 1024 * 1024)
    if provider == "s3":
        return S3Backend(settings.cloud, secrets, multipart_threshold=threshold)
    if provider == "gcs":
        return GCSBackend(settings.cloud, secrets, multipart_threshold=threshold)
    if provider == "azure":
        return AzureBlobBackend(settings.cloud, secrets, multipart_threshold=threshold)
    raise ValueError(f"Unknown provider: {provider}")
