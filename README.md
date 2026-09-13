# Folder Backup

Windows desktop app that incrementally backs up selected folders to **one** personal cloud destination: Amazon S3 (or S3-compatible), Google Cloud Storage, or Azure Blob Storage.

New and changed files are uploaded. **Files you delete on the laptop are never deleted in the cloud.**

## Requirements

- Windows 10/11
- Python 3.11 or newer
- A bucket or container you already own (the app does not create cloud accounts)

## Install

From this directory:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
```

## Run the UI

```powershell
python -m folderbackup
```

or, after install:

```powershell
folderbackup
```

Use the tabs:

1. **Sources** — add folders, include/exclude extensions, min/max size (MB), skip hidden/system/OneDrive online-only files.
2. **Destination** — choose S3, GCS, or Azure; enter bucket/container, prefix, and credentials; **Test connection**.
3. **Schedule** — enable in-app APScheduler (runs while the window or tray icon is alive). Optionally **Register Windows Task** so `python -m folderbackup --run-once` still runs when the UI is closed.
4. **Activity** — live log, last runs, **Backup now** / **Dry run**.

Closing the window minimizes to the tray if `pystray` is available. Choose **Quit** from the tray menu to exit.

Settings are saved to `%APPDATA%\FolderBackup\config.yaml`. Secrets go to **Windows Credential Manager** via `keyring` (never YAML or logs). The SQLite catalog is `%LOCALAPPDATA%\FolderBackup\catalog.sqlite`. Daily logs: `%LOCALAPPDATA%\FolderBackup\logs\run-YYYYMMDD.log`.

## Headless / scheduled run

```powershell
python -m folderbackup --run-once
python -m folderbackup --dry-run
```

`--run-once` uses a file lock so the UI and Task Scheduler cannot upload the same tree at once. Dry-run lists files that would upload and does not write to the cloud or catalog.

Object keys look like:

`{prefix}/{drive-letter}/{relative-posix-path}`

Example: `laptop-backup/C/Users/you/Documents/report.pdf`

## IAM least privilege

Create the bucket/container yourself. Create a dedicated user or service principal that can write **only** that bucket. You do not paste console passwords into the app.

### Amazon S3

Allow at least:

- `s3:ListBucket` on the bucket
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

Auth in the Destination tab: access key + secret, or an existing AWS profile name.

### Google Cloud Storage

Grant the service account a role such as **Storage Object Admin** scoped to the bucket (or a custom role with `storage.objects.list`, `storage.objects.create`, `storage.objects.delete` for the probe). Point the UI at a service-account JSON file, or use Application Default Credentials.

### Azure Blob Storage

Assign **Storage Blob Data Contributor** on the container (or a narrower custom role with read/list/write). Paste a connection string, or account name + key. The “bucket” field is the **container** name.

## Tests

```powershell
python -m pytest
```

Unit tests cover filters, object-key mapping, incremental skip/upload decisions, and the engine against a fake backend (including “local delete does not remove the cloud object”).

Optional live integration (not run by default): configure a real test prefix and use **Test connection** in the UI.

## Packaging (PyInstaller)

After `pip install pyinstaller`:

```powershell
pyinstaller --noconfirm --windowed --name FolderBackup --collect-all customtkinter src/folderbackup/__main__.py
```

A one-folder build is easier on Windows than `--onefile` (faster start, fewer AV false positives). The frozen exe accepts `--run-once` the same way; the Schedule tab registers `FolderBackup.exe --run-once` when running frozen.

## Behavior notes

- Incremental compare: size + mtime first; if those differ, a content fingerprint (full SHA-256 under 32 MB, otherwise first+last 64 KB plus size) avoids re-uploading touch-only files.
- Crash safety: files are marked `in_progress` before upload and retried on the next run.
- Locked/open files (sharing violation) are skipped and retried later.
- OneDrive online-only placeholders are skipped by default.
- Empty folders are not uploaded.
- Directory junctions are not followed unless you enable that option.
- Paths longer than 260 characters use `\\?\` long-path prefixes when opening files.

## Out of scope (v1)

Bidirectional sync, restore UI, client-side encryption, and multi-machine sharing of the same catalog.
