from folderbackup.config.settings import AppSettings, save_settings, load_settings


def test_settings_roundtrip(tmp_path):
    path = tmp_path / "config.yaml"
    settings = AppSettings()
    settings.folders = ["C:\\Data"]
    settings.cloud.bucket = "my-bucket"
    settings.cloud.provider = "gcs"
    save_settings(settings, path)
    loaded = load_settings(path)
    assert loaded.folders == ["C:\\Data"]
    assert loaded.cloud.bucket == "my-bucket"
    assert loaded.cloud.provider == "gcs"
    assert "secret" not in path.read_text(encoding="utf-8").lower()
