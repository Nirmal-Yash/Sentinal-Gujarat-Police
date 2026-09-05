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

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

def test_sensitive_routes_use_capability_permissions():
    alerts = (ROOT / "api" / "routes" / "alerts.py").read_text(encoding="utf-8")
    snapshot = (ROOT / "api" / "routes" / "camera_snapshot.py").read_text(encoding="utf-8")
    cameras = (ROOT / "api" / "routes" / "cameras.py").read_text(encoding="utf-8")
    imports = (ROOT / "api" / "routes" / "camera_imports.py").read_text(encoding="utf-8")
    assert 'has_permission(principal, "alert:operate")' in alerts
    assert 'dependencies=[Depends(require_permission("camera:read"))]' in snapshot
    assert 'require_permission("camera:write")' in cameras
    assert 'require_permission("registry:admin")' in cameras
    assert 'require_permission("registry:admin")' in imports

def test_rbac_runtime_matrix_exposes_expected_capabilities():
    import sys
    sys.path.insert(0, str(ROOT / "api"))
    from auth import ROLE_PERMISSIONS, ROLE_ORDER
    assert ROLE_ORDER["VIEWER"] < ROLE_ORDER["OPERATOR"] < ROLE_ORDER["ADMIN"] <= ROLE_ORDER["SUPERADMIN"]
    assert "camera:read" in ROLE_PERMISSIONS["VIEWER"]
    assert "camera:write" not in ROLE_PERMISSIONS["VIEWER"]
    assert "camera:write" in ROLE_PERMISSIONS["ADMIN"]
    assert "alert:operate" not in ROLE_PERMISSIONS["VIEWER"]
    assert "alert:operate" in ROLE_PERMISSIONS["OPERATOR"]
    assert "registry:admin" in ROLE_PERMISSIONS["ADMIN"]
