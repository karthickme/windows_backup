"""Engine integration against a fake backend: skip unchanged, no remote deletes."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from folderbackup.cloud.base import ConnectionTestResult, UploadResult
from folderbackup.config.settings import AppSettings, CloudSettings, EngineSettings, FilterSettings
from folderbackup.core.catalog import STATUS_LOCAL_MISSING, Catalog
from folderbackup.core.engine import BackupEngine
from folderbackup.core.keys import local_path_to_key


@dataclass
class FakeBackend:
    uploaded: list[str] = field(default_factory=list)
    deleted: list[str] = field(default_factory=list)
    store: dict[str, bytes] = field(default_factory=dict)

    def test_connection(self) -> ConnectionTestResult:
        return ConnectionTestResult(True, "ok", True)

    def upload_file(self, local_path: str, key: str, size: int) -> UploadResult:
        data = Path(local_path).read_bytes()
        self.store[key] = data
        self.uploaded.append(key)
        return UploadResult(key=key, etag="etag-" + key, bytes_sent=size)

    def list_prefix(self, max_keys: int = 1) -> list[str]:
        return list(self.store.keys())[:max_keys]

    def delete_object(self, key: str) -> None:
        self.deleted.append(key)
        self.store.pop(key, None)


def _settings(folder: Path) -> AppSettings:
    return AppSettings(
        folders=[str(folder)],
        filters=FilterSettings(use_builtin_excludes=True),
        cloud=CloudSettings(provider="s3", bucket="test", prefix="unit"),
        engine=EngineSettings(workers=1),
    )


def test_uploads_new_then_skips_unchanged(tmp_path: Path):
    src = tmp_path / "src"
    src.mkdir()
    f = src / "note.txt"
    f.write_text("hello", encoding="utf-8")
    catalog = Catalog(tmp_path / "catalog.sqlite")
    backend = FakeBackend()
    engine = BackupEngine(_settings(src), catalog, backend, lock_path=tmp_path / "lock")

    first = engine.run(dry_run=False)
    assert first.status == "ok"
    assert first.files_uploaded == 1
    assert first.files_skipped == 0
    key = local_path_to_key(f, "unit")
    assert key in backend.store

    second = engine.run(dry_run=False)
    assert second.files_uploaded == 0
    assert second.files_skipped == 1
    catalog.close()


def test_dry_run_does_not_write(tmp_path: Path):
    src = tmp_path / "src"
    src.mkdir()
    (src / "a.bin").write_bytes(b"1234")
    catalog = Catalog(tmp_path / "catalog.sqlite")
    backend = FakeBackend()
    engine = BackupEngine(_settings(src), catalog, backend, lock_path=tmp_path / "lock")
    result = engine.run(dry_run=True)
    assert result.files_uploaded == 1
    assert backend.store == {}
    assert catalog.get(str(src / "a.bin")) is None
    catalog.close()


def test_local_delete_does_not_remove_cloud_object(tmp_path: Path):
    src = tmp_path / "src"
    src.mkdir()
    gone = src / "keep-in-cloud.txt"
    gone.write_text("payload", encoding="utf-8")
    catalog = Catalog(tmp_path / "catalog.sqlite")
    backend = FakeBackend()
    engine = BackupEngine(_settings(src), catalog, backend, lock_path=tmp_path / "lock")
    engine.run(dry_run=False)
    key = local_path_to_key(gone, "unit")
    assert key in backend.store

    gone.unlink()
    result = engine.run(dry_run=False)
    assert key in backend.store
    assert backend.deleted == []
    row = catalog.get(str(gone))
    assert row is not None
    assert row.status == STATUS_LOCAL_MISSING
    assert result.local_missing >= 1
    catalog.close()


def test_content_change_reuploads(tmp_path: Path):
    src = tmp_path / "src"
    src.mkdir()
    f = src / "data.txt"
    f.write_text("v1", encoding="utf-8")
    catalog = Catalog(tmp_path / "catalog.sqlite")
    backend = FakeBackend()
    engine = BackupEngine(_settings(src), catalog, backend, lock_path=tmp_path / "lock")
    engine.run(dry_run=False)
    f.write_text("v2-changed", encoding="utf-8")
    result = engine.run(dry_run=False)
    assert result.files_uploaded == 1
    key = local_path_to_key(f, "unit")
    assert backend.store[key] == b"v2-changed"
    catalog.close()


def test_exclude_extension_not_uploaded(tmp_path: Path):
    src = tmp_path / "src"
    src.mkdir()
    (src / "keep.pdf").write_bytes(b"pdf")
    (src / "skip.tmp").write_bytes(b"tmp")
    settings = _settings(src)
    settings.filters.exclude_extensions = [".tmp"]
    catalog = Catalog(tmp_path / "catalog.sqlite")
    backend = FakeBackend()
    engine = BackupEngine(settings, catalog, backend, lock_path=tmp_path / "lock")
    result = engine.run(dry_run=False)
    assert result.files_scanned == 1
    assert result.files_uploaded == 1
    catalog.close()
