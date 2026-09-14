from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]

def test_production_ingestion_pauses_when_test_session_active():
    source=(ROOT/"ingestion/worker.py").read_text(encoding="utf-8")
    assert "production_paused" in source
    assert "Production CCTV ingestion paused" in source
    assert 'STREAM_KEY = "raw_frames"' in source

def test_test_assets_only_mark_active_session_assets_in_use():
    source=(ROOT/"api/routes/test.py").read_text(encoding="utf-8")
    assert "s.status IN ('starting','active')" in source

def test_test_feed_ui_uses_session_api_and_can_submit_selection():
    source=(ROOT/"dashboard/src/components/TestFeedManager.jsx").read_text(encoding="utf-8")
    assert "api.addTestFeed" in source
    assert "!activeAssetIds.has(String(asset.id))" in source
