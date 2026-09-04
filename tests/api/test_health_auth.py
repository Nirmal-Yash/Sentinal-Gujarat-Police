import pytest
from conftest import PREFIX, RBAC_PASSWORD, ROLES, login

def test_health_contract(api_client):
    r = api_client.get("/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert body["service"]

def test_auth_config_contract(api_client):
    r = api_client.get("/auth/config")
    assert r.status_code in {200, 503}
    if r.status_code == 200:
        assert "auth_required" in r.json()
        assert "login_available" in r.json()

@pytest.mark.parametrize("username,password", [
    ("missing-user", "bad-password"),
    (PREFIX + "-viewer", "wrong-password"),
    ("", ""),
])
def test_invalid_login_statuses(api_client, username, password):
    r = api_client.post("/auth/login", json={"username": username, "password": password})
    assert r.status_code in {400, 401, 422}

def test_malformed_login_json(api_client):
    r = api_client.post("/auth/login", content="{not-json", headers={"Content-Type": "application/json"})
    assert r.status_code in {400, 422}

def test_login_me_logout_revocation(api_client):
    r = login(api_client, "SUPERADMIN")
    assert r.status_code == 200
    token = r.json()["access_token"]
    headers = {"Authorization": "Bearer " + token}
    assert api_client.get("/auth/me", headers=headers).status_code == 200
    assert api_client.post("/auth/logout", headers=headers).status_code == 200
    assert api_client.get("/auth/me", headers=headers).status_code == 401

def test_tampered_access_token(api_client):
    r = api_client.get("/auth/me", headers={"Authorization": "Bearer definitely-not-a-jwt"})
    assert r.status_code == 401

@pytest.mark.parametrize("role", ROLES)
def test_each_rbac_user_login(api_client, role):
    r = login(api_client, role)
    assert r.status_code == 200
    assert r.json()["user"]["role"] == role
