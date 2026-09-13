"""SQLite backup catalog: local path metadata and run history."""

from __future__ import annotations

import sqlite3
import threading
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS files (
    local_path TEXT PRIMARY KEY,
    size INTEGER NOT NULL,
    mtime_ns INTEGER NOT NULL,
    content_hash TEXT,
    remote_key TEXT,
    remote_etag TEXT,
    status TEXT NOT NULL DEFAULT 'ok',
    last_error TEXT,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    started_at TEXT NOT NULL,
    finished_at TEXT,
    files_scanned INTEGER DEFAULT 0,
    files_uploaded INTEGER DEFAULT 0,
    files_skipped INTEGER DEFAULT 0,
    files_failed INTEGER DEFAULT 0,
    bytes_uploaded INTEGER DEFAULT 0,
    status TEXT NOT NULL DEFAULT 'running',
    error TEXT,
    dry_run INTEGER NOT NULL DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_files_status ON files(status);
CREATE INDEX IF NOT EXISTS idx_files_remote_key ON files(remote_key);
"""

STATUS_OK = "ok"
STATUS_IN_PROGRESS = "in_progress"
STATUS_LOCAL_MISSING = "local_missing"
STATUS_ERROR = "error"
STATUS_SKIPPED_LOCKED = "skipped_locked"


@dataclass
class CatalogRow:
    local_path: str
    size: int
    mtime_ns: int
    content_hash: str | None
    remote_key: str | None
    remote_etag: str | None
    status: str
    last_error: str | None
    updated_at: str


@dataclass
class RunRecord:
    id: int
    started_at: str
    finished_at: str | None
    files_scanned: int
    files_uploaded: int
    files_skipped: int
    files_failed: int
    bytes_uploaded: int
    status: str
    error: str | None
    dry_run: bool


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


class Catalog:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(self.path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA foreign_keys=ON")
        self._conn.executescript(SCHEMA)
        self._conn.commit()

    def close(self) -> None:
        with self._lock:
            self._conn.close()

    @contextmanager
    def _tx(self):
        with self._lock:
            try:
                yield self._conn
                self._conn.commit()
            except Exception:
                self._conn.rollback()
                raise

    def get(self, local_path: str) -> CatalogRow | None:
        with self._lock:
            cur = self._conn.execute(
                "SELECT * FROM files WHERE local_path = ?",
                (local_path,),
            )
            row = cur.fetchone()
        return _row_to_file(row) if row else None

    def upsert_ok(
        self,
        local_path: str,
        *,
        size: int,
        mtime_ns: int,
        content_hash: str | None,
        remote_key: str,
        remote_etag: str | None,
    ) -> None:
        now = _utcnow()
        with self._tx() as conn:
            conn.execute(
                """
                INSERT INTO files (
                    local_path, size, mtime_ns, content_hash, remote_key,
                    remote_etag, status, last_error, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, NULL, ?)
                ON CONFLICT(local_path) DO UPDATE SET
                    size=excluded.size,
                    mtime_ns=excluded.mtime_ns,
                    content_hash=excluded.content_hash,
                    remote_key=excluded.remote_key,
                    remote_etag=excluded.remote_etag,
                    status=excluded.status,
                    last_error=NULL,
                    updated_at=excluded.updated_at
                """,
                (
                    local_path,
                    size,
                    mtime_ns,
                    content_hash,
                    remote_key,
                    remote_etag,
                    STATUS_OK,
                    now,
                ),
            )

    def mark_in_progress(self, local_path: str, remote_key: str, size: int, mtime_ns: int) -> None:
        now = _utcnow()
        with self._tx() as conn:
            conn.execute(
                """
                INSERT INTO files (
                    local_path, size, mtime_ns, content_hash, remote_key,
                    remote_etag, status, last_error, updated_at
                ) VALUES (?, ?, ?, NULL, ?, NULL, ?, NULL, ?)
                ON CONFLICT(local_path) DO UPDATE SET
                    remote_key=excluded.remote_key,
                    status=excluded.status,
                    last_error=NULL,
                    updated_at=excluded.updated_at
                """,
                (local_path, size, mtime_ns, remote_key, STATUS_IN_PROGRESS, now),
            )

    def mark_error(self, local_path: str, message: str) -> None:
        now = _utcnow()
        with self._tx() as conn:
            conn.execute(
                """
                INSERT INTO files (
                    local_path, size, mtime_ns, content_hash, remote_key,
                    remote_etag, status, last_error, updated_at
                ) VALUES (?, 0, 0, NULL, NULL, NULL, ?, ?, ?)
                ON CONFLICT(local_path) DO UPDATE SET
                    status=excluded.status,
                    last_error=excluded.last_error,
                    updated_at=excluded.updated_at
                """,
                (local_path, STATUS_ERROR, message[:2000], now),
            )

    def mark_skipped_locked(self, local_path: str, size: int, mtime_ns: int) -> None:
        now = _utcnow()
        with self._tx() as conn:
            conn.execute(
                """
                INSERT INTO files (
                    local_path, size, mtime_ns, content_hash, remote_key,
                    remote_etag, status, last_error, updated_at
                ) VALUES (?, ?, ?, NULL, NULL, NULL, ?, 'sharing violation', ?)
                ON CONFLICT(local_path) DO UPDATE SET
                    status=excluded.status,
                    last_error=excluded.last_error,
                    updated_at=excluded.updated_at
                """,
                (local_path, size, mtime_ns, STATUS_SKIPPED_LOCKED, now),
            )

    def update_mtime_hash(
        self,
        local_path: str,
        *,
        size: int,
        mtime_ns: int,
        content_hash: str | None,
    ) -> None:
        now = _utcnow()
        with self._tx() as conn:
            conn.execute(
                """
                UPDATE files SET size=?, mtime_ns=?, content_hash=?,
                    status=?, last_error=NULL, updated_at=?
                WHERE local_path=?
                """,
                (size, mtime_ns, content_hash, STATUS_OK, now, local_path),
            )

    def mark_local_missing(self, seen_paths: set[str]) -> int:
        """Mark catalog rows whose local files were not seen this run.

        Remote objects are never deleted.
        """
        now = _utcnow()
        count = 0
        with self._tx() as conn:
            cur = conn.execute("SELECT local_path FROM files WHERE status != ?", (STATUS_LOCAL_MISSING,))
            existing = [r[0] for r in cur.fetchall()]
            for path in existing:
                if path not in seen_paths:
                    conn.execute(
                        "UPDATE files SET status=?, updated_at=? WHERE local_path=?",
                        (STATUS_LOCAL_MISSING, now, path),
                    )
                    count += 1
        return count

    def in_progress_paths(self) -> list[str]:
        with self._lock:
            cur = self._conn.execute(
                "SELECT local_path FROM files WHERE status = ?",
                (STATUS_IN_PROGRESS,),
            )
            return [r[0] for r in cur.fetchall()]

    def start_run(self, *, dry_run: bool) -> int:
        now = _utcnow()
        with self._tx() as conn:
            cur = conn.execute(
                """
                INSERT INTO runs (started_at, status, dry_run)
                VALUES (?, 'running', ?)
                """,
                (now, 1 if dry_run else 0),
            )
            return int(cur.lastrowid)

    def finish_run(
        self,
        run_id: int,
        *,
        files_scanned: int,
        files_uploaded: int,
        files_skipped: int,
        files_failed: int,
        bytes_uploaded: int,
        status: str,
        error: str | None = None,
    ) -> None:
        now = _utcnow()
        with self._tx() as conn:
            conn.execute(
                """
                UPDATE runs SET finished_at=?, files_scanned=?, files_uploaded=?,
                    files_skipped=?, files_failed=?, bytes_uploaded=?,
                    status=?, error=?
                WHERE id=?
                """,
                (
                    now,
                    files_scanned,
                    files_uploaded,
                    files_skipped,
                    files_failed,
                    bytes_uploaded,
                    status,
                    error,
                    run_id,
                ),
            )

    def latest_runs(self, limit: int = 20) -> list[RunRecord]:
        with self._lock:
            cur = self._conn.execute(
                "SELECT * FROM runs ORDER BY id DESC LIMIT ?",
                (limit,),
            )
            rows = cur.fetchall()
        return [_row_to_run(r) for r in rows]

    def last_successful_run(self) -> RunRecord | None:
        with self._lock:
            cur = self._conn.execute(
                "SELECT * FROM runs WHERE status = 'ok' ORDER BY id DESC LIMIT 1"
            )
            row = cur.fetchone()
        return _row_to_run(row) if row else None


def _row_to_file(row: sqlite3.Row) -> CatalogRow:
    return CatalogRow(
        local_path=row["local_path"],
        size=row["size"],
        mtime_ns=row["mtime_ns"],
        content_hash=row["content_hash"],
        remote_key=row["remote_key"],
        remote_etag=row["remote_etag"],
        status=row["status"],
        last_error=row["last_error"],
        updated_at=row["updated_at"],
    )


def _row_to_run(row: sqlite3.Row) -> RunRecord:
    return RunRecord(
        id=row["id"],
        started_at=row["started_at"],
        finished_at=row["finished_at"],
        files_scanned=row["files_scanned"],
        files_uploaded=row["files_uploaded"],
        files_skipped=row["files_skipped"],
        files_failed=row["files_failed"],
        bytes_uploaded=row["bytes_uploaded"],
        status=row["status"],
        error=row["error"],
        dry_run=bool(row["dry_run"]),
    )
