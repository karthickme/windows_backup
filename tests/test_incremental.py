from folderbackup.core.catalog import STATUS_IN_PROGRESS, CatalogRow
from folderbackup.core.incremental import evaluate_file


def _row(**kwargs) -> CatalogRow:
    data = dict(
        local_path="C:/a.txt",
        size=10,
        mtime_ns=100,
        content_hash="abc",
        remote_key="p/a.txt",
        remote_etag="etag",
        status="ok",
        last_error=None,
        updated_at="now",
    )
    data.update(kwargs)
    return CatalogRow(**data)


def test_new_file_uploads():
    d = evaluate_file(size=10, mtime_ns=1, row=None)
    assert d.action == "upload"
    assert d.reason == "new-file"


def test_unchanged_size_mtime_skips():
    d = evaluate_file(size=10, mtime_ns=100, row=_row())
    assert d.action == "skip"


def test_mtime_change_needs_hash():
    d = evaluate_file(size=10, mtime_ns=200, row=_row())
    assert d.action == "need_hash"


def test_hash_match_skips_touch():
    d = evaluate_file(size=10, mtime_ns=200, row=_row(), content_hash="abc")
    assert d.action == "skip_touch"


def test_hash_mismatch_uploads():
    d = evaluate_file(size=11, mtime_ns=200, row=_row(), content_hash="zzz")
    assert d.action == "upload"


def test_in_progress_retries():
    d = evaluate_file(size=10, mtime_ns=100, row=_row(status=STATUS_IN_PROGRESS))
    assert d.action == "upload"
    assert d.reason == "retry-in-progress"
