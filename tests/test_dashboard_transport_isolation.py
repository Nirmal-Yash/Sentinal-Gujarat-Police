from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]

def test_test_mode_uses_isolated_browser_transport():
    source=(ROOT/"dashboard/src/App.jsx").read_text(encoding="utf-8")
    assert "testMode||path==='/test'?null" in source
    assert "testMode?undefined:locateCamera" in source
    assert "testMode={testMode} testSession={testSession}" in source

def test_camera_search_has_test_session_scoped_path():
    source=(ROOT/"dashboard/src/components/CameraSearch.jsx").read_text(encoding="utf-8")
    assert "routeTestMode=testMode||window.location.pathname==='/test'" in source
    assert "api.getTestCameras(activeSession.id)" in source
    assert "Search test cameras…" in source
