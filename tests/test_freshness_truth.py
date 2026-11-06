from datetime import datetime, timedelta, timezone

import requests

from src.portwatch_os.freshness.truth import classify

NOW = datetime(2026, 11, 6, 18, tzinfo=timezone.utc)


def test_expired_forecast_is_stale_even_with_a_recent_export():
    current_receipt = (NOW - timedelta(minutes=2)).isoformat()
    state, age = classify(current_receipt, NOW, 3600, valid_through='2026-10-12T00:00:00Z')
    assert state == 'stale' and age == 120
    assert classify('2026-10-02T00:00:00Z', NOW, 72 * 3600)[0] == 'stale'
    assert classify((NOW + timedelta(hours=1)).isoformat(), NOW, 3600)[0] == 'unavailable'


def test_health_cannot_be_green_only_because_forecast_file_exists(tmp_path, monkeypatch):
    from backend.app.domains.system import health
    from backend.app.domains.intelligence import source_status
    from backend.app.services import cache_service as cache
    path = tmp_path / 'forecast.json'
    path.write_text('{}')
    monkeypatch.setattr(cache, 'FORECAST_CACHE', path)
    monkeypatch.setattr(health, 'durable_stores', lambda: {'ok': True})
    monkeypatch.setattr(source_status, 'source_status', lambda: {'degraded': True, 'sources': [
        {'id': 'congestion-forecast', 'status': 'stale', 'core': True}], 'scheduler': {}})
    monkeypatch.setattr(requests.sessions.Session, 'request', lambda *a, **kw: (_ for _ in ()).throw(AssertionError('Health fetched a provider')))
    payload = health.health_check()
    assert payload['status'] == 'degraded'
    assert payload['sourceHealth']['sources'][0]['status'] == 'stale'


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
