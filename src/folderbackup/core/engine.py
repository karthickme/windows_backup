"""Incremental backup engine: scan, compare catalog, upload, never delete remotes."""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from pathlib import Path

from folderbackup.cloud.base import FatalCloudError, StorageBackend
from folderbackup.config.settings import AppSettings
from folderbackup.core.catalog import Catalog
from folderbackup.core.filters import is_sharing_violation
from folderbackup.core.hashing import content_fingerprint
from folderbackup.core.incremental import evaluate_file
from folderbackup.core.lock import BackupAlreadyRunning, RunLock
from folderbackup.core.scanner import FileJob, display_path, iter_source_files, win_long_path

log = logging.getLogger("folderbackup.engine")

ProgressCallback = Callable[[str], None]


@dataclass
class RunResult:
    status: str
    files_scanned: int = 0
    files_uploaded: int = 0
    files_skipped: int = 0
    files_failed: int = 0
    bytes_uploaded: int = 0
    local_missing: int = 0
    error: str | None = None
    would_upload: list[str] = field(default_factory=list)


class BackupEngine:
    def __init__(
        self,
        settings: AppSettings,
        catalog: Catalog,
        backend: StorageBackend,
        *,
        lock_path: str | Path | None = None,
        stop_event: threading.Event | None = None,
    ):
        self.settings = settings
        self.catalog = catalog
        self.backend = backend
        self.lock_path = Path(lock_path) if lock_path else None
        self.stop_event = stop_event or threading.Event()
        self._progress: ProgressCallback | None = None

    def set_progress(self, callback: ProgressCallback | None) -> None:
        self._progress = callback

    def _emit(self, message: str) -> None:
        log.info(message)
        if self._progress:
            try:
                self._progress(message)
            except Exception:
                pass

    def cancel(self) -> None:
        self.stop_event.set()

    def run(self, *, dry_run: bool | None = None) -> RunResult:
        dry = self.settings.engine.dry_run if dry_run is None else dry_run
        if self.lock_path is not None:
            lock = RunLock(self.lock_path)
            try:
                lock.acquire()
            except BackupAlreadyRunning as exc:
                return RunResult(status="locked", error=str(exc))
            try:
                return self._run_inner(dry=dry)
            finally:
                lock.release()
        return self._run_inner(dry=dry)

    def _run_inner(self, *, dry: bool) -> RunResult:
        result = RunResult(status="running")
        run_id = self.catalog.start_run(dry_run=dry)
        full_under = int(self.settings.engine.hash_full_under_mb * 1024 * 1024)
        seen: set[str] = set()
        workers = max(1, int(self.settings.engine.workers))
        jobs: list[FileJob] = []

        self._emit("Scanning source folders…")
        try:
            for job in iter_source_files(self.settings):
                if self.stop_event.is_set():
                    break
                jobs.append(job)
                seen.add(str(Path(job.local_path)))
        except Exception as exc:
            result.status = "error"
            result.error = f"Scan failed: {exc}"
            self.catalog.finish_run(
                run_id,
                files_scanned=0,
                files_uploaded=0,
                files_skipped=0,
                files_failed=0,
                bytes_uploaded=0,
                status="error",
                error=result.error,
            )
            return result

        result.files_scanned = len(jobs)
        self._emit(f"Found {len(jobs)} matching file(s).")

        counters = {
            "uploaded": 0,
            "skipped": 0,
            "failed": 0,
            "bytes": 0,
        }
        counter_lock = threading.Lock()
        would: list[str] = []

        def handle(job: FileJob) -> None:
            if self.stop_event.is_set():
                return
            path = str(Path(job.local_path))
            row = self.catalog.get(path)
            decision = evaluate_file(size=job.size, mtime_ns=job.mtime_ns, row=row)
            digest: str | None = None

            if decision.action == "skip":
                with counter_lock:
                    counters["skipped"] += 1
                return

            if decision.action == "need_hash":
                try:
                    digest = content_fingerprint(
                        win_long_path(path),
                        job.size,
                        full_under_bytes=full_under,
                    )
                except OSError as exc:
                    if is_sharing_violation(exc):
                        self._emit(f"Locked, will retry later: {display_path(path)}")
                        if not dry:
                            self.catalog.mark_skipped_locked(path, job.size, job.mtime_ns)
                        with counter_lock:
                            counters["skipped"] += 1
                        return
                    raise
                decision = evaluate_file(
                    size=job.size,
                    mtime_ns=job.mtime_ns,
                    row=row,
                    content_hash=digest,
                )
                if decision.action == "skip_touch":
                    if not dry:
                        self.catalog.update_mtime_hash(
                            path,
                            size=job.size,
                            mtime_ns=job.mtime_ns,
                            content_hash=digest,
                        )
                    with counter_lock:
                        counters["skipped"] += 1
                    self._emit(f"Unchanged (hash): {display_path(path)}")
                    return

            if decision.action != "upload":
                with counter_lock:
                    counters["skipped"] += 1
                return

            if dry:
                would.append(path)
                with counter_lock:
                    counters["uploaded"] += 1
                    counters["bytes"] += job.size
                self._emit(f"[dry-run] would upload: {display_path(path)}")
                return

            size_before = job.size
            try:
                live_size = Path(win_long_path(path)).stat().st_size
            except OSError as exc:
                if is_sharing_violation(exc):
                    self._emit(f"Locked, will retry later: {display_path(path)}")
                    self.catalog.mark_skipped_locked(path, job.size, job.mtime_ns)
                    with counter_lock:
                        counters["skipped"] += 1
                    return
                self.catalog.mark_error(path, str(exc))
                with counter_lock:
                    counters["failed"] += 1
                self._emit(f"Failed: {display_path(path)} ({exc})")
                return

            if live_size != size_before:
                self._emit(f"Size changed during backup, retry next run: {display_path(path)}")
                with counter_lock:
                    counters["skipped"] += 1
                return

            self.catalog.mark_in_progress(path, job.remote_key, job.size, job.mtime_ns)
            try:
                uploaded = self.backend.upload_file(path, job.remote_key, job.size)
                try:
                    after = Path(win_long_path(path)).stat().st_size
                except OSError:
                    after = live_size
                if after != size_before:
                    self._emit(f"File changed during upload, will retry next run: {display_path(path)}")
                    with counter_lock:
                        counters["skipped"] += 1
                    return
                if digest is None:
                    try:
                        digest = content_fingerprint(
                            win_long_path(path),
                            job.size,
                            full_under_bytes=full_under,
                        )
                    except OSError:
                        digest = None
                self.catalog.upsert_ok(
                    path,
                    size=job.size,
                    mtime_ns=job.mtime_ns,
                    content_hash=digest,
                    remote_key=uploaded.key,
                    remote_etag=uploaded.etag,
                )
                with counter_lock:
                    counters["uploaded"] += 1
                    counters["bytes"] += job.size
                self._emit(f"Uploaded: {display_path(path)}")
            except FatalCloudError as exc:
                self.catalog.mark_error(path, str(exc))
                with counter_lock:
                    counters["failed"] += 1
                self._emit(f"Fatal cloud error: {exc}")
                raise
            except OSError as exc:
                if is_sharing_violation(exc):
                    self.catalog.mark_skipped_locked(path, job.size, job.mtime_ns)
                    with counter_lock:
                        counters["skipped"] += 1
                    self._emit(f"Locked, will retry later: {display_path(path)}")
                    return
                self.catalog.mark_error(path, str(exc))
                with counter_lock:
                    counters["failed"] += 1
                self._emit(f"Failed: {display_path(path)} ({exc})")
            except Exception as exc:
                self.catalog.mark_error(path, str(exc))
                with counter_lock:
                    counters["failed"] += 1
                self._emit(f"Failed: {display_path(path)} ({exc})")

        try:
            if workers == 1 or dry:
                for job in jobs:
                    if self.stop_event.is_set():
                        break
                    handle(job)
            else:
                with ThreadPoolExecutor(max_workers=workers) as pool:
                    futures = [pool.submit(handle, job) for job in jobs]
                    for fut in as_completed(futures):
                        exc = fut.exception()
                        if exc:
                            raise exc
        except FatalCloudError as exc:
            result.status = "error"
            result.error = str(exc)
        except Exception as exc:
            result.status = "error"
            result.error = str(exc)

        if not dry and result.status != "error":
            result.local_missing = self.catalog.mark_local_missing(seen)

        result.files_uploaded = counters["uploaded"]
        result.files_skipped = counters["skipped"]
        result.files_failed = counters["failed"]
        result.bytes_uploaded = counters["bytes"]
        result.would_upload = would
        if result.status == "running":
            result.status = "ok" if result.files_failed == 0 else "partial"
        if self.stop_event.is_set() and result.status == "ok":
            result.status = "cancelled"

        self.catalog.finish_run(
            run_id,
            files_scanned=result.files_scanned,
            files_uploaded=result.files_uploaded,
            files_skipped=result.files_skipped,
            files_failed=result.files_failed,
            bytes_uploaded=result.bytes_uploaded,
            status=result.status,
            error=result.error,
        )
        self._emit(
            f"Run {result.status}: uploaded {result.files_uploaded}, "
            f"skipped {result.files_skipped}, failed {result.files_failed}."
        )
        return result
