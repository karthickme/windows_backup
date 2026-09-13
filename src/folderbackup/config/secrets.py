"""Windows Credential Manager (keyring) secret storage. Never write secrets to YAML."""

from __future__ import annotations

from dataclasses import dataclass

import keyring
from keyring.errors import PasswordDeleteError

SERVICE = "FolderBackup"

S3_ACCESS_KEY = "s3_access_key_id"
S3_SECRET_KEY = "s3_secret_access_key"
AZURE_CONNECTION_STRING = "azure_connection_string"
AZURE_ACCOUNT_KEY = "azure_account_key"


@dataclass
class Secrets:
    s3_access_key_id: str = ""
    s3_secret_access_key: str = ""
    azure_connection_string: str = ""
    azure_account_key: str = ""


def get_secret(name: str) -> str:
    try:
        return keyring.get_password(SERVICE, name) or ""
    except Exception:
        return ""


def set_secret(name: str, value: str) -> None:
    value = (value or "").strip()
    if not value:
        try:
            keyring.delete_password(SERVICE, name)
        except PasswordDeleteError:
            pass
        except Exception:
            pass
        return
    keyring.set_password(SERVICE, name, value)


def load_secrets() -> Secrets:
    return Secrets(
        s3_access_key_id=get_secret(S3_ACCESS_KEY),
        s3_secret_access_key=get_secret(S3_SECRET_KEY),
        azure_connection_string=get_secret(AZURE_CONNECTION_STRING),
        azure_account_key=get_secret(AZURE_ACCOUNT_KEY),
    )


def save_secrets(secrets: Secrets) -> None:
    set_secret(S3_ACCESS_KEY, secrets.s3_access_key_id)
    set_secret(S3_SECRET_KEY, secrets.s3_secret_access_key)
    set_secret(AZURE_CONNECTION_STRING, secrets.azure_connection_string)
    set_secret(AZURE_ACCOUNT_KEY, secrets.azure_account_key)


def credentials_present(
    provider: str,
    secrets: Secrets,
    *,
    aws_profile: str = "",
    gcs_path: str = "",
    azure_account: str = "",
) -> bool:
    provider = provider.lower()
    if provider == "s3":
        keys = bool(secrets.s3_access_key_id and secrets.s3_secret_access_key)
        return keys or bool(aws_profile.strip())
    if provider == "gcs":
        _ = gcs_path
        return True  # ADC is allowed even without a JSON path
    if provider == "azure":
        if secrets.azure_connection_string.strip():
            return True
        return bool(azure_account.strip() and secrets.azure_account_key.strip())
    return False
