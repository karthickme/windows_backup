"""Optional per-user Windows Scheduled Task for python -m folderbackup --run-once."""

from __future__ import annotations

import shutil
import subprocess
import sys
from dataclasses import dataclass

TASK_NAME = "FolderBackup"
TASK_LOGON = "FolderBackupLogon"


@dataclass
class TaskStatus:
    registered: bool
    logon_registered: bool
    detail: str = ""


def backup_command() -> str:
    if getattr(sys, "frozen", False):
        return f'"{sys.executable}" --run-once'
    return f'"{sys.executable}" -m folderbackup --run-once'


def _run_schtasks(args: list[str]) -> subprocess.CompletedProcess[str]:
    exe = shutil.which("schtasks") or "schtasks"
    return subprocess.run(
        [exe, *args],
        capture_output=True,
        text=True,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )


def _query(name: str) -> bool:
    result = _run_schtasks(["/Query", "/TN", name])
    return result.returncode == 0


def get_status() -> TaskStatus:
    if sys.platform != "win32":
        return TaskStatus(False, False, "Windows Task Scheduler is only available on Windows.")
    return TaskStatus(_query(TASK_NAME), _query(TASK_LOGON))


def unregister() -> str:
    messages = []
    for name in (TASK_NAME, TASK_LOGON):
        if _query(name):
            result = _run_schtasks(["/Delete", "/TN", name, "/F"])
            if result.returncode != 0:
                messages.append((result.stderr or result.stdout or f"Failed to delete {name}").strip())
            else:
                messages.append(f"Removed task {name}.")
    return "\n".join(messages) or "No scheduled tasks were registered."


def register(*, interval: str, time: str, weekday: str, run_on_logon: bool) -> str:
    if sys.platform != "win32":
        return "Windows Task Scheduler is only available on Windows."
    cmd = backup_command()
    hour_minute = time.strip() or "02:00"
    args = ["/Create", "/TN", TASK_NAME, "/TR", cmd, "/RL", "LIMITED", "/F"]
    if interval == "hourly":
        args += ["/SC", "HOURLY"]
    elif interval == "weekly":
        day = (weekday or "MON").upper()[:3]
        args += ["/SC", "WEEKLY", "/D", day, "/ST", hour_minute]
    else:
        args += ["/SC", "DAILY", "/ST", hour_minute]

    result = _run_schtasks(args)
    messages = []
    if result.returncode != 0:
        messages.append((result.stderr or result.stdout or "Failed to create task").strip())
    else:
        messages.append(f"Registered task {TASK_NAME} ({interval}).")

    if run_on_logon:
        logon = _run_schtasks(
            ["/Create", "/TN", TASK_LOGON, "/TR", cmd, "/SC", "ONLOGON", "/RL", "LIMITED", "/F"]
        )
        if logon.returncode != 0:
            messages.append((logon.stderr or logon.stdout or "Failed to create logon task").strip())
        else:
            messages.append(f"Registered task {TASK_LOGON} (at logon).")
    elif _query(TASK_LOGON):
        _run_schtasks(["/Delete", "/TN", TASK_LOGON, "/F"])
        messages.append(f"Removed task {TASK_LOGON}.")
    return "\n".join(messages)
