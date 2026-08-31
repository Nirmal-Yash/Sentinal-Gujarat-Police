"""Deterministic adaptive anomaly policy independent of OpenCV/Redis."""
from __future__ import annotations
from dataclasses import dataclass


@dataclass
class AdaptiveBaseline:
    alpha: float = 0.04
    sigma: float = 3.0
    minimum_flow: float = 3.5
    warmup_seconds: float = 30.0
    persistence_seconds: float = 5.0
    cooldown_seconds: float = 60.0
    running_delta: float = 6.0
    mean: float | None = None
    variance: float = 0.0
    started_at: float | None = None
    candidate_since: float | None = None
    cooldown_until: float = 0.0

    def reset(self) -> None:
        self.mean = None
        self.variance = 0.0
        self.started_at = None
        self.candidate_since = None
        self.cooldown_until = 0.0

    @property
    def std(self) -> float:
        return max(0.5, self.variance ** 0.5)

    def update(self, value: float, now: float) -> tuple[str | None, float, bool]:
        value = max(0.0, float(value))
        if self.started_at is None:
            self.started_at = now
        if self.mean is None:
            self.mean = value
            return None, 0.0, True
        delta = value - self.mean
        deviation = max(0.0, delta)
        warmed = (now - self.started_at) >= max(1.0, self.warmup_seconds)
        if not warmed:
            self.mean = self.mean + self.alpha * delta
            self.variance = (1.0 - self.alpha) * (self.variance + self.alpha * delta * delta)
            return None, deviation, False
        crowd_limit = max(self.minimum_flow, self.mean + max(0.8, self.sigma * self.std))
        running_limit = max(self.minimum_flow + 1.0, self.mean + self.running_delta)
        candidate = value >= crowd_limit
        if candidate:
            if self.candidate_since is None:
                self.candidate_since = now
        else:
            self.candidate_since = None
        anomaly = None
        if now >= self.cooldown_until and self.candidate_since is not None and now - self.candidate_since >= self.persistence_seconds:
            anomaly = "running_crowd" if value >= running_limit else "crowd_formation"
            score = min(1.0, max(0.0, (value - self.mean) / max(1.0, self.running_delta if anomaly == "running_crowd" else self.sigma * self.std)))
            self.cooldown_until = now + self.cooldown_seconds
            self.candidate_since = None
        else:
            score = 0.0
        self.mean = self.mean + self.alpha * delta
        self.variance = (1.0 - self.alpha) * (self.variance + self.alpha * delta * delta)
        return anomaly, score, False
