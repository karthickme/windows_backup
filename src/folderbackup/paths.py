"""Application data, config, catalog, log, and lock locations."""

from __future__ import annotations

from pathlib import Path

from platformdirs import user_config_dir, user_data_dir, user_log_dir

APP_NAME = "FolderBackup"


def config_dir() -> Path:
    return Path(user_config_dir(APP_NAME, appauthor=False, roaming=True))


def data_dir() -> Path:
    return Path(user_data_dir(APP_NAME, appauthor=False, roaming=False))


def logs_dir() -> Path:
    return Path(user_log_dir(APP_NAME, appauthor=False))


def config_path() -> Path:
    return config_dir() / "config.yaml"


def catalog_path() -> Path:
    return data_dir() / "catalog.sqlite"


def lock_path() -> Path:
    return data_dir() / "backup.lock"


def ensure_app_dirs() -> None:
    config_dir().mkdir(parents=True, exist_ok=True)
    data_dir().mkdir(parents=True, exist_ok=True)
    logs_dir().mkdir(parents=True, exist_ok=True)
