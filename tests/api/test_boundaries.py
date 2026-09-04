import pytest

@pytest.mark.parametrize("path", ["/cameras/", "/alerts/", "/search/cameras", "/evidence/", "/operations/overview"])
def test_missing_auth_is_rejected(api_client, path):
    r = api_client.get(path)
    assert r.status_code in {401,403}

@pytest.mark.parametrize("path", [
    "/alerts/not-a-uuid/acknowledge",
    "/evidence/not-a-uuid",
    "/operations/cameras/not-a-uuid/health",
])
def test_invalid_identifiers_never_500(api_client, role_tokens, path):
    r = api_client.get(path, headers={"Authorization": "Bearer " + role_tokens["SUPERADMIN"]})
    assert r.status_code in {400,404,422}

def test_invalid_http_method(api_client, role_tokens):
    r = api_client.patch("/health", headers={"Authorization": "Bearer " + role_tokens["SUPERADMIN"]})
    assert r.status_code in {404,405}

def test_registry_size_limit(api_client, role_tokens):
    payload = b"x" * (5 * 1024 * 1024 + 1)
    r = api_client.post("/camera-imports/validate", headers={"Authorization": "Bearer " + role_tokens["ADMIN"]},
                        files={"file": ("huge.csv", payload, "text/csv")})
    assert r.status_code == 413

def test_registry_wrong_type(api_client, role_tokens):
    r = api_client.post("/camera-imports/validate", headers={"Authorization": "Bearer " + role_tokens["ADMIN"]},
                        files={"file": ("bad.txt", b"hello", "text/plain")})
    assert r.status_code == 415

def test_registry_invalid_data_is_reported_not_accepted(api_client, role_tokens):
    r = api_client.post("/camera-imports/validate", headers={"Authorization": "Bearer " + role_tokens["ADMIN"]},
                        files={"file": ("bad.csv", b"camera_name,latitude,longitude\nCAM-1,not-a-number,72.5\n", "text/csv")})
    assert r.status_code == 200
    assert r.json()["summary"]["allow_upload"] is False

def test_sql_injection_is_data(api_client, role_tokens):
    r = api_client.get("/search/cameras", headers={"Authorization": "Bearer " + role_tokens["VIEWER"]},
                       params={"q": "' OR 1=1 --"})
    assert r.status_code in {200,400,422}
