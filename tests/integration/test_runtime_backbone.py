import pytest

@pytest.mark.integration
def test_runtime_redis_stream_contract(api_client, role_tokens):
    r = api_client.get("/operations/overview", headers={"Authorization":"Bearer " + role_tokens["AUDITOR"]})
    assert r.status_code == 200
    runtime = r.json()["runtime"]
    for name in ["raw_frames","detections","anpr_requests","alerts"]:
        assert name in runtime["redis_streams"]
        assert "length" in runtime["redis_streams"][name]
        assert runtime["redis_streams"][name]["length"] is None or runtime["redis_streams"][name]["length"] >= 0

@pytest.mark.integration
def test_reconciliation_contract(api_client, role_tokens):
    r = api_client.get("/reports/reconciliation", headers={"Authorization":"Bearer " + role_tokens["AUDITOR"]})
    assert r.status_code in {200,503}
    if r.status_code == 200:
        body = r.json()
        for key in ["total","tracked","with_plate","business_sightings","alerts","status"]:
            assert key in body

@pytest.mark.integration
def test_runtime_does_not_expose_provider_playback_url(api_client, role_tokens):
    r = api_client.get("/cameras/", headers={"Authorization":"Bearer " + role_tokens["VIEWER"]})
    assert r.status_code == 200
    for cam in r.json():
        assert not str(cam.get("hls_url","")).startswith("http://")
        assert not str(cam.get("hls_url","")).startswith("https://")
