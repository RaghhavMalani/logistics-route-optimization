from datetime import datetime, timedelta, timezone

from src.portwatch_os.freshness.coordinator import RefreshCoordinator
from src.portwatch_os.freshness.journal import FreshnessJournal
from src.portwatch_os.freshness.ownership import OwnerLock
from src.portwatch_os.freshness.job import RefreshJob, JobOutcome
from src.portwatch_os.freshness.policy import FreshnessPolicy, ArtifactProbe

NOW = datetime(2026, 11, 6, 12, tzinfo=timezone.utc)


def job(run):
    return RefreshJob(FreshnessPolicy('source', 'Provider', timedelta(hours=1), timedelta(hours=2),
                                     max_attempts=2, backoff_base=timedelta(seconds=1),
                                     backoff_cap=timedelta(minutes=1)),
                      lambda: ArtifactProbe(NOW - timedelta(days=1)), run)


def test_history_breaker_and_last_good_survive_restart(tmp_path, monkeypatch):
    moment = [NOW]
    monkeypatch.setattr('src.portwatch_os.freshness.coordinator.wall_now', lambda: moment[0])
    journal = FreshnessJournal(tmp_path / 'journal.sqlite')
    coordinator = RefreshCoordinator(journal=journal)
    good = job(lambda ctx: JobOutcome(observed_at=NOW))
    coordinator.register(good)
    coordinator.request('source', reason='first', wait=True)
    def fail(ctx):
        raise TimeoutError('upstream refused')
    good.run = fail
    coordinator.request('source', reason='failure', wait=True)
    moment[0] += timedelta(seconds=3)
    coordinator.request('source', reason='failure', wait=True)
    row = coordinator.describe('source')
    assert row['job']['circuit'] == 'OPEN'
    assert row['job']['lastGood']['observedAt'] == NOW.isoformat(timespec='seconds')
    assert row['job']['successRate7d'] == 1 / 3
    restarted = RefreshCoordinator(journal=FreshnessJournal(journal.path))
    restarted.register(job(fail))
    assert restarted.due() == []
    assert restarted.describe('source')['job']['lastError'] == 'TimeoutError: upstream refused'
    moment[0] += timedelta(minutes=2)
    restarted.request('source', reason='half open', wait=True)
    assert restarted.record('source').last_result.attempt == 1
    assert restarted.describe('source')['job']['lastGood']['observedAt'] == NOW.isoformat(timespec='seconds')


def test_shared_volume_owner_is_exclusive_and_released(tmp_path):
    first = OwnerLock(tmp_path / 'worker.lock')
    second = OwnerLock(tmp_path / 'worker.lock')
    assert first.acquire()
    assert not second.acquire()
    first.release()
    assert second.acquire()
    second.release()


def test_enqueue_never_invokes_collector(tmp_path):
    calls = []
    coordinator = RefreshCoordinator()
    coordinator.register(job(lambda ctx: calls.append(ctx) or JobOutcome(observed_at=NOW)))
    assert coordinator.enqueue('source') == 'queued'
    assert calls == []
    coordinator.tick(wait=True)
    assert len(calls) == 1


def test_error_credentials_and_queries_are_redacted(monkeypatch):
    from src.portwatch_os.freshness.journal import safe_error
    monkeypatch.setenv('AISSTREAM_API_KEY', 'private-ais-secret')
    error = safe_error(RuntimeError('private-ais-secret https://provider.test/feed?key=credential'))
    assert 'private-ais-secret' not in error and 'credential' not in error
    assert 'provider.test/feed' in error


def test_strict_activity_failure_does_not_return_old_csv(tmp_path, monkeypatch):
    from app.data import portwatch
    monkeypatch.setattr(portwatch, 'CACHE', tmp_path)
    retained = tmp_path / 'port_activity.csv'
    retained.write_text('date,portid,portcalls,import,export\n2026-10-02,port776,2,3,4\n')
    before = retained.read_bytes()
    def failed(*args, **kwargs):
        raise TimeoutError('upstream unavailable')
    monkeypatch.setattr(portwatch, '_query', failed)
    import pytest
    with pytest.raises(TimeoutError, match='upstream unavailable'):
        portwatch.fetch_port_activity(days=45, strict=True)
    assert retained.read_bytes() == before


