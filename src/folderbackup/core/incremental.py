"""Pure incremental skip/upload decisions (easy to unit test)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from folderbackup.core.catalog import STATUS_IN_PROGRESS, CatalogRow

Action = Literal["skip", "need_hash", "skip_touch", "upload"]


@dataclass(frozen=True)
class IncrementalDecision:
    action: Action
    reason: str


def evaluate_file(
    *,
    size: int,
    mtime_ns: int,
    row: CatalogRow | None,
    content_hash: str | None = None,
) -> IncrementalDecision:
    """Decide whether a local file should be hashed, skipped, or uploaded.

    Fast path: matching size + mtime and status ok -> skip.
    If size/mtime disagree, hash to avoid re-uploading touch-only files.
    Prefer hash over mtime when they disagree. Never implies a remote delete.
    """
    if row is None:
        return IncrementalDecision("upload", "new-file")

    if row.status == STATUS_IN_PROGRESS:
        return IncrementalDecision("upload", "retry-in-progress")

    if row.status == "ok" and size == row.size and mtime_ns == row.mtime_ns:
        return IncrementalDecision("skip", "size-mtime-match")

    if content_hash is None:
        return IncrementalDecision("need_hash", "size-or-mtime-changed")

    if row.content_hash and content_hash == row.content_hash:
        return IncrementalDecision("skip_touch", "hash-match-mtime-differed")

    return IncrementalDecision("upload", "content-changed")
