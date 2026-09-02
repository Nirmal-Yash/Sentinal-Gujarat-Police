from __future__ import annotations

import os
from pathlib import Path
from cryptography.fernet import Fernet

KEY = os.getenv("FIELD_ENCRYPTION_KEY", "").strip()
ENABLED = bool(KEY)
_FERNET = Fernet(KEY.encode()) if KEY else None


def encrypted_path(path: Path) -> Path:
    return path.with_suffix(path.suffix + ".enc")


def write_protected(path: Path, data: bytes) -> Path:
    """Encrypt evidence when a production field-encryption key is configured."""
    if not _FERNET:
        path.write_bytes(data)
        return path
    target = encrypted_path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(_FERNET.encrypt(data))
    return target


def read_protected(path: Path) -> bytes:
    target = encrypted_path(path) if _FERNET and encrypted_path(path).is_file() else path
    data = target.read_bytes()
    return _FERNET.decrypt(data) if _FERNET and target.suffix == ".enc" else data