def test_current_weather_does_not_need_research_profile(monkeypatch):
    from src.portwatch_os.freshness.free_research import current_weather_eligibility
    from src.portwatch_os.clock import reset_clock
    reset_clock()
    monkeypatch.delenv('PORTWATCH_RESEARCH_SOURCE_PROFILE', raising=False)
    monkeypatch.delenv('PORTWATCH_LOCAL_PROVIDER_PROFILE', raising=False)
    monkeypatch.setenv('PORTWATCH_LICENCE_MODE', 'DEMO')
    assert current_weather_eligibility() is None
    monkeypatch.setenv('PORTWATCH_LICENCE_MODE', 'COMMERCIAL')
    assert 'not permitted' in current_weather_eligibility()


def test_last_error_survives_the_seven_day_rate_window(tmp_path):
    from src.portwatch_os.freshness.job import RefreshResult
    journal = FreshnessJournal(tmp_path / 'source.sqlite')
    failed = RefreshResult('source', False, NOW, NOW, 1, 'test', error='TimeoutError: unavailable')
    journal.save(failed, NOW + timedelta(minutes=1), 1)
    later = NOW + timedelta(days=8)
    success = RefreshResult('source', True, later, later, 1, 'test', observed_at=later)
    journal.save(success, None, 0)
    metrics = journal.metrics('source', later)
    assert metrics['attempts7d'] == 1 and metrics['successRate7d'] == 1
    assert metrics['lastError'] == 'TimeoutError: unavailable'
    assert metrics['lastErrorAt'] == NOW.isoformat(timespec='seconds')


def test_worker_sees_weather_transport_error_and_retains_snapshot(tmp_path, monkeypatch):
    import requests
    import pytest
    from src.portwatch_os.intelligence import current_environment as weather
    from src.utils import port_registry
    path = tmp_path / 'surface-INNSA.json'
    path.write_text('retained original')
    monkeypatch.setattr(weather, 'ROOT', tmp_path)
    monkeypatch.setattr(weather, 'read', lambda *a, **kw: {'status': 'STALE', 'availableAt': NOW.isoformat(), 'rows': []})
    def offline(*args, **kwargs):
        assert kwargs['timeout'] == (8, 18)
        raise requests.Timeout('provider egress timed out')
    monkeypatch.setattr(weather.requests, 'get', offline)
    with pytest.raises(requests.Timeout, match='egress timed out'):
        weather.refresh('surface', port_registry.PORTS[0], force=True, strict=True)
    assert path.read_text() == 'retained original'


def test_surface_batch_one_request_with_complete_utc_days(tmp_path, monkeypatch):
    import json
    import pytest
    from src.portwatch_os.freshness.job import RetryAfterError
    from src.portwatch_os.intelligence import current_environment as weather
    from src.portwatch_os.intelligence.surface_transport import SurfaceResponse
    from src.utils.port_registry import PORTS

    monkeypatch.setattr(weather, "ROOT", tmp_path)
    monkeypatch.setattr(weather, "wall_now", lambda: NOW)
    monkeypatch.setattr(weather, "world_now", lambda: NOW)
    ports = PORTS[:2]
    hour = NOW.replace(minute=0, second=0, microsecond=0).isoformat()
    payload = [
        {"latitude": port.lat, "longitude": port.lon, "hourly_units": weather.SURFACE_UNITS,
         "hourly": {"time": [hour], **{name: [1.0] for name in weather.SURFACE_UNITS}}}
        for port in ports
    ]
    calls = []
    response = SurfaceResponse(200, None, json.dumps(payload).encode())
    def fetch(params):
        calls.append(params)
        return response

    monkeypatch.setattr(weather.SURFACE_TRANSPORT, "fetch", fetch)
    rows = weather.refresh_surface_batch(ports)
    assert set(rows) == {port.locode for port in ports}
    assert len(calls) == 1
    assert calls[0]["forecast_days"] == 6
    assert calls[0]["latitude"] == ",".join(str(port.lat) for port in ports)
    originals = list((tmp_path / "archive").glob("*.response"))
    assert len(originals) == 1 and originals[0].read_bytes() == response.content

    response = SurfaceResponse(429, "1200", b"")
    with pytest.raises(RetryAfterError) as throttled:
        weather.refresh_surface_batch(ports)
    assert throttled.value.retry_at == NOW + timedelta(minutes=20)
    assert weather.read("surface", ports[0], at=NOW)["snapshotId"] == rows[ports[0].locode]["snapshotId"]


