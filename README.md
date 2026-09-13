# Folder Backup

Windows desktop app that incrementally copies selected folders to **one** personal cloud destination: Amazon S3 (or an S3-compatible endpoint), Google Cloud Storage, or Azure Blob Storage. New and changed files are uploaded; **files you delete on this PC are never deleted in the cloud.**

[![CI](https://github.com/OWNER/REPO/actions/workflows/ci.yml/badge.svg)](https://github.com/OWNER/REPO/actions/workflows/ci.yml)
[![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-3776AB.svg)](https://www.python.org/downloads/)
[![Platform](https://img.shields.io/badge/platform-Windows%2010%2F11-0078D6.svg)](https://www.microsoft.com/windows)

Replace `OWNER/REPO` in the CI badge after the project is published on GitHub. This repository does not currently include a license file.

## Git branches

**`main`** is production-ready. **`testing`** is the development / QA soak line. Open feature, fix, and Dependabot PRs against `testing` (pytest required), then promote **testing → main** when stable. Do not commit directly to `main`. Hotfixes branch from `main` (`hotfix/*`) and must also land on `testing`. Full flow: [CONTRIBUTING.md](CONTRIBUTING.md).

## Releases

| Path | GitHub Release |
| --- | --- |
| `feature/*` (etc.) → **`testing`** | **Beta** pre-release (`prerelease`, not latest). Tag like `v1.2.3-beta.N`. Zip: `FolderBackup-{semver}-windows-x64.zip`. |
| **`testing` → `main`** (or `hotfix/*` → `main`) | **Stable** release (not a pre-release, marked latest). Tag `vMajor.Minor.Patch`. |
| Manual `v*` tag | Pre-release identifier in the tag (a hyphen, for example `-beta`) → beta; otherwise stable. |

Production users should only download Releases that GitHub does **not** mark as pre-release. CI creates the release on push to `testing` or `main`; you do not need a separate published-release workflow.

## Features

- **Sources:** add any number of folders; include and exclude extensions (exclude wins); optional min/max size in MB; skip hidden files, system files, and OneDrive online-only placeholders; optional follow of directory junctions; built-in skip of `.git`, `node_modules`, `__pycache__`, `.venv`, `venv`, `$Recycle.Bin`, and `System Volume Information`.
- **Destination:** exactly one active provider (S3, GCS, or Azure). Bucket or container, object prefix, optional S3 region and compatible endpoint, **Test connection**.
- **Incremental catalog:** SQLite tracks size, mtime, content fingerprint, and remote key. Matching size and mtime skip the file; if those differ, a fingerprint avoids re-uploading touch-only files (full SHA-256 under 32 MB; otherwise first and last 64 KB plus size).
- **Scheduling:** in-app APScheduler while the window or tray is running (hourly, daily, weekly). Optional Windows Task Scheduler registration for unattended `--run-once` runs, including at logon.
- **UI:** CustomTkinter (Sources, Destination, Schedule, Activity). Save settings, Backup now, Dry run, Cancel. Close minimizes to the tray when pystray is available; **Quit** exits.
- **Credentials:** Windows Credential Manager via `keyring`. Access keys and Azure secrets are not written to YAML.

## Screenshots

UI screenshots can be added later under `docs/screenshots/` and linked from this section. This repository does not currently ship screenshot assets.

## What's new

Full history is in [CHANGELOG.md](CHANGELOG.md).

| Version | Date | Summary |
| --- | --- | --- |
| [Unreleased](CHANGELOG.md#unreleased) | — | No additional items yet. |
| [0.1.0](CHANGELOG.md#010---2026-09-13) | 2026-09-13 | Initial app: GUI, incremental upload to S3/GCS/Azure, schedule, keyring, Windows build/CI. |

## Requirements

- Windows 10 or 11
- Python 3.11 or newer
- A bucket or container you already own (the app does not create cloud accounts)

## Install

From the repository root:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
```

The console entry point `folderbackup` is installed as well as the `python -m folderbackup` module.

For a local exe build, install the packaging extra (`pyinstaller>=6`):

```powershell
python -m pip install -e ".[dev,packaging]"
```

## Run the GUI

```powershell
python -m folderbackup
```

or, after install:

```powershell
folderbackup
```

Use the tabs:

1. **Sources** — folders, extension and size filters, skip flags, upload worker count.
2. **Destination** — S3, GCS, or Azure; bucket/container, prefix, credentials; **Test connection**.
3. **Schedule** — enable in-app APScheduler (runs while the window or tray icon is alive). Optionally **Register Windows Task** so backups continue when the UI is closed.
4. **Activity** — live log, recent run history, progress.

## Headless / scheduled run

```powershell
python -m folderbackup --run-once
python -m folderbackup --run-once --dry-run
python -m folderbackup --dry-run
```

`--run-once` and `--dry-run` both skip the GUI. `--run-once` is the command Task Scheduler registers. Dry-run lists files that would upload and does not write objects to the cloud or update per-file catalog rows; it still records a dry-run entry in run history.

`--run-once` uses a file lock (`backup.lock`) so the UI and Task Scheduler cannot upload the same tree at once. Exit status `2` means another run held the lock; `0` means `ok`, `partial`, or `cancelled`; any other failure is `1`.

Object keys look like:

`{prefix}/{drive-letter}/{relative-posix-path}`

Example: `laptop-backup/C/Users/you/Documents/report.pdf`

UNC paths use an `_unc` segment after the prefix.

## Configuration paths

| Data | Location |
| --- | --- |
| Settings (no secrets) | `%APPDATA%\FolderBackup\config.yaml` |
| SQLite catalog | `%LOCALAPPDATA%\FolderBackup\catalog.sqlite` |
| Run lock | `%LOCALAPPDATA%\FolderBackup\backup.lock` |
| Daily logs | `%LOCALAPPDATA%\FolderBackup\Logs\run-YYYYMMDD.log` (14-day rotation) |
| Secrets | Windows Credential Manager, service name `FolderBackup` |

Paths are resolved with `platformdirs` (`appauthor=False`). The Activity tab also prints the resolved config path.

## Cloud setup and least privilege

Create the bucket or container yourself. Use a dedicated IAM user, service account, or storage credential that can write **only** that location. Do not paste console passwords into the app.

### Amazon S3

Allow at least:

- `s3:ListBucket` on the bucket (optionally limited with `s3:prefix`)
- `s3:PutObject` (and `s3:AbortMultipartUpload` / `s3:ListBucketMultipartUploads` for large files) on `arn:aws:s3:::YOUR_BUCKET/YOUR_PREFIX/*`
- `s3:DeleteObject` only for the connection-test probe (optional; if delete fails, backup still runs)
- `s3:GetObject` only if you add restore later

Example identity-based policy shape:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": ["s3:ListBucket"],
      "Resource": "arn:aws:s3:::YOUR_BUCKET",
      "Condition": { "StringLike": { "s3:prefix": ["YOUR_PREFIX/*"] } }
    },
    {
      "Effect": "Allow",
      "Action": ["s3:PutObject", "s3:AbortMultipartUpload", "s3:DeleteObject"],
      "Resource": "arn:aws:s3:::YOUR_BUCKET/YOUR_PREFIX/*"
    }
  ]
}
```

Auth in the Destination tab: access key ID plus secret access key (Credential Manager), or an existing AWS profile name. Optional custom `endpoint` supports S3-compatible stores. Default prefix is `laptop-backup`. Multipart threshold defaults to 8 MB.

### Google Cloud Storage

Grant a role such as **Storage Object Admin** scoped to the bucket, or a custom role with `storage.objects.list`, `storage.objects.create`, and `storage.objects.delete` (delete is only for the probe). Point the UI at a service-account JSON file, or leave the path empty to use Application Default Credentials. GCS credentials are not stored in keyring.

### Azure Blob Storage

Assign **Storage Blob Data Contributor** on the container (or a narrower custom role with list and write). Paste a connection string, or account name plus account key. The “bucket” field is the **container** name.

## Credential storage

S3 access key ID, S3 secret access key, Azure connection string, and Azure account key are stored with `keyring` under the Windows Credential Manager service `FolderBackup`. They are never written to `config.yaml`. Do not put secrets in YAML, environment files committed to git, or issue reports.

Bucket/container, prefix, region, endpoint, AWS profile name, GCS JSON **path**, and Azure account **name** are non-secret settings in YAML.

## Scheduling

**In-app (APScheduler).** Enable the schedule on the Schedule tab. Hourly uses a one-hour interval; daily and weekly use local clock time (`HH:MM`); weekly also uses a weekday. Jobs coalesce and allow a single instance. This scheduler runs only while the process is alive (window or tray).

**Windows Task Scheduler.** **Register Windows Task** creates a limited-rights task named `FolderBackup` that runs `python -m folderbackup --run-once` (or `"FolderBackup.exe" --run-once` when frozen). Intervals: hourly, daily at the given time, or weekly on the chosen day. If **Also run at Windows logon** is checked, a second task `FolderBackupLogon` is created (`ONLOGON`). **Unregister Windows Task** removes both.

## Building the Windows executable

A one-folder PyInstaller build is preferred over `--onefile` (faster start, fewer antivirus false positives). The frozen exe accepts `--run-once` the same way as the module.

Locally, after `pip install -e ".[dev,packaging]"`:

```powershell
.\scripts\build-windows.ps1
```

The script resolves SemVer via GitVersion when installed (`dotnet-gitversion` or `gitversion`), otherwise `git describe` or `0.1.0`. It writes `src/folderbackup/_version.py` and `packaging/file_version_info.txt`, runs `FolderBackup.spec`, and zips `dist\FolderBackup\` to `dist\FolderBackup-<version>-windows-x64.zip`. Output exe: `dist\FolderBackup\FolderBackup.exe`.

Equivalent manual invocation:

```powershell
python -m PyInstaller --noconfirm --clean FolderBackup.spec
```

### GitHub Actions, GitVersion, and Releases

Workflow: [`.github/workflows/ci.yml`](.github/workflows/ci.yml). Jobs are split so **pytest** can be a required status check without blocking QA merges on PyInstaller.

1. Job **`test`**: pytest on `windows-latest` for pull requests to `testing` and `main`, and for pushes to `testing` (merge-to-testing gate) and `main`. Required check name remains **`test`**.
2. Job **`pack`**: full history, GitVersion 6 (`GitVersion.yml`: `main` is mainline with no pre-release label; `testing` uses a `beta` pre-release label), Python 3.12, `.[dev,packaging]`, Windows zip artifacts. Runs on push to `testing` or `main`/`master`, on `v*` tags, and on optional `workflow_dispatch` — not on PRs into `testing`.
3. Creates a GitHub Release and attaches `FolderBackup-{semver}-windows-x64.zip`. Push to **`testing`** is a pre-release (`make_latest: false`). Push to **`main`** is stable (`make_latest: true`) when GitVersion has no pre-release suffix. Manual `v*` tags with a hyphen are beta; otherwise stable. Tags created with `GITHUB_TOKEN` do not re-run the workflow, so the zip is not published twice.

PRs into `main` must come from `testing` or `hotfix/*` ([`.github/workflows/protect-main.yml`](.github/workflows/protect-main.yml)). Rulesets: [.github/SETUP.md](.github/SETUP.md).

## Tests

```powershell
python -m pytest
```

Unit tests cover filters, object-key mapping, incremental skip/upload decisions, settings validation, catalog/scanner behavior, and the engine against a fake backend (including “local delete does not remove the cloud object”). Optional live checks use **Test connection** in the UI against a dedicated test prefix.

## Behavior notes

- Incremental compare: size + mtime first; if those differ, a content fingerprint avoids re-uploading touch-only files.
- Crash safety: files are marked `in_progress` before upload and retried on the next run.
- Locked or open files (sharing violation) are skipped and retried later.
- OneDrive online-only placeholders are skipped by default.
- Empty folders are not uploaded.
- Directory junctions are not followed unless that option is enabled.
- Paths longer than 260 characters use `\\?\` prefixes when opening files.
- Transient cloud errors are retried with backoff; 400/401/403/404-class failures are fatal for the run.

## Out of scope (v1)

Bidirectional sync, restore UI, client-side encryption, and multi-machine sharing of the same catalog.

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for the `main` + `testing` branch strategy and required GitHub checks. Bugs, features, and dependency upgrades use GitHub issue forms under **New issue**. Dependabot opens weekly PRs against **`testing`** for `pip` (`pyproject.toml`) and GitHub Actions, grouped for Azure, Google Cloud, and AWS SDK stacks. Commit messages use `chore(deps)` / `chore(ci)` prefixes. Patch and minor Dependabot PRs may squash-merge when CI is green; **major** bumps stay open — file a **Dependency update** issue and run the backup/UI/CI checklist before merging.

## Security

Never paste access keys, secret keys, connection strings, account keys, or service-account JSON into GitHub issues, pull requests, or chat. Rotate any credential that may have been exposed. Report suspected credential leaks privately and revoke the key in the cloud console.

## Changelog

See [CHANGELOG.md](CHANGELOG.md) for Keep a Changelog / SemVer notes, including [Unreleased](CHANGELOG.md#unreleased) and [0.1.0](CHANGELOG.md#010---2026-09-13).
