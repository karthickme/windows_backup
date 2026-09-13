"""In-app APScheduler for backups while the UI/tray is running."""

from __future__ import annotations

import logging
from collections.abc import Callable
from datetime import datetime

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

from folderbackup.config.settings import ScheduleSettings

log = logging.getLogger("folderbackup.schedule")

JOB_ID = "folderbackup_incremental"


class AppScheduler:
    def __init__(self, callback: Callable[[], None]):
        self._callback = callback
        self._scheduler = BackgroundScheduler(timezone="local")
        self._started = False

    def start(self) -> None:
        if not self._started:
            self._scheduler.start()
            self._started = True

    def shutdown(self) -> None:
        if self._started:
            self._scheduler.shutdown(wait=False)
            self._started = False

    def apply(self, schedule: ScheduleSettings) -> datetime | None:
        self.start()
        try:
            self._scheduler.remove_job(JOB_ID)
        except Exception:
            pass
        if not schedule.enabled:
            return None
        trigger = build_trigger(schedule)
        self._scheduler.add_job(
            self._callback,
            trigger=trigger,
            id=JOB_ID,
            replace_existing=True,
            max_instances=1,
            coalesce=True,
        )
        job = self._scheduler.get_job(JOB_ID)
        nxt = job.next_run_time if job else None
        log.info("Scheduled next run at %s", nxt)
        return nxt

    def next_run_time(self) -> datetime | None:
        job = self._scheduler.get_job(JOB_ID)
        return job.next_run_time if job else None


def build_trigger(schedule: ScheduleSettings):
    hour, minute = _parse_hhmm(schedule.time)
    if schedule.interval == "hourly":
        return IntervalTrigger(hours=1)
    if schedule.interval == "weekly":
        day = (schedule.weekday or "mon").lower()[:3]
        return CronTrigger(day_of_week=day, hour=hour, minute=minute)
    return CronTrigger(hour=hour, minute=minute)


def _parse_hhmm(value: str) -> tuple[int, int]:
    try:
        parts = (value or "02:00").strip().split(":")
        return int(parts[0]), int(parts[1])
    except (ValueError, IndexError):
        return 2, 0