def test_surface_groups_keep_good_ports_and_bound_connect_retries(monkeypatch):
    from collections import Counter
    from src.portwatch_os.intelligence import current_environment as weather
    from src.portwatch_os.intelligence.surface_transport import SurfaceConnectTimeout, SurfaceTransportError
    from src.utils.port_registry import PORTS

    calls = Counter()
    group_starts = [port.locode for port in PORTS[:4]]

    def collect(group):
        first = group[0].locode
        calls[first] += 1
        if first == group_starts[0]:
            raise SurfaceConnectTimeout()
        if first == group_starts[1]:
            raise SurfaceTransportError("http_timeout")
        return {port.locode: {} for port in group}

    monkeypatch.setattr(weather, "refresh_surface_batch", collect)
    monkeypatch.setattr(weather, "sleep", lambda _: None)
    rows, failures, attempts = weather.collect_surface_groups(PORTS, NOW, force=True)
    assert list(calls.values()) == [5, 1, 1, 1]
    assert set(rows) == {port.locode for port in (*PORTS[2::4], *PORTS[3::4])}
    assert attempts == {"connect_timeout": 5, "http_timeout": 1, "ok": 2}
    assert [type(error) for error in failures] == [SurfaceConnectTimeout, SurfaceTransportError]


def test_surface_groups_skip_checked_ports_and_stop_at_429(monkeypatch):
    from src.portwatch_os.freshness.job import RetryAfterError
    from src.portwatch_os.intelligence import current_environment as weather
    from src.utils.port_registry import PORTS

    calls = []
    deadline = NOW + timedelta(minutes=20)

    def collect(group):
        calls.append(group[0].locode)
        raise RetryAfterError("Open-Meteo surface HTTP 429", deadline)

    checked = {port.locode for port in PORTS[::4]}
    monkeypatch.setattr(weather, "read", lambda kind, port, **kw:
                        {"lastSuccessfulCheckAt": NOW.isoformat()} if port.locode in checked else {})
    monkeypatch.setattr(weather, "refresh_surface_batch", collect)
    rows, failures, attempts = weather.collect_surface_groups(PORTS, NOW)
    assert calls == [PORTS[1].locode]
    assert not rows
    assert attempts == {"HTTP 429": 1}
    assert failures[0].retry_at == deadline


def test_retry_after_sets_a_durable_minimum_wait(tmp_path):
    from src.portwatch_os.freshness.job import RetryAfterError
    from src.portwatch_os.freshness.coordinator import RefreshCoordinator
    from src.portwatch_os.freshness.journal import FreshnessJournal
    from src.portwatch_os.freshness.job import RefreshJob
    from src.portwatch_os.freshness.policy import ArtifactProbe, FreshnessPolicy
    from src.portwatch_os.clock import wall_now

    deadline = wall_now() + timedelta(hours=2)
    def collect(context):
        raise RetryAfterError("Open-Meteo surface HTTP 429", deadline, detail={"httpAttempts": {"HTTP 429": 1}})

    artifact = "current_surface_batch"
    job = RefreshJob(FreshnessPolicy(artifact, "Open-Meteo", timedelta(hours=1),
                                   timedelta(hours=2)), lambda: ArtifactProbe(), collect)
    journal = FreshnessJournal(tmp_path / "journal.sqlite3")
    first = RefreshCoordinator(journal=journal)
    first.register(job)
    first.request(artifact, reason="test", wait=True)
    assert first.record(artifact).next_attempt_at == deadline
    restarted = RefreshCoordinator(journal=journal)
    restarted.register(job)
    assert artifact not in restarted.due(now=deadline - timedelta(seconds=1))
    assert artifact in restarted.due(now=deadline)
    assert journal.recent_outcomes(artifact, wall_now(), hours=48)["http429"] == 1
    assert journal.load(artifact)[1][-1]["detail"] == {"httpAttempts": {"HTTP 429": 1}}
