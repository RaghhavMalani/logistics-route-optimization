from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import pytest
from src.portwatch_os.freshness.candidate_weather import summarize
from src.portwatch_os.freshness.gdelt_bigquery import reserve, SQL


def test_daily_budget_is_atomic_and_failed_reservations_cannot_spend(tmp_path):
    path = tmp_path / 'budget.sqlite3'
    def attempt(_):
        try:
            reserve(path, 'test-project', '2026-11-06', 60, 100)
            return True
        except ValueError:
            return False
    with ThreadPoolExecutor(max_workers=4) as workers:
        assert sum(workers.map(attempt, range(4))) == 1
    reserve(path, 'test-project', '2026-11-07', 100, 100)
    assert '_PARTITIONTIME >=' in SQL and '_PARTITIONTIME <' in SQL


def test_bigquery_is_disabled_without_a_cost_cap(monkeypatch):
    from src.portwatch_os.freshness.gdelt_bigquery import collect
    monkeypatch.setenv('PORTWATCH_BIGQUERY_DAILY_BYTE_CAP', '')
    with pytest.raises(ValueError, match='explicit project'):
        collect()


def test_forecast_members_require_real_finite_coverage():
    response = {'hourly': {'time': ['2026-11-06T12:00'], 'wind_speed_10m': [5],
                           'wind_speed_10m_member01': [None]}}
    with pytest.raises(ValueError, match='finite coverage'):
        summarize(response, 'ensemble')
    response['hourly']['wind_speed_10m_member01'] = [7]
    assert summarize(response, 'ensemble')['finiteValues'] == {'wind_speed_10m': 1, 'wind_speed_10m_member01': 1}


def test_trial_window_is_fixed_and_resumable(monkeypatch):
    from src.portwatch_os.freshness import source_trials
    monkeypatch.setenv('PORTWATCH_SOURCE_TRIAL_START', '2026-11-06T12:00:00+00:00')
    monkeypatch.setenv('PORTWATCH_SOURCE_TRIAL_PRODUCTS', 'frankfurter-ecb-fx')
    monkeypatch.setattr(source_trials, 'wall_now', lambda: datetime(2026, 11, 7, tzinfo=timezone.utc))
    a, b = source_trials.configured(), source_trials.configured()
    assert a == b and a['end'].isoformat() == '2026-11-08T12:00:00+00:00'


def test_missing_currents_remain_null_while_wave_coverage_is_measured():
    hourly = {'time': ['2026-11-06T12:00'], 'wave_height': [1.2], 'swell_wave_height': [0.8],
              'ocean_current_velocity': [None], 'ocean_current_direction': [None]}
    result = summarize({'hourly': hourly}, 'marine')
    assert result['finiteValues']['ocean_current_velocity'] == 0
    assert result['hourly']['ocean_current_velocity'] == [None]
    assert result['hourly']['wave_height'] == [1.2]


def test_reviewed_products_collect_in_a_separate_scope_after_trial(monkeypatch, tmp_path):
    import asyncio

    from src.portwatch_os.freshness import source_trials, source_worker

    product = 'open-meteo-ensemble'
    monkeypatch.setenv('PORTWATCH_SOURCE_TRIAL_START', '2026-11-06T18:00:34+00:00')
    monkeypatch.setenv('PORTWATCH_SOURCE_TRIAL_PRODUCTS', product)
    monkeypatch.setenv('PORTWATCH_PUBLISH_REVIEWED_SOURCES', f'{product},nho-navarea-viii')
    monkeypatch.setenv('PORTWATCH_SOURCE_SNAPSHOT_URL', f'sqlite:///{(tmp_path / "sources.db").as_posix()}')
    monkeypatch.setenv('PORTWATCH_LICENCE_MODE', 'DEMO')
    monkeypatch.setattr(source_trials, 'wall_now', lambda: datetime(2026, 11, 11, tzinfo=timezone.utc))
    calls = []

    async def record_jobs(store, jobs, *, until=None):
        calls.append(([(job.product.product_id, job.scope) for job in jobs], until))

    monkeypatch.setattr(source_worker, 'run_worker', record_jobs)
    asyncio.run(source_trials.run())
    assert calls == [([(product, 'published')], None)]
