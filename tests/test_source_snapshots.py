from datetime import datetime, timedelta, timezone

import pytest

from src.portwatch_os.fabric.products import ProductCatalogue
from src.portwatch_os.freshness.source_snapshots import Snapshot, SnapshotStore
from src.portwatch_os.freshness.source_worker import SourceJob, collect_due


NOW = datetime(2026, 11, 4, tzinfo=timezone.utc)
PRODUCT = "aisstream-websocket"


@pytest.fixture
def store(tmp_path):
    result = SnapshotStore(f"sqlite:///{(tmp_path / 'sources.sqlite').as_posix()}")
    result.initialize()
    return result


def test_health_reads_success_and_lag_from_public_snapshots_only(store):
    store.record("trial-a", PRODUCT, NOW, snapshot=Snapshot({"private": True}, NOW))
    assert store.health("published", PRODUCT, NOW, timedelta(minutes=5))["status"] == "unavailable"
    assert store.latest("published", PRODUCT) is None

    store.record("published", PRODUCT, NOW - timedelta(days=8), error="OldFailure")
    store.record("published", PRODUCT, NOW, snapshot=Snapshot({"reports": 6}, NOW - timedelta(seconds=60)))
    store.record("published", PRODUCT, NOW + timedelta(seconds=60), error="Offline")
    assert store.latest("published", PRODUCT).payload == {"reports": 6}
    assert store.health("published", PRODUCT, NOW + timedelta(minutes=2), timedelta(minutes=5)) == {
        "status": "live",
        "lastSuccess": NOW,
        "observedAt": NOW - timedelta(minutes=1),
        "successRate7d": 0.5,
        "attempts7d": 2,
        "medianLagSeconds": 60.0,
        "lastError": "Offline",
        "lastErrorAt": NOW + timedelta(seconds=60),
    }
    assert store.health("published", PRODUCT, NOW + timedelta(days=8), timedelta(minutes=5)) == {
        "status": "stale",
        "lastSuccess": NOW,
        "observedAt": NOW - timedelta(minutes=1),
        "successRate7d": None,
        "attempts7d": 0,
        "medianLagSeconds": None,
        "lastError": "Offline",
        "lastErrorAt": NOW + timedelta(seconds=60),
    }


def test_undated_snapshot_and_future_timestamp(store):
    store.record("published", PRODUCT, NOW, snapshot=Snapshot({}, None))
    assert store.health("published", PRODUCT, NOW, timedelta(days=1))["status"] == "stale"
    assert store.health("published", PRODUCT, NOW, timedelta(days=1))["medianLagSeconds"] is None
    with pytest.raises(ValueError, match="future"):
        store.record("published", PRODUCT, NOW, snapshot=Snapshot({}, NOW + timedelta(seconds=1)))


def test_worker_persists_breaker_and_preserves_last_good_after_failure(store):
    _, product = ProductCatalogue().product(PRODUCT)
    now = NOW
    offline = False

    def fetch():
        if offline:
            raise OSError("credential or provider body goes here")
        return Snapshot({"reports": 1}, now)

    def clock():
        return now

    job = SourceJob(product, fetch, timedelta(minutes=1), "trial-a", trial_permitted=True)
    assert collect_due(store, job, clock)
    assert not collect_due(store, job, clock)
    offline = True
    now += timedelta(minutes=1)
    assert collect_due(store, job, clock)
    now += timedelta(seconds=29)
    assert not collect_due(store, job, clock)
    now += timedelta(seconds=1)
    assert collect_due(store, job, clock)
    now += timedelta(seconds=60)
    assert collect_due(store, job, clock)
    assert store.latest("trial-a", PRODUCT).observed_at == NOW
    assert store.attempts("trial-a", PRODUCT, limit=1)[0].error == "OSError"

    restarted = SnapshotStore(str(store.engine.url))
    now += timedelta(minutes=14)
    assert not collect_due(restarted, job, clock)
    now += timedelta(minutes=1)
    offline = False
    assert collect_due(restarted, job, clock)
    assert store.latest("trial-a", PRODUCT).observed_at == now
    assert not collect_due(restarted, job, clock)


def test_source_job_needs_explicit_trial_permission_or_publication_approval():
    _, product = ProductCatalogue().product(PRODUCT)
    with pytest.raises(ValueError, match="Trial collection"):
        SourceJob(product, lambda: Snapshot({}, NOW), timedelta(minutes=1), "trial-a")
    with pytest.raises(ValueError, match="Publication"):
        SourceJob(product, lambda: Snapshot({}, NOW), timedelta(minutes=1), "published", publication_approved=True)
