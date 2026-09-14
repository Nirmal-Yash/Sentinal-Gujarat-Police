"""Shared input validators for API boundaries."""
from __future__ import annotations

import re

from plate_normalise import normalize_plate

INDIAN_PLATE_RE = re.compile(r"^[A-Z]{2}[0-9]{1,2}[A-Z]{1,3}[0-9]{1,4}$")
CAMERA_LABEL_RE = re.compile(r"^[A-Za-z0-9 ,.\-]{2,255}$")
USERNAME_RE = re.compile(r"^[a-zA-Z0-9_.-]{3,64}$")


def is_valid_indian_plate(value: str | None) -> bool:
    normalized = normalize_plate(value)
    return bool(normalized and INDIAN_PLATE_RE.fullmatch(normalized))


def require_valid_plate(value: str | None, *, required: bool = True) -> str:
    normalized = normalize_plate(value)
    if not normalized:
        if required:
            raise ValueError("A valid plate number is required")
        return ""
    if not INDIAN_PLATE_RE.fullmatch(normalized):
        raise ValueError("Plate must match Indian format, e.g. GJ01AB1234")
    return normalized


def is_valid_camera_label(value: str | None) -> bool:
    text = str(value or "").strip()
    return bool(text and CAMERA_LABEL_RE.fullmatch(text))


def is_valid_username(value: str | None) -> bool:
    text = str(value or "").strip()
    return bool(text and USERNAME_RE.fullmatch(text))
