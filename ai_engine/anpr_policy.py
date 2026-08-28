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

    def consensus(self, min_agreements: int = 2, max_edit_distance: int = 1):
        """Return (plate, score) only when evidence is sufficiently consistent."""
        if not self.observations:
            return None, 0.0
        scores = Counter()
        best = {}
        for item in self.observations:
            if not item.plate:
                continue
            score = max(0.0, min(1.0, item.ocr_confidence)) * max(0.0, min(1.0, item.quality))
            scores[item.plate] += score
            best[item.plate] = max(best.get(item.plate, 0.0), score)
        if not scores:
            return None, 0.0
        plate, score = scores.most_common(1)[0]
        exact = sum(1 for item in self.observations if item.plate == plate)
        if exact >= min_agreements and score > 0:
            return plate, min(1.0, score / max(1, len(self.observations)))
        # One-character OCR disagreement may still represent the same plate.
        for candidate in scores:
            if _edit_distance(candidate, plate) <= max_edit_distance:
                similar = sum(1 for item in self.observations if _edit_distance(item.plate, plate) <= max_edit_distance)
                if similar >= min_agreements:
                    return plate, min(1.0, (score + best[candidate]) / max(1, len(self.observations)))
        return None, 0.0


def _edit_distance(a: str, b: str) -> int:
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(cur[-1] + 1, prev[j] + 1, prev[j - 1] + (ca != cb)))
        prev = cur
    return prev[-1]


def normalize_indian_plate(value: str | None) -> str | None:
    """Normalize common OCR noise without inventing characters."""
    raw = re.sub(r"[^A-Z0-9]", "", (value or "").upper())
    return raw or None


def plate_is_valid(value: str | None) -> bool:
    normalized = normalize_indian_plate(value)
    return bool(normalized and PLATE_RE.fullmatch(normalized))


def quality_score(width: int, height: int, blur_score: float = 1.0, brightness: float = 0.5) -> float:
    """Lightweight quality gate for choosing OCR keyframes."""
    if width <= 0 or height <= 0:
        return 0.0
    size = min(1.0, (width * height) / (220 * 80))
    blur = max(0.0, min(1.0, blur_score))
    light = max(0.0, min(1.0, 1.0 - abs(brightness - 0.5) * 2.0))
    score = 0.55 * size + 0.30 * blur + 0.15 * light
    return score if isfinite(score) else 0.0


def should_run_ocr(state: TrackANPRState, now: float, min_interval: float = 0.8) -> bool:
    """Adaptive OCR trigger: do not OCR every frame."""
    if state.confirmed_plate:
        return False
    return (now - state.last_ocr_at) >= min_interval
