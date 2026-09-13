"""Stable object-key mapping: {prefix}/{drive-letter}/{relative-posix-path}."""

from __future__ import annotations

from pathlib import Path, PureWindowsPath


def normalize_prefix(prefix: str) -> str:
    return prefix.replace("\\", "/").strip("/")


def local_path_to_key(local_path: str | Path, prefix: str) -> str:
    """Map a local file path to a portable cloud object key.

    Examples:
        C:\\Users\\you\\Documents\\report.pdf + prefix laptop-backup
        -> laptop-backup/C/Users/you/Documents/report.pdf
    """
    prefix = normalize_prefix(prefix)
    raw = str(local_path)
    for marker in ("\\\\?\\UNC\\", "//?/UNC/"):
        if raw.startswith(marker):
            raw = "\\\\" + raw[len(marker) :]
            break
    else:
        for marker in ("\\\\?\\", "//?/"):
            if raw.startswith(marker):
                raw = raw[len(marker) :]
                break

    win = PureWindowsPath(raw)
    drive = win.drive  # 'C:' or '\\\\server\\share'
    parts: list[str] = []
    if prefix:
        parts.append(prefix)

    if len(drive) == 2 and drive[1] == ":":
        parts.append(drive[0].upper())
        rest = [p for p in win.parts[1:] if p not in ("/", "\\")]
        parts.extend(rest)
    elif drive.startswith("\\\\") or drive.startswith("//"):
        parts.append("_unc")
        unc = drive.replace("\\", "/").lstrip("/")
        parts.extend([p for p in unc.split("/") if p])
        rest = [p for p in win.parts[1:] if p not in ("/", "\\")]
        parts.extend(rest)
    else:
        posix = Path(raw).as_posix().lstrip("/")
        parts.extend([p for p in posix.split("/") if p])

    return "/".join(parts)
