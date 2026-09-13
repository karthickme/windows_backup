from folderbackup.config.settings import dest_visible_fields


def test_s3_shows_aws_fields_only():
    fields = dest_visible_fields("s3")
    assert "s3_key" in fields
    assert "gcs_path" not in fields
    assert "azure_conn" not in fields


def test_gcs_shows_json_path_only():
    fields = dest_visible_fields("gcs")
    assert fields == {"bucket", "prefix", "gcs_path"}


def test_azure_shows_azure_fields_only():
    fields = dest_visible_fields("azure")
    assert "azure_account" in fields
    assert "azure_key" in fields
    assert "azure_conn" in fields
    assert "s3_key" not in fields
    assert "gcs_path" not in fields
    assert "bucket" in fields
    assert "prefix" in fields
