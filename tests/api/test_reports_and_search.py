import pytest

@pytest.mark.parametrize("path", [
    "/reports/detections",
    "/reports/vehicle-sightings",
    "/reports/reconciliation",
])
def test_report_contract_for_report_roles(api_client, role_tokens, path):
    for role in ["INVESTIGATOR","AUDITOR","ADMIN","SUPERADMIN"]:
        r = api_client.get(path, headers={"Authorization":"Bearer " + role_tokens[role]})
        assert r.status_code in {200,503}

@pytest.mark.parametrize("role", ["VIEWER","OPERATOR","INVESTIGATOR","AUDITOR","ADMIN","SUPERADMIN"])
def test_camera_search_access(api_client, role_tokens, role):
    r = api_client.get("/search/cameras", headers={"Authorization":"Bearer " + role_tokens[role]})
    assert r.status_code == 200

def test_search_boundary_values(api_client, role_tokens):
    h = {"Authorization":"Bearer " + role_tokens["VIEWER"]}
    for params in [{"limit":0},{"limit":-1},{"limit":10001}]:
        r = api_client.get("/search/cameras", headers=h, params=params)
        assert r.status_code in {200,400,422}
