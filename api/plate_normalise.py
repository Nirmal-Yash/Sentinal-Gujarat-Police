"""Canonical plate normalization contract for API boundaries."""
from __future__ import annotations
import re

NORMALIZATION_VERSION = "1.1"


def normalize_plate(value: str | None) -> str | None:
    normalized = re.sub(r"[^A-Z0-9]", "", (value or "").upper())
    return normalized or None
