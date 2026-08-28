"""Canonical ANPR policy: track-driven, quality-gated, adaptive OCR and bounded state."""
from __future__ import annotations

from collections import Counter, deque
from dataclasses import dataclass, field
from math import isfinite
from typing import Optional
import re

PLATE_RE = re.compile(r"^[A-Z]{2}\d{2}[A-Z]{1,3}\d{4}$")

@dataclass
class PlateObservation:
    plate: str
    ocr_confidence: float
    detector_confidence: float
    quality: float
    validated: bool
    observed_at: float

@dataclass
class TrackANPRState:
    observations: deque[PlateObservation] = field(default_factory=lambda: deque(maxlen=8))
    status: str = "DETECTED"
    last_ocr_at: float = 0.0
    last_seen_at: float = 0.0
    confirmed_plate: Optional[str] = None
    confirmed_at: Optional[float] = None

    def add(self, observation: PlateObservation) -> None:
        self.observations.append(observation)
        self.last_seen_at = observation.observed_at

    def consensus(self, min_agreements: int = 2):
        """Confirm only on repeated exact normalized plate agreement."""
        valid = [o for o in self.observations if o.validated and o.plate]
        if not valid:
            return None, 0.0
        grouped = {}
        for item in valid:
            score = max(0.0, min(1.0, item.ocr_confidence)) * max(0.0, min(1.0, item.quality))
            grouped.setdefault(item.plate, []).append(score)
        ranked = sorted(grouped.items(), key=lambda pair: (len(pair[1]), sum(pair[1])), reverse=True)
        plate, scores = ranked[0]
        if len(scores) < max(2, min_agreements):
            return None, 0.0
        return plate, min(1.0, sum(scores) / len(scores))


def normalize_indian_plate(value: str | None) -> str | None:
    """Normalize OCR separators/case without guessing character substitutions."""
    raw = re.sub(r"[^A-Z0-9]", "", (value or "").upper())
    return raw or None


def plate_is_valid(value: str | None) -> bool:
    normalized = normalize_indian_plate(value)
    return bool(normalized and PLATE_RE.fullmatch(normalized))


def quality_score(width: int, height: int, blur_score: float = 1.0, brightness: float = 0.5) -> float:
    """Bounded lightweight quality score for OCR keyframe selection."""
    if width <= 0 or height <= 0:
        return 0.0
    size = min(1.0, (width * height) / (220 * 80))
    blur = max(0.0, min(1.0, blur_score))
    light = max(0.0, min(1.0, 1.0 - abs(brightness - 0.5) * 2.0))
    score = 0.55 * size + 0.30 * blur + 0.15 * light
    return score if isfinite(score) else 0.0


def should_run_ocr(state: TrackANPRState, now: float, min_interval: float = 0.8) -> bool:
    """Adaptive OCR trigger; confirmed tracks are not reprocessed."""
    if state.confirmed_plate:
        return False
    return (now - state.last_ocr_at) >= max(0.2, min_interval)
