#!/usr/bin/env python3
"""Fast, dependency-light regression gates for the enterprise-hardening branch."""
from __future__ import annotations

import importlib.util
import pathlib
import sys
import time

ROOT = pathlib.Path(__file__).resolve().parents[1]
FAILURES: list[str] = []


def require(condition: bool, message: str) -> None:
    if not condition:
        FAILURES.append(message)
        print(f"[FAIL] {message}")
    else:
        print(f"[OK]   {message}")


def load_module(path: pathlib.Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main() -> int:
    ai = load_module(ROOT / "ai_engine" / "anpr_policy.py", "anpr_policy_gate")
    event = load_module(ROOT / "ai_engine" / "event_schema.py", "event_schema_gate")

    required = {"cam_id", "stream_id", "source_ts", "ingested_at", "pts_ms", "session_id"}
    require(required.issubset(set(event.REQUIRED_FRAME_FIELDS)), "canonical frame event contains all mandatory context")
    require(ai.plate_is_valid("GJ01AB1234"), "valid Indian plate is accepted")
    require(not ai.plate_is_valid("NOTAPLATE"), "invalid plate is rejected")

    state = ai.TrackANPRState()
    obs = ai.PlateObservation
    state.add(obs("GJ01AB1234", .95, .9, .95, True, 1.0))
    require(state.consensus(2)[0] is None, "one observation cannot confirm a plate")
    state.add(obs("GJ01AB1234", .93, .9, .94, True, 2.0))
    require(state.consensus(2)[0] == "GJ01AB1234", "repeated agreeing observations confirm a plate")

    conflict = ai.TrackANPRState()
    conflict.add(obs("GJ01AB1234", .99, .95, .95, True, 1.0))
    conflict.add(obs("GJ01AB1238", .99, .95, .95, True, 2.0))
    require(conflict.consensus(2)[0] is None, "conflicting high-confidence OCR is not merged")

    throttle = ai.TrackANPRState()
    require(ai.should_run_ocr(throttle, 1.0, .8), "OCR initially dispatches")
    throttle.last_ocr_at = 1.0
    require(not ai.should_run_ocr(throttle, 1.5, .8), "OCR interval suppresses excessive calls")
    require(ai.should_run_ocr(throttle, 1.81, .8), "OCR resumes after configured interval")

    start = time.perf_counter()
    for _ in range(10_000):
        ai.normalize_indian_plate(" gj 01 ab 1234 ")
        ai.plate_is_valid("GJ01AB1234")
    elapsed = time.perf_counter() - start
    require(elapsed < 2.0, f"ANPR policy path remains lightweight ({elapsed:.3f}s / 10k iterations)")

    require((ROOT / "ingestion" / "worker.py").exists(), "ingestion supervisor path exists")
    require(not (ROOT / "ingestion" / "rtsp_worker.py").exists(), "regression gate does not reference a removed ingestion worker")
    require((ROOT / "database" / "migrations" / "011_vehicle_journey_domain.sql").exists(), "vehicle journey schema migration exists")
    require((ROOT / "database" / "migrations" / "012_runtime_integrity_and_dedup.sql").exists(), "runtime dedup/integrity migration exists")
    require((ROOT / "dashboard" / "package.json").exists(), "dashboard package manifest exists")

    workflow = (ROOT / ".github" / "workflows" / "refactor-regression.yml").read_text(encoding="utf-8")
    require("ingestion/worker.py" in workflow, "CI compiles the actual ingestion supervisor")
    require("npm install --no-audit --no-fund" in workflow, "CI uses the repository's manifest without requiring an absent lockfile")
    require("docker compose config -q" in workflow, "CI validates Compose configuration")

    if FAILURES:
        print(f"\n{len(FAILURES)} refactor gate(s) failed.")
        return 1
    print("\nAll refactor gates passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
