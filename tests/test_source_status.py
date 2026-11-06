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
    store.record("published", product, now, snapshot=Snapshot({"secret": "published payload"}, now - timedelta(hours=1)))
    reply = client.get("/api/public/sources")
    row = next(row for row in reply.json()["sources"] if row["id"] == product)
    assert row["status"] == "live" and row["successRate7d"] == 1 and row["medianLagSeconds"] == 3600
    assert "published payload" not in reply.text
