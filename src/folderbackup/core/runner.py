"""Load config, catalog, backend and execute one backup run."""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable
from pathlib import Path

from folderbackup.cloud.factory import create_backend
from folderbackup.config.secrets import Secrets, load_secrets
from folderbackup.config.settings import AppSettings, load_settings, validate_settings
from folderbackup.core.catalog import Catalog
from folderbackup.core.engine import BackupEngine, RunResult
from folderbackup.paths import catalog_path, ensure_app_dirs, lock_path

log = logging.getLogger("folderbackup.runner")


def run_from_disk(
    *,
    dry_run: bool = False,
    settings: AppSettings | None = None,
    secrets: Secrets | None = None,
    backend=None,
    progress: Callable[[str], None] | None = None,
    stop_event: threading.Event | None = None,
    catalog_file: Path | None = None,
    lock_file: Path | None = None,
) -> RunResult:
    ensure_app_dirs()
    settings = settings or load_settings()
    secrets = secrets if secrets is not None else load_secrets()
    errors = validate_settings(settings, require_cloud=backend is None)
    if errors:
        msg = "; ".join(errors)
        log.error(msg)
        return RunResult(status="error", error=msg)

    cat = Catalog(catalog_file or catalog_path())
    try:
        store = backend or create_backend(settings, secrets)
        engine = BackupEngine(
            settings,
            cat,
            store,
            lock_path=lock_file or lock_path(),
            stop_event=stop_event,
        )
        engine.set_progress(progress)
        return engine.run(dry_run=dry_run)
    finally:
        cat.close()
