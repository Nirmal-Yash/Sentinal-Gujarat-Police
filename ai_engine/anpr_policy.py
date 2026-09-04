"""Canonical ANPR policy: quality-gated OCR, exact consensus and bounded state."""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from math import isfinite
from typing import Optional

try:
    from .plate_normalise import normalize_plate, is_valid_indian_plate
except ImportError:
    from plate_normalise import normalize_plate, is_valid_indian_plate


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
    """Bounded ANPR state; consensus is measured against wall-clock time."""
    window_seconds: float = 8.0
    first_seen_at: float = 0.0
    observations: deque[PlateObservation] = field(default_factory=deque)
    status: str = "DETECTED"
    last_ocr_at: float = 0.0
    last_seen_at: float = 0.0
    confirmed_plate: Optional[str] = None
    confirmed_at: Optional[float] = None
    window_size: Optional[int] = None

    def __post_init__(self):
        self.window_seconds = max(1.0, float(self.window_seconds))
        self.observations = deque(self.observations, maxlen=max(8, int(self.window_size or 32)))

    def add(self, observation: PlateObservation) -> None:
        if not self.first_seen_at:
            self.first_seen_at = observation.observed_at
        self.observations.append(observation)
        self.last_seen_at = observation.observed_at

    def consensus(self, min_agreements: int = 2, now: Optional[float] = None):
        required = max(2, int(min_agreements))
        current = self.last_seen_at if now is None else now
        valid = [o for o in self.observations
                 if o.validated and o.plate and o.observed_at >= current - self.window_seconds]
        if not valid:
            return None, 0.0
        grouped: dict[str, list[float]] = {}
        for item in valid:
            score = max(0.0, min(1.0, item.ocr_confidence)) * max(0.0, min(1.0, item.quality))
            grouped.setdefault(item.plate, []).append(score)
        plate, scores = sorted(
            grouped.items(),
            key=lambda pair: (len(pair[1]), sum(pair[1])),
            reverse=True,
        )[0]
        if len(scores) < required:
            return None, 0.0
        return plate, min(1.0, sum(scores) / len(scores))


def normalize_indian_plate(value: str | None) -> str | None:
    return normalize_plate(value)


def plate_is_valid(value: str | None) -> bool:
    return is_valid_indian_plate(value)


def quality_score(width: int, height: int, blur_score: float = 1.0, brightness: float = 0.5) -> float:
    if width <= 0 or height <= 0:
        return 0.0
    size = min(1.0, (width * height) / (220 * 80))
    blur = max(0.0, min(1.0, blur_score))
    light = max(0.0, min(1.0, 1.0 - abs(brightness - 0.5) * 2.0))
    score = 0.55 * size + 0.30 * blur + 0.15 * light
    return score if isfinite(score) else 0.0


def should_run_ocr(state: TrackANPRState, now: float, min_interval: float = 1.5, min_track_age: float = 1.5) -> bool:
    if state.confirmed_plate:
        return False
    if state.first_seen_at and (now - state.first_seen_at) < max(0.0, min_track_age):
        return False
    return (now - state.last_ocr_at) >= max(0.2, min_interval)
