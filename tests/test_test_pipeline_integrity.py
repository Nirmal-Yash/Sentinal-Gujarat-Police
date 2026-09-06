from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]

def test_test_sighting_store_imports_numpy_for_face_matching():
    source=(ROOT/"intelligence/test_sighting_store.py").read_text(encoding="utf-8")
    assert "import numpy as np" in source

def test_person_investigation_uses_test_session_during_validation():
    source=(ROOT/"dashboard/src/components/InvestigationPanel.jsx").read_text(encoding="utf-8")
    assert "api.validatePersonPhoto(file,testMode&&testSession?.id?testSession.id:undefined)" in source

def test_test_runner_supervises_media_publisher():
    source=(ROOT/"ingestion/test_runner.py").read_text(encoding="utf-8")
    assert "publisher.poll()" in source
    assert "stream_loop" in source
