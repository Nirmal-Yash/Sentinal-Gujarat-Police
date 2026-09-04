import pytest
import uuid

def test_test_mode_role_access(api_client, role_tokens):
    for role in ["ADMIN","SUPERADMIN"]:
        r = api_client.get("/test/assets", headers={"Authorization":"Bearer " + role_tokens[role]})
        assert r.status_code in {200,404}
    for role in ["VIEWER","OPERATOR","INVESTIGATOR","AUDITOR"]:
        r = api_client.get("/test/assets", headers={"Authorization":"Bearer " + role_tokens[role]})
        assert r.status_code == 403

def test_invalid_test_session_id(api_client, role_tokens):
    r = api_client.get("/test/sessions/not-a-uuid/status", headers={"Authorization":"Bearer " + role_tokens["ADMIN"]})
    assert r.status_code in {400,422}

def test_test_mode_isolation_flag(api_client, role_tokens):
    r = api_client.get("/test/sessions/active", headers={"Authorization":"Bearer " + role_tokens["ADMIN"]})
    assert r.status_code in {200,404}
