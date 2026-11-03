import json

from fastapi.testclient import TestClient

from backend.app.auth_store import AuthStore, get_auth_store
from backend.app.main import app


def test_configured_fleet_is_scoped_before_serialization_and_caching(tmp_path, monkeypatch):
    store = AuthStore(tmp_path / "identity.db")
    provider = tmp_path / "fleet.json"
    hulls = [
        {"vesselId": "QA-ONE", "name": "QA_FLEET_ONE", "availableTeu": 1234, "destinationPort": "INNSA"},
        {"vesselId": "QA-TWO", "name": "QA_FLEET_TWO", "availableTeu": 5678, "destinationPort": "INMAA"},
    ]
    provider.write_text(json.dumps({"companyId": "carrier-qa", "name": "QA carrier", "verified": True, "vessels": hulls}))
    monkeypatch.setenv("PORTWATCH_FLEET_PROVIDER", str(provider))
    monkeypatch.setenv("PORTWATCH_IDENTITY_MODE", "verified")
    monkeypatch.setattr("backend.app.auth_store.get_auth_store", lambda: store)
    monkeypatch.setitem(app.dependency_overrides, get_auth_store, lambda: store)
    monkeypatch.setattr("backend.app.services.cache_service.get_fleet", lambda: [
        {"id": row["vesselId"], "name": row["name"], "privateTerms": "QA_PRIVATE_TERMS"} for row in hulls
    ])
    password = "fixture-only-password"
    client = TestClient(app)
    identities = {}
    for name, role, company, hull, port in (
        ("owner", "SHIPPING_COMPANY", "carrier-qa", (), ()),
        ("rival", "SHIPPING_COMPANY", "another-carrier", (), ()),
        ("bridge-one", "VESSEL_OPERATOR", "carrier-qa", ("QA-ONE",), ()),
        ("bridge-two", "VESSEL_OPERATOR", "carrier-qa", ("QA-TWO",), ()),
        ("wrong-carrier", "VESSEL_OPERATOR", "another-carrier", ("QA-ONE",), ()),
        ("port", "PORT_AUTHORITY", "port-agency", (), ("INNSA",)),
    ):
        email = name + "@example.invalid"
        store.provision(email, password, role=role, display_name=name, organisation=company, vessel_ids=hull, ports=port)
        login = client.post("/api/auth/login", json={"email": email, "password": password})
        assert login.status_code == 200
        identities[name] = {"Authorization": "Bearer " + login.json()["accessToken"],
                            "X-PortWatch-Role": "NATIONAL_ADMIN", "X-PortWatch-Org": "carrier-qa",
                            "X-PortWatch-Vessels": "QA-ONE,QA-TWO"}

    def get(path, identity):
        return client.get("/api" + path, headers=identities[identity])

    owned = get("/company/fleet", "owner")
    assert owned.status_code == 200 and owned.headers["cache-control"] == "no-store"
    assert [v["available_teu"] for v in owned.json()["vessels"]] == [1234, 5678]
    for identity, own, other in (("bridge-one", "QA-ONE", "QA-TWO"), ("bridge-two", "QA-TWO", "QA-ONE"),
                                 ("port", "QA-ONE", "QA-TWO")):
        own_response = get("/company/vessels/" + own, identity)
        assert own_response.status_code == 200 and own_response.json()["vessel"]["vessel_id"] == own
        assert "available_teu" not in own_response.json()["vessel"]
        assert get("/company/vessels/" + other, identity).status_code == 404
        assert get("/company/cargo?port_code=INNSA", identity).status_code == 403
        assert [v["vessel_id"] for v in get("/company", identity).json()["vessels"]] == [own]
        assert get("/fleet", identity).json() == [{"id": own, "name": "QA_FLEET_" + own[3:]}]
    for identity in ("rival", "wrong-carrier"):
        for path in ("/company", "/company/fleet?company_id=carrier-qa", "/company/vessels/QA-ONE", "/company/risk", "/company/routes"):
            response = get(path, identity)
            assert response.status_code == 404 and "QA_FLEET_" not in response.text
        assert get("/fleet", identity).json() == []

    marker = "QA_PRIVATE_ASSISTANT_REQUEST"
    run = client.post("/api/agents/run", headers=identities["owner"], json={"question": marker})
    assert run.status_code == 200
    run_id = run.json()["runId"]
    assert get("/agents/runs/" + run_id, "owner").status_code == 200
    assert get("/agents/runs/" + run_id + "?include_results=true", "rival").status_code == 404
    assert marker not in get("/agents/runs", "bridge-one").text
    branch = client.post("/api/world/branches", headers=identities["owner"], json={
        "mode": "DEMO", "assumptions": [{"kind": "close_chokepoint", "subject": "BAB_EL_MANDEB", "value": 0.9}],
    })
    assert branch.status_code == 200
    branch_id = branch.json()["branch"]["branchId"]
    assert branch_id in get("/world/observed?mode=DEMO", "owner").text
    assert branch_id not in get("/world/observed?mode=DEMO", "rival").text
    assert get("/world/branches/" + branch_id + "/cascades/guessed", "rival").status_code == 404
    world = get("/world/entities/lookup?fleetId=QA-ONE", "rival")
    assert world.status_code == 404
    public = client.get("/api/public/workspace")
    assert public.status_code == 200 and "QA_FLEET_" not in public.text and "QA_PRIVATE_TERMS" not in public.text
    store.provision("owner@example.invalid", password, role="SHIPPING_COMPANY", display_name="owner",
                    organisation="another-carrier")
    assert get("/company/fleet", "owner").status_code == 401
    login = client.post("/api/auth/login", json={"email": "owner@example.invalid", "password": password})
    assert login.status_code == 200
    identities["owner"]["Authorization"] = "Bearer " + login.json()["accessToken"]
    assert get("/company/fleet", "owner").status_code == 404
    assert get("/agents/runs/" + run_id, "owner").status_code == 404
    assert branch_id not in get("/world/observed?mode=DEMO", "owner").text
    client.close()
