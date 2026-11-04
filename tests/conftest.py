"""Opt-in fixtures for tests of compatibility endpoints."""

from datetime import timedelta

import pytest


@pytest.fixture
def asserted_api(monkeypatch):
    """Exercise legacy header-based requests while verified suites keep their own mode."""
    monkeypatch.setenv("PORTWATCH_IDENTITY_MODE", "asserted")


@pytest.fixture
def fictional_fleet(monkeypatch):
    """Supply carrier data for tests whose assertions concern downstream policy."""
    from backend.app.domains.voyages import company
    from src.portwatch_os.fleet.company import demo_company

    profile = demo_company()
    monkeypatch.setattr(company, "resolve_company", lambda company_id=None: profile)
    return profile


@pytest.fixture
def red_sea_evidence(monkeypatch, fictional_fleet):
    """One current event and a fictional carrier still short of its chokepoint."""
    from backend.app.domains.system import agents
    from backend.app.services import cache_service
    from src.portwatch_os.agents import portwatch_tools
    from src.portwatch_os.clock import world_now
    from src.portwatch_os.world.live import reset_live_world

    issued = (world_now() - timedelta(hours=1)).isoformat()
    bundle = {"events": [
        {"title": "Bab el-Mandeb closed to all vessel traffic", "source": f"fixture-{outlet}.invalid",
         "timestamp": issued, "category": "chokepoint_disruption", "chokepoint": "BAB_EL_MANDEB",
         "region": "Red Sea", "severity": 0.95}
        for outlet in range(5)
    ]}
    hull = next(vessel for vessel in fictional_fleet.vessels if vessel.lane_code == "EUR_IND")
    hull.hours_to_chokepoint["BAB_EL_MANDEB"] = 12.0
    monkeypatch.setattr(cache_service, "get_news_bundle", lambda: bundle)
    read_cache = portwatch_tools._read_cache
    monkeypatch.setattr(portwatch_tools, "_read_cache",
                        lambda name: bundle if name == "news_bundle.json" else read_cache(name))
    monkeypatch.setattr(portwatch_tools, "demo_company", lambda: fictional_fleet)
    monkeypatch.setattr(agents, "_COMMAND", None)
    reset_live_world()
    yield
    reset_live_world()


@pytest.fixture
def scenario_forecast(tmp_path, monkeypatch):
    """Real scenario arithmetic against the existing deterministic forecast fixture."""
    from backend.app.domains.voyages import scenarios
    from tests.test_decision_and_scenarios import _forecast

    file = tmp_path / "forecast.csv"
    _forecast().to_csv(file, index=False)
    monkeypatch.setattr(scenarios, "FORECAST_PATH", file)
    for key in ("PANEL_PATH", "REGIME_PATH", "WEATHER_PATH"):
        monkeypatch.setattr(scenarios, key, tmp_path / key)
    scenarios._load.cache_clear()
    yield
    scenarios._load.cache_clear()
