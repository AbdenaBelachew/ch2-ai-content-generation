"""Hashing utilities for deterministic caching."""

import hashlib
import json
from pathlib import Path
from typing import Any


def hash_text(text: str) -> str:
    """Return SHA-256 hash of a text string."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def hash_data(data: Any) -> str:
    """Return SHA-256 hash of JSON-serializable data."""
    serialized = json.dumps(data, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def hash_file(file_path: str | Path) -> str:
    """Return SHA-256 hash of file contents. If file does not exist, return empty hash."""
    path = Path(file_path)
    if not path.is_file():
        return ""
    hasher = hashlib.sha256()
    with path.open("rb") as f:
        while chunk := f.read(65536):
            hasher.update(chunk)
    return hasher.hexdigest()

