from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]

def test_camera_out_adds_canonical_camera_id():
    source=(ROOT/"api/models.py").read_text(encoding="utf-8")
    assert "camera_id:Optional[str]=None" in source
    assert 'value["camera_id"]=provider_id' in source
    assert "Field(None,ge=1,le=30)" in source

def test_cctv_gateway_rejects_ids_outside_cam01_cam30():
    source=(ROOT/"api/services/cctv_gateway.py").read_text(encoding="utf-8")
    assert "camera id must be cam01 through cam30" in source

def test_map_uses_canonical_camera_id():
    source=(ROOT/"dashboard/src/components/MapView.jsx").read_text(encoding="utf-8")
    assert "cam.camera_id" in source
