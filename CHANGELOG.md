# Changelog

All notable changes to Folder Backup are documented in this file.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and versioning follows [Semantic Versioning](https://semver.org/spec/v2.0.0.html). Packaged Windows builds also receive a GitVersion SemVer from git history (see `GitVersion.yml`).

## [Unreleased]

### Fixed

- App startup no longer fails on Windows/Python 3.13 with `ZoneInfoNotFoundError: 'No time zone found with key local'` (APScheduler was given `timezone="local"`).
- CI **Retarget beta tag** no longer fails when the reusable `0.x.y-beta` tag does not exist yet (first testing pack, or `gh` 404 left as the step exit code).

### Changed

- Destination tab shows only the connection fields for the selected cloud (S3, GCS, or Azure).
- Merged pull-request head branches are deleted automatically (`feature/*`, `fix/*`, `deps/*`, `hotfix/*`). `main` and `testing` are not deleted.
- CI publishes a **beta GitHub pre-release** (Windows zip) on merge to `testing` (tag `0.1.0-beta`, retargeted on later testing merges), and a **stable** release on merge to `main` (tag `0.1.0`). GitVersion on `testing` still uses a `beta` label for InformationalVersion.

## [0.1.0] - 2026-09-13

Initial public-facing release of the Windows desktop backup app (`folderbackup` 0.1.0).

### Added

- CustomTkinter UI with Sources, Destination, Schedule, and Activity tabs, plus Save, Backup now, Dry run, and Cancel.
- Incremental backup of selected folders to a single destination: Amazon S3 (including S3-compatible endpoints), Google Cloud Storage, or Azure Blob Storage.
- Extension include/exclude filters, min/max size (MB), skip hidden/system/OneDrive online-only files, optional junction following, and built-in directory excludes (`.git`, `node_modules`, `__pycache__`, `.venv`, `venv`, `$Recycle.Bin`, `System Volume Information`).
- Local SQLite catalog (`%LOCALAPPDATA%\FolderBackup\catalog.sqlite`) that skips unchanged files using size and mtime, then a content fingerprint when those differ.
- Cloud object keys of the form `{prefix}/{drive-letter}/{relative-posix-path}` (UNC paths use an `_unc` segment).
- Append-only remote behavior: local deletes are marked in the catalog and are never deleted in the cloud.
- Crash-safe uploads (`in_progress` then retry), skip of sharing-violation / locked files, long-path (`\\?\`) opens, and parallel upload workers (default 4).
- Connection test that lists the prefix and uploads a probe object (delete of the probe is optional).
- Secrets in Windows Credential Manager via `keyring`; YAML holds non-secret settings only.
- In-app APScheduler (hourly / daily / weekly) while the window or tray icon is running.
- Optional per-user Task Scheduler jobs `FolderBackup` and `FolderBackupLogon` that run `python -m folderbackup --run-once` (or `FolderBackup.exe --run-once` when frozen).
- Headless CLI: `--run-once` and `--dry-run`, with a file lock so the UI and Task Scheduler cannot upload the same tree at once.
- System tray (pystray): close minimizes; Open, Backup now, and Quit.
- Daily rotating logs under the platformdirs log directory.
- Unit tests for filters, object keys, incremental decisions, settings, catalog/scanner, and the engine against a fake backend.
- Windows one-folder PyInstaller build (`FolderBackup.spec`, `scripts/build-windows.ps1`), GitVersion 6 (`GitVersion.yml`), and GitHub Actions CI that tests, builds, and attaches a zip on `v*` tags / published releases.

### Security

- Access keys, secret keys, Azure connection strings, and account keys are stored in Credential Manager, not `config.yaml` or log files.
- Connection-test probe objects are unique and intended to be deleted; backup itself never issues remote deletes for user files.

[Unreleased]: CHANGELOG.md
[0.1.0]: CHANGELOG.md
