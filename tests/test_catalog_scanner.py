from pathlib import Path

from folderbackup.config.settings import AppSettings, CloudSettings, FilterSettings, validate_settings
from folderbackup.core.catalog import Catalog
from folderbackup.core.hashing import content_fingerprint
from folderbackup.core.scanner import iter_source_files


def test_catalog_roundtrip(tmp_path: Path):
    cat = Catalog(tmp_path / "c.sqlite")
    cat.upsert_ok(
        "C:/a.txt",
        size=3,
        mtime_ns=9,
        content_hash="h",
        remote_key="p/a.txt",
        remote_etag="e",
    )
    row = cat.get("C:/a.txt")
    assert row is not None
    assert row.size == 3
    run_id = cat.start_run(dry_run=False)
    cat.finish_run(
        run_id,
        files_scanned=1,
        files_uploaded=1,
        files_skipped=0,
        files_failed=0,
        bytes_uploaded=3,
        status="ok",
    )
    runs = cat.latest_runs()
    assert runs[0].status == "ok"
    cat.close()


def test_fingerprint_full_and_sample(tmp_path: Path):
    small = tmp_path / "small.bin"
    small.write_bytes(b"abc")
    assert len(content_fingerprint(small, 3, full_under_bytes=10)) == 64
    big = tmp_path / "big.bin"
    data = b"x" * 200_000
    big.write_bytes(data)
    digest = content_fingerprint(big, len(data), full_under_bytes=100)
    again = content_fingerprint(big, len(data), full_under_bytes=100)
    assert digest == again


def test_scanner_skips_excluded_dir(tmp_path: Path):
    root = tmp_path / "tree"
    (root / "keep").mkdir(parents=True)
    (root / "node_modules").mkdir()
    (root / "keep" / "a.txt").write_text("ok")
    (root / "node_modules" / "pkg.js").write_text("nope")
    settings = AppSettings(folders=[str(root)], filters=FilterSettings())
    jobs = list(iter_source_files(settings))
    names = [Path(j.local_path).name for j in jobs]
    assert "a.txt" in names
    assert "pkg.js" not in names


def test_validate_requires_folder_and_bucket(tmp_path: Path):
    missing = AppSettings(folders=[], cloud=CloudSettings(bucket=""))
    errors = validate_settings(missing)
    assert any("folder" in e.lower() for e in errors)
    folder = tmp_path / "d"
    folder.mkdir()
    ok = AppSettings(folders=[str(folder)], cloud=CloudSettings(bucket="bkt"))
    assert validate_settings(ok) == []
