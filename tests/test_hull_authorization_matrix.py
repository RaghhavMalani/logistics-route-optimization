import json

import pytest
from fastapi.testclient import TestClient

from backend.app.auth_store import AuthStore, get_auth_store
from backend.app.main import app
from tests.test_demo_terminal import setup


ACCOUNTS = [
    ("admin", "NATIONAL_ADMIN", "", (), (), ("QA-ONE", "QA-TWO")),
    ("owner", "SHIPPING_COMPANY", "carrier-qa", (), (), ("QA-ONE", "QA-TWO")),
    ("rival", "SHIPPING_COMPANY", "other-carrier", (), (), ()),
    ("assigned", "VESSEL_OPERATOR", "", ("QA-ONE",), (), ("QA-ONE",)),
    ("sibling", "VESSEL_OPERATOR", "carrier-qa", ("QA-TWO",), (), ("QA-TWO",)),
    ("port", "PORT_AUTHORITY", "", (), ("INNSA", "INMAA"), ("QA-ONE",)),
    ("anonymous", None, "", (), (), ()),
    ("asserted", None, "", (), (), ()),
]


@pytest.fixture(scope="module")
def verified_api(tmp_path_factory):
    root = tmp_path_factory.mktemp("hull-matrix")
    store = AuthStore(root / "identity.db")
    provider = root / "fleet.json"
    hulls = [{"vesselId": hull, "name": "PRIVATE-" + hull, "availableTeu": 1243, "destinationPort": port}
             for hull, port in (("QA-ONE", "INNSA"), ("QA-TWO", "INMAA"))]
    provider.write_text(json.dumps({"companyId": "carrier-qa", "name": "QA Carrier", "verified": True, "vessels": hulls}))
    cache = [{"id": hull["vesselId"], "name": hull["name"], "privateTerms": "fixture-secret"} for hull in hulls]
    with pytest.MonkeyPatch.context() as patch:
        patch.setenv("PORTWATCH_FLEET_PROVIDER", str(provider))
        patch.setenv("PORTWATCH_IDENTITY_MODE", "verified")
        patch.setattr("backend.app.auth_store.get_auth_store", lambda: store)
        patch.setitem(app.dependency_overrides, get_auth_store, lambda: store)
        patch.setattr("backend.app.services.cache_service.get_fleet", lambda: cache)
        client = TestClient(app)
        headers = {"anonymous": {}, "asserted": {"X-PortWatch-Role": "NATIONAL_ADMIN"}}
        password = "test-only-hull-matrix"
        for name, role, organisation, vessels, ports, _ in ACCOUNTS:
            if role is None:
                continue
            email = name + "@example.invalid"
            store.provision(email, password, role=role, display_name=name, organisation=organisation,
                            vessel_ids=vessels, ports=ports)
            response = client.post("/api/auth/login", json={"email": email, "password": password})
            assert response.status_code == 200
            headers[name] = {"Authorization": "Bearer " + response.json()["accessToken"],
                             "X-PortWatch-Role": "NATIONAL_ADMIN", "X-PortWatch-Vessels": "QA-ONE,QA-TWO"}
        yield client, headers, provider
        client.close()


@pytest.mark.parametrize("name,role,organisation,vessels,ports,allowed", ACCOUNTS, ids=[row[0] for row in ACCOUNTS])
@pytest.mark.parametrize("path", ["/fleet", "/company", "/company/fleet", "/company/risk", "/company/routes",
                                  "/company/vessels/QA-ONE", "/company/vessels/QA-TWO"])
def test_private_hull_endpoints(verified_api, monkeypatch, name, role, organisation, vessels, ports, allowed, path):
    client, headers, _ = verified_api
    if name == "asserted":
        monkeypatch.setenv("PORTWATCH_IDENTITY_MODE", "asserted")
    response = client.get("/api" + path, headers=headers[name])
    if name == "anonymous":
        expected = 401
    elif path.startswith("/company/vessels/"):
        expected = 200 if path.rsplit("/", 1)[-1] in allowed else 404
    else:
        expected = 200 if path == "/fleet" or allowed else 404
    assert response.status_code == expected
    assert "fixture-secret" not in response.text
    for hull in {"QA-ONE", "QA-TWO"}.difference(allowed):
        assert "PRIVATE-" + hull not in response.text
    if path in ("/fleet", "/company", "/company/fleet") and expected == 200:
        rows = response.json() if path == "/fleet" else response.json()["vessels"]
        assert {row.get("id") or row.get("vessel_id") for row in rows} == set(allowed)
    if expected == 200 and role in ("VESSEL_OPERATOR", "PORT_AUTHORITY"):
        assert "available_teu" not in response.text


def test_unattributed_cache_and_company_override(verified_api, monkeypatch):
    client, headers, _ = verified_api
    assert client.get("/api/company/vessels/QA-ONE?company_id=other-carrier", headers=headers["owner"]).status_code == 404
    assert client.get("/api/company/fleet?company_id=carrier-qa", headers=headers["rival"]).status_code == 404
    monkeypatch.delenv("PORTWATCH_FLEET_PROVIDER")
    assert client.get("/api/fleet", headers=headers["rival"]).json() == []
    assert client.get("/api/fleet", headers=headers["assigned"]).json() == []
    assert client.get("/api/fleet", headers=headers["admin"]).status_code == 200


def test_demo_company_and_port_only_receive_their_hulls(tmp_path, monkeypatch):
    store, client = setup(tmp_path, monkeypatch)
    token = store.create("SHIPPING_COMPANY")["accessToken"]
    headers = {"Authorization": "Bearer " + token}

    store.switch(token, "NATIONAL_ADMIN")
    comparison = client.post("/api/demo/scenario", headers=headers, json={"vesselId": "PWD-002"}).json()
    option = comparison["result"]["options"][0]["optionId"]

    def populate(world):
        world["fleet"][1].update(operatorOrganisation="Other Demo Carrier", portCode="INMAA")
        world["fleet"][2].update(portCode="INMAA")

    store.update(token, populate)
    for role, allowed in (("SHIPPING_COMPANY", {"PWD-001", "PWD-003"}), ("PORT_AUTHORITY", {"PWD-001"}),
                          ("VESSEL_OPERATOR", {"PWD-001"}), ("NATIONAL_ADMIN", {"PWD-001", "PWD-002", "PWD-003"})):
        store.switch(token, role)
        for path, field in (("/fleet", "id"), ("/company/fleet", "vessel_id")):
            response = client.get("/api/demo/terminal" + path, headers=headers)
            assert response.status_code == 200
            rows = response.json() if path == "/fleet" else response.json()["vessels"]
            assert {row[field] for row in rows} == allowed
        detail = client.get("/api/demo/terminal/company/vessels/PWD-002", headers=headers)
        assert detail.status_code == (200 if "PWD-002" in allowed else 404)
        workspace = client.get("/api/demo/workspace", headers=headers).json()["world"]
        assert {row["id"] for row in workspace["fleet"]} == allowed

    # A comparison made in a broader role must not widen a later action.
    store.switch(token, "SHIPPING_COMPANY")
    response = client.post("/api/demo/proposal", headers=headers, json={
        "comparisonId": comparison["id"], "optionId": option,
    })
    assert response.status_code == 404
    store.switch(token, "PORT_AUTHORITY")
    response = client.post("/api/demo/port-scenario", headers=headers, json={})
    assert response.status_code == 200
    assert response.json()["vesselIds"] == ["PWD-001"]
    assert "PWD-002" not in response.text
    assert "PWD-003" not in response.text
    client.close()
