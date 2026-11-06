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
