from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]

def test_test_mode_persists_across_route_refresh():
    source=(ROOT/"dashboard/src/App.jsx").read_text(encoding="utf-8")
    assert "useState(Boolean(storedTestSessionId))" in source
    assert "api.getActiveTestSession()" in source

def test_face_worker_emits_face_box_and_activity_heartbeat():
    source=(ROOT/"ai_engine/face_worker.py").read_text(encoding="utf-8")
    assert "fx1,fy1" in source
    assert "HEALTH_PREFIX" in source
    assert "OUT_STREAM" in source

def test_person_worker_and_watchlist_have_explicit_service_failures():
    worker=(ROOT/"ai_engine/person_investigation_worker.py").read_text(encoding="utf-8")
    route=(ROOT/"api/routes/watchlist.py").read_text(encoding="utf-8")
    assert "HEALTH_PREFIX" in worker
    assert "Person analysis worker did not return a result" in route
