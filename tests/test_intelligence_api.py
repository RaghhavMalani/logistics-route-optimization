from datetime import timedelta
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

from fastapi import HTTPException
from fastapi.testclient import TestClient

from backend.app.main import app
from backend.app.routes import intelligence
from backend.app.auth_store import AuthStore, get_auth_store
from src.portwatch_os.clock import world_now
from src.portwatch_os.intelligence.cameras import CameraRegistry
from src.portwatch_os.ledger.store import SqliteLedgerStore

ADMIN = {"X-PortWatch-Role": "NATIONAL_ADMIN", "X-PortWatch-Actor": "test.admin"}
PORT = {"X-PortWatch-Role": "PORT_AUTHORITY", "X-PortWatch-Actor": "test.port", "X-PortWatch-Port": "INNSA"}
OTHER_PORT = {**PORT, "X-PortWatch-Port": "INMAA"}
COMPANY = {"X-PortWatch-Role": "SHIPPING_COMPANY", "X-PortWatch-Actor": "test.company"}


def camera(camera_id="jnpa-berth-1", access="port_authority"):
    return {"id": camera_id, "portCode": "JNPT", "name": "JNPA berth viewpoint", "lat": 18.95, "lon": 72.95,
            "coverage": "One supplied quay viewpoint", "viewpoint": "berth", "access": access,
            "source": "Port authority", "rightsBasis": "Feed supplied by the authority"}


class IntelligenceApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.auth_tmp = tempfile.TemporaryDirectory()
        cls.auth = AuthStore(Path(cls.auth_tmp.name) / "identity.db")
        password = "test-only-strong-password"
        global ADMIN, PORT, OTHER_PORT, COMPANY
        for name, role, ports in (("admin", "NATIONAL_ADMIN", ()), ("port", "PORT_AUTHORITY", ("INNSA",)),
                                  ("other", "PORT_AUTHORITY", ("INMAA",)), ("company", "SHIPPING_COMPANY", ())):
            cls.auth.provision(f"{name}@test.invalid", password, role=role, display_name=name, ports=ports)
        def headers(name):
            return {"Authorization": "Bearer " + cls.auth.login(f"{name}@test.invalid", password, "test")["accessToken"]}
        ADMIN, PORT, OTHER_PORT, COMPANY = (headers(name) for name in ("admin", "port", "other", "company"))

    @classmethod
    def tearDownClass(cls):
        cls.auth_tmp.cleanup()

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.registry = CameraRegistry(Path(self.tmp.name) / "cameras.db")
        self.ledger = SqliteLedgerStore(Path(self.tmp.name) / "ledger.db")
        app.dependency_overrides[intelligence.registry] = lambda: self.registry
        self.ledger_patch = patch.object(intelligence, "get_ledger", return_value=self.ledger)
        self.ledger_patch.start()
        self.auth_patch = patch("backend.app.auth_store.get_auth_store", return_value=self.auth)
        self.auth_patch.start()
        app.dependency_overrides[get_auth_store] = lambda: self.auth
        self.mode_patch = patch.dict("os.environ", {"PORTWATCH_IDENTITY_MODE": "verified"})
        self.mode_patch.start()
        self.client = TestClient(app)

    def tearDown(self):
        self.client.close()
        app.dependency_overrides.pop(intelligence.registry, None)
        self.ledger_patch.stop()
        self.auth_patch.stop()
        self.mode_patch.stop()
        app.dependency_overrides.pop(get_auth_store, None)
        self.ledger.close()
        self.tmp.cleanup()

    def test_all_ports_context_without_camera_or_forecast_fabrication(self):
        with patch("backend.app.routes.global_eye._load_events", side_effect=HTTPException(503, "news unavailable")):
            result = self.client.get("/api/intelligence/context", headers=ADMIN)
        self.assertEqual(result.status_code, 200, result.text)
        body = result.json()
        from src.utils import port_registry
        self.assertEqual({p["code"] for p in body["ports"]}, {p.locode for p in port_registry.all_ports()})
        self.assertEqual(body["cameras"], [])
        self.assertEqual(body["weatherFeedback"]["total"], 0)
        self.assertEqual(body["news"]["status"], "UNAVAILABLE")

    def test_camera_registration_requires_named_authority(self):
        for headers, status in (({}, 401), (COMPANY, 403), (OTHER_PORT, 403), (PORT, 200)):
            result = self.client.post("/api/intelligence/cameras", json=camera(), headers=headers)
            self.assertEqual(result.status_code, status, result.text)
        saved = self.registry.get("jnpa-berth-1")
        self.assertEqual(saved["portCode"], "INNSA")
        self.assertEqual(saved["health"], "UNCONFIGURED")

    def test_feedback_route_is_not_treated_as_a_port_identifier(self):
        response = self.client.get("/api/weather/feedback?portCode=JNPT", headers=ADMIN)
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["total"], 0)

    def test_camera_registry_health_reports_corruption(self):
        self.assertTrue(self.registry.probe()["ok"])
        self.registry.path.write_bytes(b"not sqlite")
        self.assertFalse(self.registry.probe()["ok"])

    def test_private_camera_and_evidence_are_scoped(self):
        self.client.post("/api/intelligence/cameras", json=camera(), headers=PORT)
        for headers, expected in ((ADMIN, 1), (PORT, 1), (OTHER_PORT, 0), (COMPANY, 0)):
            result = self.client.get("/api/intelligence/cameras", headers=headers)
            self.assertEqual(len(result.json()["cameras"]), expected)

    def test_forged_administrator_headers_and_missing_identity_are_refused(self):
        self.client.post("/api/intelligence/cameras", json={**camera(), "mediaUrl": "https://private.test.invalid/feed"}, headers=PORT)
        forged = {"X-PortWatch-Role": "NATIONAL_ADMIN", "X-PortWatch-Actor": "attacker", "X-PortWatch-Port": "INNSA"}
        for headers in ({}, forged, {**forged, "Authorization": "Bearer invented"}):
            self.assertEqual(self.client.get("/api/intelligence/cameras", headers=headers).status_code, 401)
            self.assertEqual(self.client.post("/api/intelligence/cameras", json=camera(), headers=headers).status_code, 401)
        # Valid credentials plus forged claims cannot elevate the company or another port.
        for headers in ({**COMPANY, **forged}, {**OTHER_PORT, **forged}):
            response = self.client.get("/api/intelligence/cameras", headers=headers)
            self.assertEqual(response.status_code, 200)
            self.assertNotIn("private.test.invalid", response.text)
            self.assertEqual(self.client.post("/api/intelligence/cameras", json=camera(), headers=headers).status_code, 403)

    def test_explicit_demo_mode_cannot_access_private_cameras_or_write_evidence(self):
        self.client.post("/api/intelligence/cameras", json=camera(), headers=PORT)
        with patch.dict("os.environ", {"PORTWATCH_IDENTITY_MODE": "asserted"}):
            demo = {"X-PortWatch-Role": "NATIONAL_ADMIN", "X-PortWatch-Actor": "demo"}
            self.assertEqual(self.client.get("/api/intelligence/cameras", headers=demo).json()["cameras"], [])
            self.assertEqual(self.client.post("/api/intelligence/cameras", json=camera(), headers=demo).status_code, 401)

    def test_replay_requires_observed_and_recorded_availability_and_withholds_media(self):
        from src.portwatch_os.intelligence import cameras as camera_module
        recorded = world_now()
        replay = recorded-timedelta(days=4)
        self.client.post("/api/intelligence/cameras", json={**camera(), "mediaUrl": "https://private.test.invalid/feed"}, headers=PORT)
        evidence = {"id": "later-record", "cameraId": "jnpa-berth-1", "observedAt": (replay-timedelta(hours=1)).isoformat(),
                    "kind": "berth_occupied", "confidence": .8, "summary": "Backdated observation", "source": "Operator"}
        self.client.post("/api/intelligence/camera-evidence", json=evidence, headers=PORT)
        with patch.object(camera_module, "world_now", return_value=replay), patch.object(intelligence, "get_clock", return_value=Mock(state=Mock(mode="HISTORICAL_MISSION"))):
            result = self.client.get("/api/intelligence/cameras", headers=PORT).json()
        self.assertEqual(result["evidence"], [])
        self.assertIsNone(result["cameras"][0]["mediaUrl"])
        self.assertEqual(result["cameras"][0]["mediaAvailability"], "HISTORICAL_UNAVAILABLE")
        with patch.object(camera_module, "world_now", return_value=recorded+timedelta(minutes=1)):
            self.assertEqual(len(self.registry.evidence({"jnpa-berth-1"})), 1)

    def test_forecast_variable_is_filtered_before_limit_across_all_ports(self):
        import pandas as pd
        from src.portwatch_os.learning.weather_feedback import WeatherFeedback
        from src.utils import port_registry
        issue = world_now()-timedelta(hours=1)
        target = issue.replace(hour=0, minute=0, second=0, microsecond=0)
        feedback = WeatherFeedback(self.ledger)
        ports = port_registry.all_ports()
        wind = pd.DataFrame([{"port_id": p.locode, "date": (target+timedelta(days=d)).date().isoformat(), "wind_speed": 17}
                             for p in ports for d in range(1, 6)])
        wave = wind.drop(columns="wind_speed").assign(wave_height=2)
        feedback.record_frame(wind, issued_at=issue, provider="test", source_state="LIVE", now=issue)
        feedback.record_frame(wave, issued_at=issue+timedelta(minutes=1), provider="test", source_state="LIVE", now=issue+timedelta(minutes=1))
        result = self.client.get("/api/weather/feedback?variable=wind_speed&limit=60", headers=ADMIN).json()
        self.assertEqual(len(result["forecasts"]), 60)
        self.assertTrue(all(r["variable"] == "wind_speed" for r in result["forecasts"]))
        self.assertEqual(result["matchingForecasts"], len(ports)*5)
        with patch("backend.app.routes.global_eye._load_events", side_effect=HTTPException(503, "offline")):
            response = self.client.get("/api/intelligence/context?weatherVariable=wind_speed", headers=ADMIN)
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual({r["portCode"] for r in response.json()["weatherFeedback"]["forecasts"]}, {p.locode for p in ports})

    def test_public_camera_is_visible_without_granting_write_access(self):
        self.client.post("/api/intelligence/cameras", json=camera(access="public"), headers=PORT)
        self.assertEqual(len(self.client.get("/api/intelligence/cameras", headers=COMPANY).json()["cameras"]), 1)
        self.assertEqual(self.client.post("/api/intelligence/cameras", json=camera(access="public"), headers=COMPANY).status_code, 403)

    def test_camera_feed_credentials_and_unknown_ports_are_refused(self):
        for url in ("http://example.com/feed", "https://user:secret@example.com/feed", "javascript:alert(1)"):
            result = self.client.post("/api/intelligence/cameras", json={**camera(), "mediaUrl": url}, headers=ADMIN)
            self.assertEqual(result.status_code, 422)
        self.assertEqual(self.client.get("/api/intelligence/context?portCode=UNKNOWN", headers=ADMIN).status_code, 404)

    def test_camera_evidence_preserves_coverage_confidence_and_review(self):
        self.client.post("/api/intelligence/cameras", json=camera(), headers=PORT)
        evidence = {"id": "observation-1", "cameraId": "jnpa-berth-1", "observedAt": (world_now()-timedelta(minutes=5)).isoformat(),
                    "kind": "berth_occupied", "confidence": .8, "summary": "Visible berth appears occupied", "source": "Operator review"}
        self.assertEqual(self.client.post("/api/intelligence/camera-evidence", json=evidence, headers=OTHER_PORT).status_code, 403)
        result = self.client.post("/api/intelligence/camera-evidence", json=evidence, headers=PORT)
        self.assertEqual(result.status_code, 200)
        self.assertEqual(result.json()["operationalUse"], "needs_review")
        self.assertEqual(result.json()["coverage"], camera()["coverage"])
        self.assertEqual(self.client.post("/api/intelligence/camera-evidence", json=evidence, headers=PORT).status_code, 409)
        self.assertEqual(self.client.get("/api/intelligence/cameras", headers=OTHER_PORT).json()["evidence"], [])

    def test_weather_observation_rejects_forecasts_and_cross_port_writes(self):
        body = {"portCode": "INNSA", "variable": "wind_speed", "validAt": "2025-06-02T00:00:00Z",
                "availableAt": "2025-06-03T00:00:00Z", "value": 14, "source": "JNPA station", "kind": "station", "unit": "kn", "statistic": "maximum"}
        self.assertEqual(self.client.post("/api/weather/observations", json=body, headers=OTHER_PORT).status_code, 403)
        self.assertEqual(self.client.post("/api/weather/observations", json={**body, "kind": "forecast"}, headers=PORT).status_code, 422)
        self.assertEqual(self.client.post("/api/weather/observations", json={**body, "statistic": "mean"}, headers=PORT).status_code, 422)
        self.assertEqual(self.client.post("/api/weather/observations", json=body, headers=PORT).status_code, 200)

    def test_registry_survives_reopen_and_refuses_corruption(self):
        from src.portwatch_os.ledger.store import LedgerError
        self.client.post("/api/intelligence/cameras", json=camera(), headers=PORT)
        self.assertEqual(len(CameraRegistry(self.registry.path).cameras()), 1)
        self.registry.path.write_bytes(b"not sqlite")
        with self.assertRaises(LedgerError):
            self.registry.cameras()

    def test_earthquake_failure_keeps_original_snapshot_time_then_expires(self):
        import requests
        original = world_now()
        payload = {"type": "FeatureCollection", "features": [], "portwatch": {"status": "LIVE", "fetchedAt": original.isoformat(), "source": "USGS"}}
        with patch.dict(intelligence._QUAKES, {"at": original, "payload": payload}, clear=True), patch("requests.get", side_effect=requests.RequestException("offline")):
            with patch.object(intelligence, "world_now", return_value=original+timedelta(minutes=10)):
                response = self.client.get("/api/intelligence/earthquakes", headers=ADMIN)
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json()["portwatch"]["status"], "STALE")
            self.assertEqual(response.json()["portwatch"]["fetchedAt"], original.isoformat())
            with patch.object(intelligence, "world_now", return_value=original+timedelta(hours=2)):
                self.assertEqual(self.client.get("/api/intelligence/earthquakes", headers=ADMIN).status_code, 503)

    def test_historical_economic_context_does_not_assume_publication_vintages(self):
        from src.portwatch_os.intelligence import context
        with patch.object(context, "get_clock", return_value=Mock(state=Mock(mode="HISTORICAL_MISSION"))):
            quotes = context.economic_context(Path(self.tmp.name))
        self.assertTrue(all(q["value"] is None and q["status"] == "UNAVAILABLE" for q in quotes))
