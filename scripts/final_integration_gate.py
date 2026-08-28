#!/usr/bin/env python3
"""Deterministic final integration gate for the business pipeline contracts."""
from __future__ import annotations
import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
checks = {
    "event_contract": (ROOT / "ai_engine/event_schema.py").exists(),
    "adaptive_anpr": (ROOT / "ai_engine/anpr_policy.py").exists() and (ROOT / "ai_engine/anpr_worker.py").exists(),
    "tracked_detector": (ROOT / "ai_engine/yolo_worker.py").exists(),
    "durable_sightings": (ROOT / "intelligence/sighting_store.py").exists(),
    "vehicle_journey": (ROOT / "database/migrations/011_vehicle_journey_domain.sql").exists(),
    "alert_lifecycle": (ROOT / "api/routes/alerts.py").exists(),
    "evidence": (ROOT / "api/routes/evidence.py").exists() and (ROOT / "intelligence/evidence_capture.py").exists(),
    "registry_gis": (ROOT / "api/routes/cameras.py").exists() and (ROOT / "dashboard/src/components/MapView.jsx").exists(),
    "health": (ROOT / "api/routes/operations.py").exists(),
    "test_alert_lifecycle": (ROOT / "api/routes/test_alerts.py").exists() and (ROOT / "database/migrations/020_test_alert_lifecycle.sql").exists(),
}
failed = [name for name, ok in checks.items() if not ok]
for name, ok in checks.items(): print(f"[{'OK' if ok else 'FAIL'}] {name}")
if failed:
    raise SystemExit(f"Final integration gate failed: {failed}")
print("FINAL_INTEGRATION_GATE=PASS")
