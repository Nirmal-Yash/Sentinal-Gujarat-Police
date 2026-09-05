import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[1]

def read(path):
    return (ROOT / path).read_text(encoding="utf-8")

def test_test_mode_isolation_and_fast_state_contracts():
    app=read("dashboard/src/App.jsx")
    client=read("dashboard/src/api/client.js")
    test_route=read("api/routes/test.py")
    runner=read("ingestion/test_runner.py")
    assert "sanitizeProductionCameras" in app
    assert "PRODUCTION_CAMERAS_KEY" in app and "TEST_CAMERAS_KEY" in app
    assert "getTestState" in client
    assert "@router.get('/assets')" in test_route or '@router.get("/assets")' in test_route
    assert "@router.post('/sessions/{session_id}/feeds'" in test_route or '@router.post("/sessions/{session_id}/feeds"' in test_route
    assert "@router.delete('/assets/{asset_id}')" in test_route or '@router.delete("/assets/{asset_id}")' in test_route
    assert "test:remove_feed:" in runner
    assert "POLL_SECS" in runner

def test_camera_registry_is_rejected_from_test_session_context():
    source=read("api/routes/cameras.py")+read("api/routes/camera_imports.py")
    assert "Camera Registry is production-only; use Test Feed management in Test Mode" in source

def test_face_analysis_uses_test_namespace_when_session_is_supplied():
    source=read("api/routes/search.py")
    worker=read("ai_engine/person_investigation_worker.py")
    assert "test_session_id" in source
    assert "test:" in source
    assert "PREFIX = 'test:' if TEST_MODE else ''" in worker

def test_registry_database_contract_contains_import_audit():
    migrations="".join((ROOT/"database"/"migrations").glob("*.sql").__iter__().__next__().read_text(encoding="utf-8") if False else [])
    source=read("database/migrations/002_registry_onboarding_and_integrity.sql")+read("database/migrations/004_operations_security_and_test_isolation.sql")
    assert "CREATE TABLE IF NOT EXISTS camera_imports" in source
    assert "CREATE TABLE IF NOT EXISTS camera_audit_log" in source
    assert "ADD COLUMN IF NOT EXISTS column_map" in source
