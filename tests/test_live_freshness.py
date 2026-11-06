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
