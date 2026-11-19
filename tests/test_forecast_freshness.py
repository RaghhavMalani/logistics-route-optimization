from datetime import datetime, timedelta, timezone
from copy import deepcopy

from src.portwatch_os.intelligence import current_environment as weather
from src.portwatch_os.intelligence.forecast_freshness import describe

NOW = datetime(2026, 11, 19, 10, tzinfo=timezone.utc)


def snapshot():
    return {"kind": "surface", "availableAt": (NOW - timedelta(hours=5)).isoformat(),
            "lastSuccessfulCheckAt": NOW.isoformat(), "rows": [{"validAt": NOW.isoformat(),
            **{field: 1 for field in weather.SURFACE_UNITS}}]}


def test_unchanged_latest_forecast_stays_current_within_model_interval():
    source = snapshot()
    clocks = describe(source, NOW)
    assert clocks["status"] == "CURRENT"
    assert clocks["forecastIssuedAt"] == source["availableAt"]
    assert clocks["checkedAt"] == NOW.isoformat()
    assert clocks["forecastIssueBasis"] == "VALUES_LAST_CHANGED"
    assert clocks["latestAvailable"] is True


def test_successful_checks_cannot_hide_old_issue_or_invalid_coverage():
    source = snapshot()
    source["availableAt"] = (NOW - timedelta(hours=8, seconds=1)).isoformat()
    assert describe(source, NOW)["status"] == "STALE"
    source = snapshot()
    source["rows"][0]["visibility"] = None
    assert describe(source, NOW)["status"] == "STALE"
    source = snapshot()
    source["lastSuccessfulCheckAt"] = (NOW - timedelta(minutes=90, seconds=1)).isoformat()
    assert describe(source, NOW)["status"] == "STALE"
    assert describe(source, NOW)["latestAvailable"] is False


def test_future_receipts_and_issue_proxies_are_rejected():
    for key in ("availableAt", "lastSuccessfulCheckAt"):
        source = snapshot()
        source[key] = (NOW + timedelta(seconds=1)).isoformat()
        assert describe(source, NOW)["status"] == "STALE"


def test_same_values_preserve_issue_proxy_and_changed_values_advance_it(tmp_path, monkeypatch):
    monkeypatch.setattr(weather, "ROOT", tmp_path)
    monkeypatch.setattr(weather, "world_now", lambda: NOW)
    previous = snapshot()
    previous.update(units=weather.SURFACE_UNITS, returnedGrid={"latitude": 19, "longitude": 73})
    port = weather.port_registry.resolve("INNSA")
    def save(rows):
        return weather._save_snapshot("surface", port, previous, {}, rows, previous["units"],
                                      previous["returnedGrid"], b"original", NOW, digest="fixture")
    same = save(previous["rows"])
    assert same["forecastIssuedAt"] == previous["availableAt"]
    assert same["issuedAt"] is None
    assert same["checkedAt"] == NOW.isoformat()
    changed = deepcopy(previous["rows"])
    changed[0]["precipitation"] = 5
    assert save(changed)["forecastIssuedAt"] == NOW.isoformat()


def test_changed_response_metadata_cannot_advance_a_marine_issue_proxy(tmp_path, monkeypatch):
    monkeypatch.setattr(weather, "ROOT", tmp_path)
    monkeypatch.setattr(weather, "world_now", lambda: NOW)
    previous = {"kind": "marine", "availableAt": (NOW - timedelta(hours=5)).isoformat(),
                "rows": [{"validAt": NOW.isoformat(), "wave_height": 1.5}],
                "units": {"wave_height": "m"}, "returnedGrid": {"latitude": 19, "longitude": 73},
                "responseSha256": "previous-original"}
    result = weather._save_snapshot("marine", weather.port_registry.resolve("INNSA"),
                                   previous, {}, previous["rows"], previous["units"],
                                   previous["returnedGrid"], b"new-generationtime-ms", NOW)
    assert result["status"] == "CURRENT"
    assert result["responseSha256"] != previous["responseSha256"]
    assert result["forecastIssuedAt"] == previous["availableAt"]
    assert result["checkedAt"] == NOW.isoformat()
