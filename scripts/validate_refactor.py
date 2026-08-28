#!/usr/bin/env python3
"""Fast, dependency-light regression gates for the enterprise-hardening branch."""
from __future__ import annotations
import pathlib, sys, time
ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path: sys.path.insert(0, str(ROOT))
from ai_engine import anpr_policy as ai
from ai_engine import event_schema as event
FAILURES: list[str] = []
def require(condition: bool, message: str) -> None:
    if not condition:
        FAILURES.append(message); print(f"[FAIL] {message}")
    else: print(f"[OK]   {message}")
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
    required_paths = [
        ("ingestion/worker.py", "ingestion supervisor path exists"),
        ("database/migrations/010_alert_lifecycle_and_evidence.sql", "alert lifecycle and evidence schema exists"),
        ("database/migrations/011_vehicle_journey_domain.sql", "vehicle journey schema migration exists"),
        ("database/migrations/012_runtime_integrity_and_dedup.sql", "runtime dedup/integrity migration exists"),
        ("database/migrations/016_evidence_and_operational_integrity.sql", "evidence/operational integrity migration exists"),
        ("database/migrations/017_evidence_capture_integrity.sql", "evidence capture integrity migration exists"),
        ("api/routes/evidence.py", "evidence API exists"),
        ("api/routes/operations.py", "operational health API exists"),
        ("intelligence/evidence_capture.py", "alert evidence capture utility exists"),
        ("dashboard/src/components/AlertPanel.jsx", "operational alert UI exists"),
        ("dashboard/src/components/MapView.jsx", "operational GIS UI exists"),
    ]
    for rel, message in required_paths: require((ROOT / rel).exists(), message)
    auth_source = (ROOT / "api/auth.py").read_text(encoding="utf-8")
    for permission in ("camera:read", "camera:write", "alert:operate", "search:read", "report:read", "evidence:read", "evidence:create", "registry:admin", "system:admin"):
        require(permission in auth_source, f"RBAC permission exists: {permission}")
    alerts_source = (ROOT / "api/routes/alerts.py").read_text(encoding="utf-8")
    for fragment, message in [
        ('"NEW": {"ACKNOWLEDGED"}', "NEW alert has a safe acknowledgement transition"),
        ('"ACKNOWLEDGED": {"INVESTIGATING", "RESOLVED"}', "acknowledged alert supports investigation/resolution"),
        ('"INVESTIGATING": {"RESOLVED"}', "investigating alert resolves only after investigation"),
        ('"RESOLVED": {"CLOSED"}', "resolved alert can be closed"),
        ('"CLOSED": set()', "closed alert is terminal"),
        ('alert_status_changed', "alert status transitions have a realtime event type"),
    ]: require(fragment in alerts_source, message)
    operations_source = (ROOT / "api/routes/operations.py").read_text(encoding="utf-8")
    require('"/overview"' in operations_source, "operations overview endpoint exists")
    require("cameras_healthy" in operations_source and "active_journeys" in operations_source, "operations overview exposes fleet and investigation metrics")
    evidence_source = (ROOT / "api/routes/evidence.py").read_text(encoding="utf-8")
    require("evidence:create" in evidence_source and "evidence:read" in evidence_source, "evidence routes enforce permissions")
    require("/{evidence_id}/content" in evidence_source, "evidence content endpoint exists")
    alert_source = (ROOT / "intelligence/alert_engine.py").read_text(encoding="utf-8")
    require("capture_snapshot" in alert_source and "INSERT INTO evidence" in alert_source, "alerts attempt durable snapshot evidence capture")
    compose = (ROOT / "docker-compose.yml").read_text(encoding="utf-8")
    require("evidence_data:/evidence" in compose, "shared durable evidence volume is configured")
    workflow = (ROOT / ".github" / "workflows" / "refactor-regression.yml").read_text(encoding="utf-8")
    for fragment, message in [
        ("ingestion/worker.py", "CI compiles the actual ingestion supervisor"),
        ("intelligence/evidence_capture.py", "CI compiles evidence capture"),
        ("intelligence/test_evidence_capture.py", "CI runs evidence capture regression"),
        ("api/routes/evidence.py", "CI compiles the evidence API"),
        ("api/routes/operations.py", "CI compiles the operations API"),
        ("scripts/p0_runtime_e2e.py", "CI executes P0 runtime data-plane E2E"),
        ("scripts/anpr_benchmark.py", "CI executes the ANPR benchmark harness"),
        ("npm run build", "CI executes dashboard production build"),
        ("docker compose config -q", "CI validates Compose configuration"),
    ]: require(fragment in workflow, message)
    if FAILURES:
        print(f"\n{len(FAILURES)} refactor gate(s) failed."); return 1
    print("\nAll refactor gates passed."); return 0
if __name__ == "__main__": sys.exit(main())
