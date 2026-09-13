from folderbackup.core.keys import local_path_to_key, normalize_prefix


def test_windows_drive_key():
    key = local_path_to_key(r"C:\Users\you\Documents\report.pdf", "laptop-backup")
    assert key == "laptop-backup/C/Users/you/Documents/report.pdf"


def test_empty_prefix():
    key = local_path_to_key(r"D:\photos\cat.jpg", "")
    assert key == "D/photos/cat.jpg"


def test_strips_long_path_prefix():
    key = local_path_to_key(r"\\?\C:\Users\you\file.txt", "p")
    assert key == "p/C/Users/you/file.txt"


def test_unc_path():
    key = local_path_to_key(r"\\server\share\docs\a.txt", "backup")
    assert key.startswith("backup/_unc/")
    assert "server" in key
    assert key.endswith("docs/a.txt") or key.endswith("a.txt")


def test_normalize_prefix():
    assert normalize_prefix("\\foo\\bar\\") == "foo/bar"
