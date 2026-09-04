import pytest

@pytest.mark.parametrize("camera", ["cam01","cam02","cam30","cam00","cam31","bad-camera"])
def test_cctv_identifier_and_upstream_handling(api_client, role_tokens, camera):
    r = api_client.get("/cctv/" + camera + "/index.m3u8", headers={"Authorization":"Bearer " + role_tokens["VIEWER"]})
    if camera in {"cam00","cam31","bad-camera"}:
        assert r.status_code in {400,404,502,503}
    else:
        assert r.status_code in {200,404,502,503}
        if r.status_code == 200:
            assert "#EXTM3U" in r.text

def test_cctv_token_scope(api_client, role_tokens):
    issued = api_client.get("/cctv/token/cam01", headers={"Authorization":"Bearer " + role_tokens["VIEWER"]})
    if issued.status_code != 200:
        pytest.skip("cam01 playback token unavailable")
    token = issued.json()["token"]
    wrong = api_client.get("/cctv/cam02/index.m3u8", params={"access_token":token},
                           headers={"Authorization":"Bearer " + role_tokens["VIEWER"]})
    assert wrong.status_code == 403

def test_evidence_path_traversal(api_client, role_tokens):
    r = api_client.post("/evidence/", headers={"Authorization":"Bearer " + role_tokens["OPERATOR"]},
                        json={"media_type":"image/jpeg","storage_key":"../../etc/passwd"})
    assert r.status_code == 422

def test_missing_evidence_returns_404(api_client, role_tokens):
    r = api_client.get("/evidence/00000000-0000-0000-0000-000000000000",
                       headers={"Authorization":"Bearer " + role_tokens["VIEWER"]})
    assert r.status_code == 404

def test_operations_contract(api_client, role_tokens):
    r = api_client.get("/operations/overview", headers={"Authorization":"Bearer " + role_tokens["AUDITOR"]})
    assert r.status_code == 200
    body = r.json()
    assert "metrics" in body and "runtime" in body
    assert "redis" in body["runtime"]
    audit = api_client.get("/operations/audit/verify", headers={"Authorization":"Bearer " + role_tokens["AUDITOR"]})
    assert audit.status_code in {200,503}
