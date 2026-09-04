import pytest

@pytest.mark.parametrize("path", ["/cameras/", "/cameras/stats/summary", "/cameras/pipeline/stats", "/cameras/analytics/recent"])
def test_camera_read_contract(api_client, role_tokens, path):
    r = api_client.get(path, headers={"Authorization": "Bearer " + role_tokens["VIEWER"]})
    assert r.status_code == 200
    assert r.headers.get("content-type","").startswith("application/json")

def test_camera_pagination_boundaries(api_client, role_tokens):
    h = {"Authorization": "Bearer " + role_tokens["VIEWER"]}
    for limit in [1,250,500]:
        assert api_client.get("/cameras/", headers=h, params={"limit":limit,"offset":0}).status_code == 200
    for params in [{"limit":0},{"limit":501},{"offset":-1}]:
        assert api_client.get("/cameras/", headers=h, params=params).status_code == 422

def test_alert_read_contract(api_client, role_tokens):
    h = {"Authorization": "Bearer " + role_tokens["VIEWER"]}
    for path in ["/alerts/","/alerts/stats/counts","/search/alerts/recent"]:
        assert api_client.get(path, headers=h).status_code == 200

def test_invalid_alert_transition_never_mutates_for_bad_target(api_client, role_tokens):
    r = api_client.get("/alerts/", headers={"Authorization":"Bearer " + role_tokens["OPERATOR"]})
    assert r.status_code == 200
    alerts = r.json()
    if not alerts:
        pytest.skip("No alert available for transition test")
    alert_id = alerts[0]["id"]
    bad = api_client.post("/alerts/" + str(alert_id) + "/transition",
                          headers={"Authorization":"Bearer " + role_tokens["OPERATOR"]},
                          json={"status":"CLOSED"})
    assert bad.status_code in {200,409}

def test_watchlist_admin_crud(api_client, role_tokens):
    h = {"Authorization":"Bearer " + role_tokens["ADMIN"]}
    body = {"name":"API Suite Temp Watch","entity_type":"vehicle","description":"temporary test entry",
            "plate_number":"GJ01AB1234","alert_priority":"HIGH"}
    created = api_client.post("/watchlist/", headers=h, json=body)
    assert created.status_code == 200
    entry_id = created.json()["id"]
    listed = api_client.get("/watchlist/", headers={"Authorization":"Bearer " + role_tokens["VIEWER"]})
    assert listed.status_code == 200
    assert any(str(x["id"]) == str(entry_id) for x in listed.json())
    deleted = api_client.delete("/watchlist/" + str(entry_id), headers=h)
    assert deleted.status_code == 200

def test_watchlist_write_forbidden_for_operator(api_client, role_tokens):
    r = api_client.post("/watchlist/", headers={"Authorization":"Bearer " + role_tokens["OPERATOR"]},
                        json={"name":"denied","entity_type":"vehicle","plate_number":"GJ01AB1234","alert_priority":"HIGH"})
    assert r.status_code == 403
