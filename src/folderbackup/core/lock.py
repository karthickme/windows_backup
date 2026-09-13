"""Single-instance file lock so UI and --run-once cannot upload in parallel."""

from __future__ import annotations

import sys
from pathlib import Path
from types import TracebackType


class BackupAlreadyRunning(RuntimeError):
    pass


class RunLock:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._fh = None

    def acquire(self) -> None:
        self._fh = open(self.path, "a+b")
        try:
            self._fh.seek(0)
            if self._fh.read(1) == b"":
                self._fh.write(b"\0")
                self._fh.flush()
            if sys.platform == "win32":
                import msvcrt

                self._fh.seek(0)
                msvcrt.locking(self._fh.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl

                fcntl.flock(self._fh.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            self._fh.seek(0)
            self._fh.write(str(os_getpid()).encode("ascii"))
            self._fh.flush()
        except OSError as exc:
            self._close_quietly()
            raise BackupAlreadyRunning("Another backup is already running.") from exc

    def release(self) -> None:
        if self._fh is None:
            return
        try:
            if sys.platform == "win32":
                import msvcrt

                self._fh.seek(0)
                msvcrt.locking(self._fh.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl

                fcntl.flock(self._fh.fileno(), fcntl.LOCK_UN)
        except OSError:
            pass
        self._close_quietly()

    def _close_quietly(self) -> None:
        if self._fh is not None:
            try:
                self._fh.close()
            except OSError:
                pass
            self._fh = None

    def __enter__(self) -> RunLock:
        self.acquire()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        self.release()


def os_getpid() -> int:
    import os

    return os.getpid()
