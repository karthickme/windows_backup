"""Logging to %LOCALAPPDATA%\\FolderBackup\\logs with daily files."""

from __future__ import annotations

import logging
from datetime import datetime
from logging.handlers import TimedRotatingFileHandler
from pathlib import Path

from folderbackup.paths import ensure_app_dirs, logs_dir

_CONFIGURED = False


def setup_logging(*, also_console: bool = True) -> Path:
    global _CONFIGURED
    ensure_app_dirs()
    log_dir = logs_dir()
    log_dir.mkdir(parents=True, exist_ok=True)
    day = datetime.now().strftime("%Y%m%d")
    log_file = log_dir / f"run-{day}.log"

    root = logging.getLogger("folderbackup")
    root.setLevel(logging.INFO)
    if _CONFIGURED:
        return log_file

    fmt = logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
    fh = TimedRotatingFileHandler(log_file, when="midnight", backupCount=14, encoding="utf-8")
    fh.setFormatter(fmt)
    root.addHandler(fh)

    if also_console:
        sh = logging.StreamHandler()
        sh.setFormatter(fmt)
        root.addHandler(sh)

    _CONFIGURED = True
    return log_file


def get_logger(name: str = "folderbackup") -> logging.Logger:
    return logging.getLogger(name)
