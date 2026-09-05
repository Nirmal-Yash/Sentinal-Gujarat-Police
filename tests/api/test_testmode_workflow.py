# existing test file unavailable

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

def test_test_feed_api_exposes_dynamic_lifecycle_operations():
    source = (ROOT / "api" / "routes" / "test.py").read_text(encoding="utf-8")
    assert '@router.post("/sessions/{session_id}/feeds"' in source
    assert '@router.delete("/sessions/{session_id}/feeds/{stream_id}")' in source
    assert '@router.delete("/assets/{asset_id}")' in source
    assert "production_data_affected" in source

def test_test_runner_reconciles_active_feeds_without_restarting_production_services():
    source = (ROOT / "ingestion" / "test_runner.py").read_text(encoding="utf-8")
    assert 'decode_responses=True' in source
    assert "test:remove_feed:{session_id}:*" in source
    assert "SELECT f.stream_id,a.storage_key,f.loop" in source
    assert "def _start_feed(session_id, row, conn, publishers, feeds):" in source
    assert "while running:" in source

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

def test_test_alerts_are_read_and_operated_with_capabilities():
    source = (ROOT / "api" / "routes" / "test_alerts.py").read_text(encoding="utf-8")
    assert '@router.get("/{session_id}/alerts")' in source
    assert '@router.get("/{session_id}/alerts/counts")' in source
    assert 'require_permission("alert:read")' in source
    assert 'require_permission("alert:operate")' in source
    assert "WHERE session_id=CAST(:session_id AS uuid)" in source

def test_dashboard_uses_isolated_test_alert_endpoint():
    client = (ROOT / "dashboard" / "src" / "api" / "client.js").read_text(encoding="utf-8")
    workspace = (ROOT / "dashboard" / "src" / "components" / "AlertWorkspace.jsx").read_text(encoding="utf-8")
    app = (ROOT / "dashboard" / "src" / "App.jsx").read_text(encoding="utf-8")
    assert "getTestAlerts:" in client
    assert "getTestAlertCounts:" in client
    assert "testMode&&testSession?.id?await api.getTestAlerts" in workspace
    assert "testMode={testMode} testSession={testSession}" in app
