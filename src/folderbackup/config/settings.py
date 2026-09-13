"""YAML settings (no secrets) persisted under %APPDATA%\\FolderBackup."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field, fields
from pathlib import Path
from typing import Any

import yaml

from folderbackup.paths import config_path, ensure_app_dirs

PROVIDERS = ("s3", "gcs", "azure")
INTERVALS = ("hourly", "daily", "weekly")


@dataclass
class FilterSettings:
    include_extensions: list[str] = field(default_factory=list)
    exclude_extensions: list[str] = field(default_factory=list)
    min_size_mb: float | None = None
    max_size_mb: float | None = None
    skip_hidden: bool = True
    skip_system: bool = True
    skip_online_only: bool = True
    follow_junctions: bool = False
    use_builtin_excludes: bool = True
    extra_exclude_dirs: list[str] = field(default_factory=list)


@dataclass
class CloudSettings:
    provider: str = "s3"
    bucket: str = ""
    prefix: str = "laptop-backup"
    region: str = ""
    endpoint: str = ""
    aws_profile: str = ""
    gcs_credentials_path: str = ""
    azure_account_name: str = ""


@dataclass
class ScheduleSettings:
    enabled: bool = False
    interval: str = "daily"
    time: str = "02:00"
    weekday: str = "mon"
    run_on_logon: bool = False


@dataclass
class EngineSettings:
    workers: int = 4
    hash_full_under_mb: float = 32.0
    multipart_threshold_mb: float = 8.0
    dry_run: bool = False


@dataclass
class AppSettings:
    folders: list[str] = field(default_factory=list)
    filters: FilterSettings = field(default_factory=FilterSettings)
    cloud: CloudSettings = field(default_factory=CloudSettings)
    schedule: ScheduleSettings = field(default_factory=ScheduleSettings)
    engine: EngineSettings = field(default_factory=EngineSettings)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _coerce_dataclass(cls, data: Any):
    if not isinstance(data, dict):
        return cls()
    allowed = {f.name for f in fields(cls)}
    kwargs = {k: v for k, v in data.items() if k in allowed}
    return cls(**kwargs)


def default_settings() -> AppSettings:
    return AppSettings()


def load_settings(path: Path | None = None) -> AppSettings:
    ensure_app_dirs()
    target = path or config_path()
    if not target.exists():
        return default_settings()
    raw = yaml.safe_load(target.read_text(encoding="utf-8")) or {}
    return AppSettings(
        folders=list(raw.get("folders") or []),
        filters=_coerce_dataclass(FilterSettings, raw.get("filters")),
        cloud=_coerce_dataclass(CloudSettings, raw.get("cloud")),
        schedule=_coerce_dataclass(ScheduleSettings, raw.get("schedule")),
        engine=_coerce_dataclass(EngineSettings, raw.get("engine")),
    )


def save_settings(settings: AppSettings, path: Path | None = None) -> Path:
    ensure_app_dirs()
    target = path or config_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    payload = settings.to_dict()
    target.write_text(
        yaml.safe_dump(payload, sort_keys=False, allow_unicode=True),
        encoding="utf-8",
    )
    return target


def validate_settings(settings: AppSettings, *, require_cloud: bool = True) -> list[str]:
    errors: list[str] = []
    if not settings.folders:
        errors.append("Add at least one source folder.")
    for folder in settings.folders:
        if not Path(folder).exists():
            errors.append(f"Folder does not exist: {folder}")
    f = settings.filters
    if f.min_size_mb is not None and f.min_size_mb < 0:
        errors.append("Minimum size cannot be negative.")
    if f.max_size_mb is not None and f.max_size_mb < 0:
        errors.append("Maximum size cannot be negative.")
    if (
        f.min_size_mb is not None
        and f.max_size_mb is not None
        and f.min_size_mb > f.max_size_mb
    ):
        errors.append("Minimum size must be less than or equal to maximum size.")
    if settings.cloud.provider not in PROVIDERS:
        errors.append(f"Unknown provider: {settings.cloud.provider}")
    if require_cloud and not settings.cloud.bucket.strip():
        errors.append("Bucket or container name is required.")
    if settings.engine.workers < 1:
        errors.append("Worker count must be at least 1.")
    if settings.schedule.interval not in INTERVALS:
        errors.append(f"Unknown interval: {settings.schedule.interval}")
    return errors
