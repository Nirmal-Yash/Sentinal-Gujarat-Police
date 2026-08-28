#!/usr/bin/env python3
"""Fast, dependency-light regression gates for the enterprise-hardening branch."""
from __future__ import annotations

import pathlib
import sys
import time

ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from ai_engine import anpr_policy as ai
from ai_engine import event_schema as event

FAILURES: list[str] = []


def require(condition: bool, message: str) -> None:
    if not condition:
        FAILURES.append(message)
        print(f"[FAIL] {message}")
    else:
        print(f"[OK]   {message}")


def main() -> int:
    required = {"cam_id", "stream_id", "source_ts", "ingested_at", "pts_ms", "session_id"}
    require(required.issubset(set(event.REQUIRED_FRAME_FIELDS)), "canonical frame event contains all mandatory context")
    require(ai.plate_is_valid("GJ01AB1234"), "valid Indian plate is accepted")
    require(not ai.plate_is_valid("NOTAPLATE"), "invalid plate is rejected")

    state = ai.TrackANPRState(); obs = ai.PlateObservation
    state.add(obs("GJ01AB1234", .95, .9, .95, True, 1.0)); require(state.consensus(2)[0] is None, "one observation cannot confirm a plate")
    state.add(obs("GJ01AB1234", .93, .9, .94, True, 2.0)); require(state.consensus(2)[0] == "GJ01AB1234", "repeated agreeing observations confirm a plate")

    conflict = ai.TrackANPRState(); conflict.add(obs("GJ01AB1234", .99, .95, .95, True, 1.0)); conflict.add(obs("GJ01AB1238", .99, .95, .95, True, 2.0)); require(conflict.consensus(2)[0] is None, "conflicting high-confidence OCR is not merged")

    throttle = ai.TrackANPRState(); require(ai.should_run_ocr(throttle, 1.0, .8), "OCR initially dispatches"); throttle.last_ocr_at = 1.0; require(not ai.should_run_ocr(throttle, 1.5, .8), "OCR interval suppresses excessive calls"); require(ai.should_run_ocr(throttle, 1.81, .8), "OCR resumes after configured interval")

    start = time.perf_counter()
    for _ in range(10_000): ai.normalize_indian_plate(" gj 01 ab 1234 "); ai.plate_is_valid("GJ01AB1234")
    elapsed = time.perf_counter() - start; require(elapsed < 2.0, f"ANPR policy path remains lightweight ({elapsed:.3f}s / 10k iterations)")

    require((ROOT / "ingestion" / "worker.py").exists(), "ingestion supervisor path exists")
    require((ROOT / "database" / "migrations" / "010_alert_lifecycle_and_evidence.sql").exists(), "alert lifecycle and evidence schema exists")
    require((ROOT / "database" / "migrations" / "011_vehicle_journey_domain.sql").exists(), "vehicle journey schema migration exists")
    require((ROOT / "database" / "migrations" / "012_runtime_integrity_and_dedup.sql").exists(), "runtime dedup/integrity migration exists")
    require((ROOT / "api" / "routes" / "evidence.py").exists(), "evidence API exists")
    require((ROOT / "dashboard" / "src" / "components" / "AlertPanel.jsx").exists(), "operational alert UI exists")
    require((ROOT / "dashboard" / "src" / "components" / "MapView.jsx").exists(), "operational GIS UI exists")

    alerts_source = (ROOT / "api" / "routes" / "alerts.py").read_text(encoding="utf-8")
    for fragment, message in [
        ('"NEW": {"ACKNOWLEDGED"}', "NEW alert has a safe acknowledgement transition"),
        ('"ACKNOWLEDGED": {"INVESTIGATING", "RESOLVED"}', "acknowledged alert supports investigation/resolution"),
        ('"INVESTIGATING": {"RESOLVED"}', "investigating alert resolves only after investigation"),
        ('"RESOLVED": {"CLOSED"}', "resolved alert can be closed"),
        ('"CLOSED": set()', "closed alert is terminal"),
        ('alert_status_changed', "alert status transitions have a realtime event type"),
    ]:
        require(fragment in alerts_source, message)

    workflow = (ROOT / ".github" / "workflows" / "refactor-regression.yml").read_text(encoding="utf-8")
    require("ingestion/worker.py" in workflow, "CI compiles the actual ingestion supervisor")
    require("api/routes/evidence.py" in workflow, "CI compiles the evidence API")
    require("scripts/p0_runtime_e2e.py" in workflow, "CI executes P0 runtime data-plane E2E")
    require("scripts/anpr_benchmark.py" in workflow, "CI executes the ANPR benchmark harness")
    require("npm run build" in workflow, "CI executes dashboard production build")
    require("docker compose config -q" in workflow, "CI validates Compose configuration")

    if FAILURES:
        print(f"\n{len(FAILURES)} refactor gate(s) failed."); return 1
    print("\nAll refactor gates passed."); return 0

if __name__ == "__main__": sys.exit(main())
