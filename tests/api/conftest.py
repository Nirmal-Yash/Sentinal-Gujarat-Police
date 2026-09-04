import os
import pathlib
import sys
import pytest
import httpx

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "api"))

BASE_URL = os.getenv("SENTINEL_BASE_URL", "http://localhost:8000").rstrip("/")
RBAC_PASSWORD = os.getenv("RBAC_TEST_PASSWORD", "Test@12345")
PREFIX = os.getenv("RBAC_TEST_USERNAME_PREFIX", "rbac-test")
ROLES = ("SUPERADMIN", "ADMIN", "OPERATOR", "INVESTIGATOR", "VIEWER", "AUDITOR")
ROLE_PERMISSIONS = {
    "VIEWER": {"camera:read","alert:read","search:read","evidence:read"},
    "OPERATOR": {"camera:read","alert:read","alert:operate","search:read","evidence:read","evidence:create"},
    "INVESTIGATOR": {"camera:read","alert:read","alert:operate","search:read","report:read","evidence:read","evidence:create"},
    "AUDITOR": {"camera:read","alert:read","search:read","report:read","evidence:read","audit:read"},
    "ADMIN": {"camera:read","camera:write","alert:read","alert:operate","search:read","report:read","evidence:read","evidence:create","registry:admin","audit:read"},
    "SUPERADMIN": {"camera:read","camera:write","alert:read","alert:operate","search:read","report:read","evidence:read","evidence:create","registry:admin","audit:read","system:admin"},
}

@pytest.fixture(scope="session")
def api_client():
    with httpx.Client(base_url=BASE_URL, timeout=httpx.Timeout(20.0), follow_redirects=False) as client:
        try:
            response = client.get("/health")
        except Exception as exc:
            pytest.skip("Sentinel API unavailable at %s: %s" % (BASE_URL, exc))
        if response.status_code != 200:
            pytest.skip("Sentinel API /health returned %s" % response.status_code)
        yield client

def login(client, role):
    return client.post("/auth/login", json={"username": PREFIX + "-" + role.lower(), "password": RBAC_PASSWORD})

@pytest.fixture(scope="session")
def role_tokens(api_client):
    tokens = {}
    for role in ROLES:
        response = login(api_client, role)
        if response.status_code != 200:
            pytest.skip("RBAC user %s unavailable: HTTP %s %s" % (role, response.status_code, response.text[:200]))
        tokens[role] = response.json()["access_token"]
    return tokens
