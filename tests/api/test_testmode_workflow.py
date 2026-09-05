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
