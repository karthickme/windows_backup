"""Retry helper for cloud SDK calls."""

from __future__ import annotations

import random
import time
from collections.abc import Callable
from typing import TypeVar

from folderbackup.cloud.base import FatalCloudError, RetryableCloudError

T = TypeVar("T")


def retry_call(
    fn: Callable[[], T],
    *,
    retries: int = 5,
    base_delay: float = 1.0,
    max_delay: float = 30.0,
) -> T:
    delay = base_delay
    last: BaseException | None = None
    for attempt in range(retries):
        try:
            return fn()
        except FatalCloudError:
            raise
        except RetryableCloudError as exc:
            last = exc
            if attempt == retries - 1:
                break
            time.sleep(delay + random.random() * 0.25)
            delay = min(delay * 2, max_delay)
        except Exception as exc:
            last = exc
            if attempt == retries - 1:
                break
            time.sleep(delay + random.random() * 0.25)
            delay = min(delay * 2, max_delay)
    assert last is not None
    raise last
