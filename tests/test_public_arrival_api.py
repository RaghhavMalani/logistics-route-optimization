from unittest.mock import patch

from fastapi.testclient import TestClient

from backend.app.main import app
from backend.app.auth_store import AuthStore, get_auth_store
from backend.app.routes import public_arrivals
from src.portwatch_os.clock import get_clock, world_now
from src.portwatch_os.intelligence.public_ports import PublicPilot
from src.portwatch_os.intelligence.vesselfinder import VesselStore


def test_verified_scope_exact_ports_replay_and_no_client_source_urls(tmp_path):
    auth = AuthStore(tmp_path/"identity.db")
    for name, role, ports in [("chennai", "PORT_AUTHORITY", ("INMAA",)), ("paradip", "PORT_AUTHORITY", ("INPRT",)),
                               ("company", "SHIPPING_COMPANY", ()), ("admin", "NATIONAL_ADMIN", ())]:
        auth.provision(name+"@test.invalid", "qa-verified-password", role=role, ports=ports, display_name=name)
    store = PublicPilot(tmp_path/"pilot")
    vendor = VesselStore(tmp_path/"vendor")
    app.dependency_overrides[public_arrivals.service] = lambda: store
    app.dependency_overrides[get_auth_store] = lambda: auth
    try:
        with patch("src.portwatch_os.intelligence.vesselfinder.get_vessel_store", return_value=vendor), patch("backend.app.auth_store.get_auth_store", return_value=auth), patch.dict("os.environ", {"PORTWATCH_IDENTITY_MODE": "verified", "PORTWATCH_FRESHNESS_SCHEDULER": "0", "AISSTREAM_API_KEY": ""}), TestClient(app) as client:
            headers = {name: {"Authorization": "Bearer "+auth.login(name+"@test.invalid", "qa-verified-password", name)["accessToken"]} for name in ("chennai", "paradip", "company", "admin")}
            url = "/api/public-arrivals/workspace?portCode=INMAA"
            assert client.get(url, headers={"X-PortWatch-Role": "NATIONAL_ADMIN"}).status_code == 401
            assert client.get(url, headers={**headers["paradip"], "X-PortWatch-Port": "INMAA", "X-PortWatch-Role": "NATIONAL_ADMIN"}).status_code == 403
            assert client.get(url, headers=headers["company"]).status_code == 403
            assert client.get(url, headers=headers["chennai"]).status_code == 200
            assert client.get(url, headers=headers["chennai"]).json()["collection"]["schedulerRunning"] is False
            assert client.get(url.replace("INMAA", "INKAT"), headers=headers["admin"]).status_code == 422
            with get_clock().pin_replay(world_now()):
                assert client.post("/api/public-arrivals/refresh?portCode=INMAA", headers=headers["chennai"]).status_code == 409
                assert client.post("/api/public-arrivals/evaluate?portCode=INMAA", headers=headers["chennai"]).status_code == 409
                assert client.post("/api/public-arrivals/cohorts?portCode=INMAA", json={}, headers=headers["chennai"]).status_code == 409
            cohort_url = "/api/public-arrivals/cohorts?portCode=INMAA"
            assert client.post(cohort_url, json={}, headers={"X-PortWatch-Role": "NATIONAL_ADMIN"}).status_code == 401
            assert client.post(cohort_url, json={}, headers=headers["paradip"]).status_code == 403
            assert client.post(cohort_url, json={"enrollmentDays": 0}, headers=headers["chennai"]).status_code == 422
            assert client.post(cohort_url, json={"enrollmentEndAt": "2026-01-01T00:00:00Z"}, headers=headers["chennai"]).status_code == 422
            cohort = client.post(cohort_url, json={"enrollmentDays": 30}, headers=headers["chennai"])
            assert cohort.status_code == 200 and cohort.json()["status"] == "ENROLLING"
            assert client.post(cohort_url, json={}, headers=headers["chennai"]).status_code == 409
            key = cohort.json()["cohortId"]
            assert client.post(f"/api/public-arrivals/evaluate?portCode=INPRT&cohortId={key}", headers=headers["admin"]).status_code == 404
            with patch.object(store, "refresh", return_value={"results": [], "errors": []}) as refresh:
                assert client.post("/api/public-arrivals/refresh?portCode=INMAA", headers=headers["chennai"]).status_code == 200
                assert refresh.call_args.args[0] == "INMAA"
            assert client.get("/api/public-arrivals/dataset?portCode=INPRT", headers=headers["admin"]).status_code == 200
            assert client.get("/api/public-arrivals/evidence/not-a-file?portCode=INMAA", headers=headers["chennai"]).status_code == 404
            assert client.get("/api/public-arrivals/structured-evidence/not-a-file?portCode=INMAA", headers=headers["chennai"]).status_code == 404
            with patch.dict("os.environ", {"PORTWATCH_IDENTITY_MODE": "asserted"}):
                forged = client.post("/api/admin/freshness/public_ports_INMAA/refresh", headers={"X-PortWatch-Role": "NATIONAL_ADMIN", "X-PortWatch-Actor": "forged"})
                assert forged.status_code == 401
    finally:
        app.dependency_overrides.pop(public_arrivals.service, None)
        app.dependency_overrides.pop(get_auth_store, None)
        store.close()
        vendor.close()
