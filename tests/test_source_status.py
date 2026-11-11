from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient
import requests

from backend.app.domains.intelligence import source_status
from backend.app.main import app
from src.portwatch_os.freshness.source_snapshots import Snapshot, SnapshotStore


def test_public_source_status_uses_only_retained_metadata(tmp_path, monkeypatch):
    now = datetime(2026, 11, 4, 15, tzinfo=timezone.utc)
    product = "frankfurter-ecb-fx"
    store = SnapshotStore(f"sqlite:///{(tmp_path / 'sources.db').as_posix()}")
    store.initialize()
    store.record("trial-proof", product, now, snapshot=Snapshot({"secret": "trial sample"}, now))
    monkeypatch.setattr(source_status, "configured_store", lambda: store)
    monkeypatch.setattr(source_status, "wall_now", lambda: now)
    monkeypatch.setattr(source_status.free_sources, "ROOT", tmp_path)
    monkeypatch.setenv("PORTWATCH_IDENTITY_MODE", "REQUIRED")

    def unexpected(*args, **kwargs):
        raise AssertionError("Public health attempted to fetch a provider")

    monkeypatch.setattr(requests.sessions.Session, "request", unexpected)
    client = TestClient(app)
    reply = client.get("/api/public/sources")
    assert reply.status_code == 200
    row = next(row for row in reply.json()["sources"] if row["id"] == product)
    assert row["status"] == "unavailable" and row["successRate7d"] is None
    assert "trial sample" not in reply.text

    monkeypatch.setitem(source_status.PUBLISHED_MAX_AGE, product, timedelta(days=1))
    monkeypatch.setenv("PORTWATCH_PUBLISH_REVIEWED_SOURCES", product)
    store.record("published", product, now, snapshot=Snapshot({"secret": "published payload"}, now - timedelta(hours=1)))
    reply = client.get("/api/public/sources")
    row = next(row for row in reply.json()["sources"] if row["id"] == product)
    assert row["status"] == "live" and row["successRate7d"] == 1 and row["medianLagSeconds"] == 3600
    assert "published payload" not in reply.text


def test_modelled_readings_require_a_published_fresh_snapshot(tmp_path, monkeypatch):
    from src.portwatch_os.freshness.candidate_weather import summarize

    now = datetime(2026, 11, 11, 15, 30, tzinfo=timezone.utc)
    product = "open-meteo-marine-extended"
    store = SnapshotStore(f"sqlite:///{(tmp_path / 'sources.db').as_posix()}")
    store.initialize()
    hourly = {"time": ["2026-11-11T15:00", "2026-11-11T16:00"],
              "wave_height": [1.2, 1.4], "swell_wave_height": [0.8, 0.9],
              "ocean_current_velocity": [None, None], "ocean_current_direction": [None, None]}
    sample = Snapshot({"availableAt": now.isoformat(), "ports": {
        "INPRT": summarize({"hourly": hourly, "hourly_units": {"wave_height": "m"}}, "marine"),
        "INCCU": {"error": "ValueError"},
    }}, None)
    store.record("trial-private", product, now, snapshot=sample)
    monkeypatch.setattr(source_status, "configured_store", lambda: store)
    monkeypatch.setattr(source_status, "wall_now", lambda: now)
    monkeypatch.setenv("PORTWATCH_PUBLISH_REVIEWED_SOURCES", product)
    monkeypatch.setenv("PORTWATCH_LICENCE_MODE", "DEMO")
    client = TestClient(app)
    path = f"/api/public/source-readings/{product}"
    assert client.get(path).json() == []

    store.record("published", product, now, snapshot=sample)
    row, = client.get(path).json()
    assert row["label"] == "INPRT" and row["validAt"] == "2026-11-11T15:00:00Z"
    assert row["values"][0]["value"] == "1.2" and row["values"][2]["value"] is None
    sources = client.get("/api/public/sources").json()["sources"]
    health = next(row for row in sources if row["id"] == product)
    assert health["status"] == "live" and health["observedAt"] is None
    assert (health["portsCurrent"], health["portsTotal"]) == (1, 2)

    monkeypatch.setenv("PORTWATCH_LICENCE_MODE", "COMMERCIAL")
    assert client.get(path).json() == []
    monkeypatch.setenv("PORTWATCH_LICENCE_MODE", "DEMO")
    now += timedelta(hours=1)
    assert client.get(path).json() == []
