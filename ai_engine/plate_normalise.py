"""Single canonical ANPR plate normalization contract for the AI service."""
from __future__ import annotations
import re

NORMALIZATION_VERSION = "1.1"
PLATE_RE = re.compile(r"^[A-Z]{2}\d{2}[A-Z]{1,3}\d{4}$")


def normalize_plate(value: str | None) -> str | None:
    """Uppercase and remove separators/non-alphanumeric characters; never guess OCR glyphs."""
    normalized = re.sub(r"[^A-Z0-9]", "", (value or "").upper())
    return normalized or None


def is_valid_indian_plate(value: str | None) -> bool:
    normalized = normalize_plate(value)
    return bool(normalized and PLATE_RE.fullmatch(normalized))
