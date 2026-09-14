from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]

def test_test_camera_contract_uses_hls_url_and_session_id():
    source=(ROOT/"api/routes/test.py").read_text(encoding="utf-8")
    assert '"hls_url": row["hls_path"]' in source
    assert '"session_id": str(session_id)' in source

def test_camera_player_prefers_test_hls_and_retries_warmup():
    source=(ROOT/"dashboard/src/components/CameraGrid.jsx").read_text(encoding="utf-8")
    assert "if(cam?.is_test)" in source
    assert "hls.startLoad(-1)" in source
    assert "FRAG_BUFFERED" in source

def test_production_ingestion_has_test_mode_pause_branch():
    source=(ROOT/"ingestion/worker.py").read_text(encoding="utf-8")
    assert "Production CCTV ingestion paused" in source
