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
