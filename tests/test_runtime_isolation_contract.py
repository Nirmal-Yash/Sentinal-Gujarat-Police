from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]

def test_test_session_persistence_is_route_independent():
    source=(ROOT/"dashboard/src/App.jsx").read_text(encoding="utf-8")
    assert "useState(Boolean(storedTestSessionId))" in source
    assert "!storedTestSessionId" in source
    assert "path===''/test'" not in source

def test_production_ingestion_continues_during_test_mode():
    source=(ROOT/"ingestion/worker.py").read_text(encoding="utf-8")
    assert "stop_production_workers(procs)" not in source or "production service itself is shutting down" in source
    assert 'STREAM_KEY = "raw_frames"' in source

def test_person_photo_worker_errors_are_explicit():
    watch=(ROOT/"api/routes/watchlist.py").read_text(encoding="utf-8")
    worker=(ROOT/"ai_engine/person_investigation_worker.py").read_text(encoding="utf-8")
    assert "Person analysis worker did not return a result" in watch
    assert "embeddings" in worker
    assert "face_count" in worker
