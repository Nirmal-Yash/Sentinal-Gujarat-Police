from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]

def test_catalogue_enforces_cam01_to_cam30():
    source=(ROOT/"ingestion/catalogue_sync.py").read_text(encoding="utf-8")
    assert "numeric < 1 or numeric > 30" in source
    assert 'f"cam{numeric:02d}"' in source
    assert '"camera_id": canonical' in source

def test_search_and_dashboard_expose_canonical_camera_id():
    search=(ROOT/"api/routes/search.py").read_text(encoding="utf-8")
    ui=(ROOT/"dashboard/src/components/CameraGrid.jsx").read_text(encoding="utf-8")
    assert "AS camera_id" in search
    assert "cam${padded}" in ui

def test_ingestion_rejects_out_of_contract_ids():
    source=(ROOT/"ingestion/worker.py").read_text(encoding="utf-8")
    assert "Skipping out-of-contract production camera" in source