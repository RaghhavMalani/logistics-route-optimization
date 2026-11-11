from datetime import datetime, timedelta, timezone

import requests

from src.portwatch_os.freshness.publication_lag import imf_publication_lag
from src.portwatch_os.freshness.truth import classify, classify_daily_activity

NOW = datetime(2026, 11, 6, 18, tzinfo=timezone.utc)


def test_expired_forecast_is_stale_even_with_a_recent_export():
    current_receipt = (NOW - timedelta(minutes=2)).isoformat()
    state, age = classify(current_receipt, NOW, 3600, valid_through='2026-10-12T00:00:00Z')
    assert state == 'stale' and age == 120
    assert classify('2026-10-02T00:00:00Z', NOW, 72 * 3600)[0] == 'stale'
    assert classify((NOW + timedelta(hours=1)).isoformat(), NOW, 3600)[0] == 'unavailable'


def test_lag_uses_distinct_observation_days_and_excludes_expired_forecasts():
    now = datetime(2026, 11, 11, 16, tzinfo=timezone.utc)
    lag = imf_publication_lag(now, [
        ("2026-10-30T00:00:00Z", "2026-11-10T00:00:00Z"),
        ("2026-11-06T00:00:00Z", "2026-11-11T12:00:00Z"),
        ("2026-11-12T00:00:00Z", "2026-11-12T02:00:00Z"),
    ])
    assert lag["samples"] == 2
    assert 161 * 3600 <= lag["medianSeconds"] < 162 * 3600
    observed = "2026-11-06T00:00:00Z"
    assert classify_daily_activity(observed, now, lag)[0] == "expected_lag"
    assert classify_daily_activity(observed, now, lag, valid_through="2026-11-11T00:00:00Z")[0] == "stale"
    assert classify_daily_activity(observed, now + timedelta(days=2), lag)[0] == "stale"
    assert classify_daily_activity("2026-11-11T00:00:00Z", now, lag)[0] == "live"


def test_upstream_staleness_is_data_degradation_only(tmp_path, monkeypatch):
    from backend.app.domains.system import health
    from backend.app.domains.intelligence import source_status
    from backend.app.services import cache_service as cache
    path = tmp_path / 'forecast.json'
    path.write_text('{}')
    monkeypatch.setattr(cache, 'FORECAST_CACHE', path)
    monkeypatch.setattr(health, 'durable_stores', lambda: {'ok': True})
    monkeypatch.setattr(source_status, 'source_status', lambda: {'degraded': True, 'sources': [
        {'id': 'congestion-forecast', 'status': 'stale', 'core': True},
        {'id': 'weather', 'status': 'live', 'core': True}], 'scheduler': {}})
    monkeypatch.setattr(requests.sessions.Session, 'request', lambda *a, **kw: (_ for _ in ()).throw(AssertionError('Health fetched a provider')))
    payload = health.health_check()
    assert payload['status'] == payload['service']['status'] == 'ok'
    assert payload['data']['status'] == 'degraded'
    assert [source['status'] for source in payload['data']['sources']] == ['stale', 'current']
    assert payload['intelligence'] == 'degraded'
    assert payload['sourceHealth']['sources'][0]['status'] == 'stale'


def test_successful_collection_updates_lag_without_a_forecast_run(tmp_path, monkeypatch):
    from types import SimpleNamespace

    import pandas as pd
    from app.data import portwatch
    from src.portwatch_os import clock, freshness
    from src.portwatch_os.freshness.journal import FreshnessJournal

    journal = FreshnessJournal(tmp_path / "freshness.sqlite3")
    observed = datetime(2026, 11, 8, tzinfo=timezone.utc)
    received = datetime(2026, 11, 11, 16, tzinfo=timezone.utc)
    data = pd.DataFrame([{"portid": "port883", "date": int(observed.timestamp() * 1000),
                          "portcalls": 5, "import": 0, "export": 0}])
    monkeypatch.setattr(portwatch, "CACHE", tmp_path)
    monkeypatch.setattr(portwatch, "_query", lambda *a, **kw: data.copy())
    monkeypatch.setattr(clock, "wall_now", lambda: received)
    monkeypatch.setattr(freshness, "get_coordinator", lambda: SimpleNamespace(journal=journal))

    baseline = imf_publication_lag(received, journal.publication_receipts())
    portwatch.fetch_port_activity(strict=True)
    portwatch.fetch_port_activity(strict=True)
    receipts = journal.publication_receipts()
    assert len(receipts) == 2
    refreshed = imf_publication_lag(received, receipts)
    assert refreshed["samples"] == baseline["samples"] + 1
    assert refreshed["medianSeconds"] < baseline["medianSeconds"]


def test_service_faults_remain_degraded_with_current_data(monkeypatch):
    from backend.app.domains.system.health import service_health
    from src.portwatch_os.freshness.write_health import failed_writes, record_write

    production = {"environment": "production"}
    scheduler = {"running": True, "singleOwner": True, "tickSeconds": 5, "lastTickAt": NOW}
    capacity = {"status": "ok"}
    monkeypatch.setenv("PORTWATCH_FRESHNESS_SCHEDULER", "0")
    assert service_health(NOW, production, {"ok": True}, capacity, scheduler, [])["status"] == "ok"
    record_write("test-writer", ok=False)
    try:
        assert service_health(
            NOW + timedelta(seconds=61), production, {"ok": False},
            {"status": "low"}, scheduler, failed_writes(),
        )["reasons"] == ["scheduler", "durable_stores", "state_capacity", "state_writes"]
    finally:
        record_write("test-writer", ok=True)


def test_existing_workspace_stream_carries_public_freshness_without_provider_calls(monkeypatch):
    import asyncio
    from types import SimpleNamespace
    from backend.app.domains.advisories import handoffs
    from backend.app.domains.intelligence import source_status
    from backend.app import auth_store
    from backend.app.identity import Identity, current_identity
    from src.portwatch_os.sandbox import current_sandbox
    who = Identity('NATIONAL_ADMIN', actor='reader', verified=True)
    user = {'id': 'reader', 'role': 'NATIONAL_ADMIN', 'organisation': None, 'portCode': None,
            'portCodes': [], 'vesselIds': []}
    monkeypatch.setattr(auth_store, 'get_auth_store', lambda: SimpleNamespace(session=lambda credential: {'user': user}))
    monkeypatch.setattr(handoffs, 'handoffs', lambda: {'items': []})
    monkeypatch.setattr(source_status, 'source_status', lambda: {'checkedAt': NOW,
        'sources': [{'id': 'weather', 'status': 'stale', 'dataAgeSeconds': 7200}]})
    monkeypatch.setattr(requests.sessions.Session, 'request', lambda *a, **kw: (_ for _ in ()).throw(AssertionError('Stream fetched a provider')))
    class Request:
        headers = {'authorization': 'Bearer private-session-token'}
        async def is_disconnected(self):
            return False
    async def read():
        response = await handoffs.handoff_stream(Request())
        iterator = response.body_iterator
        first, second = await anext(iterator), await anext(iterator)
        await iterator.aclose()
        assert first.startswith('event: handoffs\n')
        assert second.startswith('event: sources\n') and '7200' in second
        assert 'private-session-token' not in first + second
    token = current_identity.set(who)
    sandbox_token = current_sandbox.set(None)
    try:
        asyncio.run(read())
    finally:
        current_identity.reset(token)
        current_sandbox.reset(sandbox_token)
