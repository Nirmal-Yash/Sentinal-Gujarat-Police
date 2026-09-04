import pytest

def test_login_to_operational_dashboard(api_client, role_tokens):
    h = {"Authorization":"Bearer " + role_tokens["VIEWER"]}
    assert api_client.get("/auth/me", headers=h).status_code == 200
    assert api_client.get("/cameras/", headers=h).status_code == 200
    assert api_client.get("/alerts/", headers=h).status_code == 200
    assert api_client.get("/search/cameras", headers=h).status_code == 200

def test_investigation_path(api_client, role_tokens):
    h = {"Authorization":"Bearer " + role_tokens["INVESTIGATOR"]}
    assert api_client.get("/reports/detections", headers=h).status_code in {200,503}
    assert api_client.get("/reports/vehicle-sightings", headers=h).status_code in {200,503}

def test_admin_operations_path(api_client, role_tokens):
    h = {"Authorization":"Bearer " + role_tokens["ADMIN"]}
    assert api_client.get("/operations/overview", headers=h).status_code == 200
    assert api_client.get("/test/assets", headers=h).status_code in {200,404}

def test_viewer_boundary_path(api_client, role_tokens):
    h = {"Authorization":"Bearer " + role_tokens["VIEWER"]}
    assert api_client.get("/watchlist/", headers=h).status_code == 200
    assert api_client.post("/watchlist/", headers=h, json={"name":"denied","entity_type":"vehicle","plate_number":"GJ01AA1111","alert_priority":"HIGH"}).status_code == 403

def test_superadmin_full_read_path(api_client, role_tokens):
    h = {"Authorization":"Bearer " + role_tokens["SUPERADMIN"]}
    for path in ["/cameras/","/alerts/","/search/cameras","/reports/detections","/operations/overview"]:
        assert api_client.get(path, headers=h).status_code in {200,503}
