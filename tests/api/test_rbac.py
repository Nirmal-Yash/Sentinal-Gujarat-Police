import pytest
from conftest import ROLES, ROLE_PERMISSIONS

CAPABILITY_PROBES = {
    "camera:read": ("GET", "/cameras/", {}),
    "camera:write": ("POST", "/cameras/", {"json": {"name": "rbac-probe", "lat": 23.0}}),
    "alert:read": ("GET", "/alerts/", {}),
    "alert:operate": ("POST", "/alerts/not-a-uuid/acknowledge", {}),
    "search:read": ("GET", "/search/cameras", {}),
    "report:read": ("GET", "/reports/detections", {}),
    "evidence:read": ("GET", "/evidence/", {}),
    "evidence:create": ("POST", "/evidence/", {"json": {"media_type":"image/jpeg","storage_key":"../blocked"}}),
    "audit:read": ("GET", "/operations/audit/verify", {}),
    "registry:admin": ("POST", "/camera-imports/validate", {"files":{"file":("bad.txt", b"not-a-registry", "text/plain")}}),
}

AUTHORIZED = {
    "camera:read": {200}, "camera:write": {400,409,422},
    "alert:read": {200}, "alert:operate": {400,404,422},
    "search:read": {200,400,422}, "report:read": {200,400,422},
    "evidence:read": {200}, "evidence:create": {400,409,422},
    "audit:read": {200,503}, "registry:admin": {400,415,422},
}

@pytest.mark.parametrize("role", ROLES)
@pytest.mark.parametrize("capability", CAPABILITY_PROBES)
def test_full_rbac_matrix(api_client, role_tokens, role, capability):
    method, path, kwargs = CAPABILITY_PROBES[capability]
    r = api_client.request(method, path, headers={"Authorization": "Bearer " + role_tokens[role]}, **kwargs)
    if capability in ROLE_PERMISSIONS[role]:
        assert r.status_code in AUTHORIZED[capability], "%s %s returned %s: %s" % (role, capability, r.status_code, r.text[:300])
    else:
        assert r.status_code == 403

def test_runtime_rbac_matrix_matches_expected():
    from auth import ROLE_PERMISSIONS as runtime_permissions
    assert {k: set(v) for k, v in runtime_permissions.items()} == ROLE_PERMISSIONS

def test_rbac_users_are_distinct(api_client, role_tokens):
    ids = set()
    for role in ROLES:
        r = api_client.get("/auth/me", headers={"Authorization": "Bearer " + role_tokens[role]})
        assert r.status_code == 200
        ids.add(r.json()["id"])
    assert len(ids) == len(ROLES)
