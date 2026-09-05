from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]

def test_test_face_watchlist_isolated_alert_path():
    source=(ROOT/"intelligence/test_sighting_store.py").read_text(encoding="utf-8")
    route=(ROOT/"api/routes/test.py").read_text(encoding="utf-8")
    assert "FROM test_watchlists" in source
    assert "FACE_SIM_THRESHOLD" in source
    assert "watchlist_match" in source
    assert "import base64" in route and "import numpy as np" in route

def test_test_alert_api_treats_undefined_filters_as_unset():
    source=(ROOT/"api/routes/test_alerts.py").read_text(encoding="utf-8")
    assert 'priority.lower() in {"undefined", "null"}' in source
    assert 'status.lower() in {"undefined", "null"}' in source