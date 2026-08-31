#!/usr/bin/env python3
"""Deterministic P1 contract/regression tests with no live CCTV dependency."""
from __future__ import annotations

import importlib.util
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
for rel in ("ai_engine", "intelligence", "api"):
    sys.path.insert(0, str(ROOT / rel))

from anpr_policy import TrackANPRState, PlateObservation  # type: ignore
from behavior_policy import AdaptiveBaseline  # type: ignore
from alert_engine import AlertEngine  # type: ignore


def load_exact(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    if not spec or not spec.loader:
        raise RuntimeError(f"Unable to load {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def check(condition, message):
    if not condition:
        raise AssertionError(message)
    print(f"[OK] {message}")


def main() -> int:
    ai_plate = load_exact(ROOT / "ai_engine" / "plate_normalise.py", "p1_ai_plate")
    intel_plate = load_exact(ROOT / "intelligence" / "plate_normalise.py", "p1_intel_plate")
    api_plate = load_exact(ROOT / "api" / "plate_normalise.py", "p1_api_plate")
    sample = [" gj 01-ab.1234 ", "GJ01AB1234", "gj-01 ab 1234"]
    outputs = [m.normalize_plate(value) for m in (ai_plate, intel_plate, api_plate) for value in sample]
    check(all(value == "GJ01AB1234" for value in outputs), "API/AI/intelligence plate normalization is identical")

    state = TrackANPRState(window_size=5)
    observation = PlateObservation("GJ01AB1234", .95, .95, .95, True, 1.0)
    for _ in range(4):
        state.add(observation)
    check(state.consensus(5)[0] is None, "ANPR requires configured vote threshold")
    state.add(observation)
    check(state.consensus(5)[0] == "GJ01AB1234", "ANPR promotes exact five-observation consensus")

    baseline = AdaptiveBaseline(alpha=.01, sigma=2.0, minimum_flow=3.0, warmup_seconds=2.0, persistence_seconds=2.0, cooldown_seconds=10.0, running_delta=10.0)
    for t in (0.0, 1.0, 2.0, 3.0):
        baseline.update(5.0, t)
    for t in (4.0, 5.0):
        anomaly, _, _ = baseline.update(5.0, t)
        check(anomaly is None, "Stable public-road movement remains below adaptive crowd baseline")
    anomaly = None
    for t in (6.0, 7.0, 8.0):
        anomaly, _, _ = baseline.update(18.0, t)
    check(anomaly in {"crowd_formation", "running_crowd"}, "Sustained deviation above baseline raises crowd anomaly")

    engine = AlertEngine()
    a = engine._dedup_key({"cam_id": "cam01", "alert_type": "crowd_formation", "detection_id": "a"})
    b = engine._dedup_key({"cam_id": "cam01", "alert_type": "crowd_formation", "detection_id": "b"})
    c = engine._dedup_key({"cam_id": "cam01", "alert_type": "watchlist_match", "details": {"plate_text": "gj 01-ab 1234"}, "detection_id": "c"})
    d = engine._dedup_key({"cam_id": "cam01", "alert_type": "watchlist_match", "details": {"plate_text": "GJ01AB1234"}, "detection_id": "d"})
    check(a == b, "Anomaly dedup key is stable across detection IDs")
    check(c == d, "Plate dedup key is stable across OCR formatting")

    search_text = (ROOT / "api" / "routes" / "search.py").read_text(encoding="utf-8")
    client_text = (ROOT / "dashboard" / "src" / "api" / "client.js").read_text(encoding="utf-8")
    check("X-Test-Session-Id" in search_text, "Person investigation API accepts test-session scope")
    check("X-Test-Session-Id" in client_text, "Dashboard propagates test-session scope")
    migration = (ROOT / "database" / "migrations" / "013_p1_intelligence_consistency.sql").read_text(encoding="utf-8")
    check("test_tracks" in migration and "vector(512)" in migration, "P1 isolated face embedding schema exists")
    watchlist = (ROOT / "intelligence" / "watchlist_engine.py").read_text(encoding="utf-8")
    check("watchlist:updated" in watchlist and "WATCHLIST_RELOAD_SECS" in watchlist, "Watchlist is event-driven with periodic fallback")
    behavior = (ROOT / "ai_engine" / "behavior_worker.py").read_text(encoding="utf-8")
    check("AdaptiveBaseline" in behavior and "CROWD_PERSISTENCE_SECS" in behavior, "Behavior worker uses adaptive baseline and persistence")
    compose = (ROOT / "docker-compose.yml").read_text(encoding="utf-8")
    for token in ("ANPR_VOTE_THRESHOLD", "ANPR_VOTE_WINDOW_FRAMES", "WATCHLIST_RELOAD_SECS", "ALERT_DEDUP_PREFIX", "CROWD_BASELINE_ALPHA", "CROWD_PERSISTENCE_SECS"):
        check(token in compose, f"Compose exposes P1 setting: {token}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
