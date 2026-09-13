"""Content fingerprints used to skip touch-only files."""

from __future__ import annotations

import hashlib
from pathlib import Path

SAMPLE = 64 * 1024
DEFAULT_FULL_UNDER = 32 * 1024 * 1024
CHUNK = 1024 * 1024


def content_fingerprint(
    path: str | Path,
    size: int,
    *,
    full_under_bytes: int = DEFAULT_FULL_UNDER,
    opener=None,
) -> str:
    """SHA-256 of the full file if under threshold; else first+last 64KB and size."""
    open_fn = opener or (lambda p, mode: open(p, mode))
    h = hashlib.sha256()
    with open_fn(path, "rb") as fh:
        if size <= full_under_bytes:
            while True:
                chunk = fh.read(CHUNK)
                if not chunk:
                    break
                h.update(chunk)
        else:
            first = fh.read(SAMPLE)
            h.update(first)
            if size > SAMPLE:
                fh.seek(max(0, size - SAMPLE))
                last = fh.read(SAMPLE)
                h.update(last)
            h.update(str(size).encode("ascii"))
    return h.hexdigest()
