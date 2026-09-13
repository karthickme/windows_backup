"""Unit tests for extension, size, and exclude-dir filters."""

from pathlib import Path

from folderbackup.config.settings import FilterSettings
from folderbackup.core.filters import (
    apply_file_filters,
    parse_ext_list,
    should_skip_dir_name,
)


def test_parse_ext_list_adds_dots_and_lowercases():
    assert parse_ext_list(".PDF, jpg;EXE") == [".pdf", ".jpg", ".exe"]


def test_exclude_wins_over_include():
    settings = FilterSettings(include_extensions=[".pdf", ".tmp"], exclude_extensions=[".tmp"])
    keep = apply_file_filters(Path("doc.pdf"), size=100, settings=settings)
    drop = apply_file_filters(Path("scratch.tmp"), size=100, settings=settings)
    assert keep.include
    assert not drop.include
    assert drop.reason == "exclude-extension"


def test_include_list_rejects_other_types():
    settings = FilterSettings(include_extensions=[".docx"])
    assert apply_file_filters(Path("a.docx"), size=10, settings=settings).include
    assert not apply_file_filters(Path("a.jpg"), size=10, settings=settings).include


def test_size_bounds():
    settings = FilterSettings(min_size_mb=1, max_size_mb=2)
    too_small = apply_file_filters(Path("a.bin"), size=100, settings=settings)
    ok = apply_file_filters(Path("a.bin"), size=1_500_000, settings=settings)
    too_big = apply_file_filters(Path("a.bin"), size=5_000_000, settings=settings)
    assert too_small.reason == "below-min-size"
    assert ok.include
    assert too_big.reason == "above-max-size"


def test_builtin_exclude_dirs_and_files():
    settings = FilterSettings()
    assert should_skip_dir_name("node_modules", settings)
    assert should_skip_dir_name(".git", settings)
    assert not should_skip_dir_name("Documents", settings)
    decision = apply_file_filters(Path("Thumbs.db"), size=20, settings=settings)
    assert not decision.include


def test_extra_exclude_dirs():
    settings = FilterSettings(use_builtin_excludes=False, extra_exclude_dirs=["build"])
    assert should_skip_dir_name("build", settings)
    assert not should_skip_dir_name("node_modules", settings)
