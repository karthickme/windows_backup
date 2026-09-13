"""Entry: GUI by default, or --run-once / --dry-run for scheduled jobs."""

from __future__ import annotations

import argparse
import sys

from folderbackup.core.logging_setup import setup_logging
from folderbackup.core.runner import run_from_disk
from folderbackup.paths import ensure_app_dirs


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Incremental folder backup to S3, GCS, or Azure Blob.")
    parser.add_argument(
        "--run-once",
        action="store_true",
        help="Run one incremental backup using saved settings (for Task Scheduler).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="List files that would be uploaded without writing to the cloud or catalog.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    ensure_app_dirs()
    if args.run_once or args.dry_run:
        setup_logging(also_console=True)
        result = run_from_disk(dry_run=bool(args.dry_run))
        print(
            f"{result.status}: scanned={result.files_scanned} uploaded={result.files_uploaded} "
            f"skipped={result.files_skipped} failed={result.files_failed} bytes={result.bytes_uploaded}"
        )
        if result.error:
            print(result.error, file=sys.stderr)
        if result.status == "locked":
            return 2
        return 0 if result.status in {"ok", "partial", "cancelled"} else 1

    from folderbackup.ui.app import launch

    launch()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
