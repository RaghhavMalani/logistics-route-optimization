"""Local role adapters expose research without adopting or editing forecasts."""
from datetime import timedelta

from tests.test_demo_terminal import resources, setup
from tests.test_weather_shadow import NOW, START, add, state
from backend.app.routes.weather_verification import daily_recommendation


def test_shadow_route_filters_asof_and_is_read_only(state, tmp_path, monkeypatch):
    ledger, evidence, root = state
    add(state, variable="wind_gust", horizon=1)
    add(state, variable="wind_speed", horizon=2)
    from src.portwatch_os.intelligence import current_environment as environment
    from backend.app.routes import weather_verification as route
    monkeypatch.setattr(environment, "FEEDBACK_DB", ledger.path)
    monkeypatch.setattr(environment, "ROOT", root)
    monkeypatch.setattr(route, "wall_now", lambda: NOW)
    store, client = setup(tmp_path/"demo", monkeypatch)
    token = store.create("SHIPPING_COMPANY")["accessToken"]
    headers = {"Authorization": "Bearer "+token}
    before = [r.to_row() for r in ledger.predictions(domain="weather")]
    path = "/api/demo/terminal/weather/shadow"
    response = client.get(path, headers=headers)
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["mode"] == "SHADOW_ONLY" and data["decisionEligible"] is False
    assert len(data["contexts"]) == 2
    filtered = client.get(path, headers=headers, params={"portCode":"INNSA", "variable":"wind_gust", "provider":"Open-Meteo surface", "horizon":1})
    assert filtered.status_code == 200, filtered.text
    assert len(filtered.json()["contexts"]) == 1
    assert filtered.json()["contexts"][0]["shadow"]["status"] == "COLLECTING"
    prior = client.get(path, headers=headers, params={"asOf":START.isoformat()})
    assert prior.status_code == 200 and not prior.json()["contexts"]
    for params in ({"asOf":(NOW+timedelta(days=1)).isoformat()}, {"asOf":"2025-06-01"},
                   {"asOf":"0001-01-01T00:00:00+14:00"}, {"provider":"private-operator-source"}, {"portCode":"FOREIGN"}, {"horizon":-1}):
        assert client.get(path, headers=headers, params=params).status_code == 422
    assert before == [r.to_row() for r in ledger.predictions(domain="weather")]
    assert client.post(path, headers=headers, json={"adopt":True}).status_code in (404,405)
    client.close(); resources.cache_clear()


def test_daily_watch_does_not_consume_even_a_legacy_validated_correction():
    forecast = {"id":"frozen-old", "variable":"wind_gust", "unit":"kn", "statistic":"maximum",
        "targetDate":"2026-10-23", "original":14., "corrected":19.,
        "correction":{"status":"VALIDATED", "decisionEligible":True, "modelId":"candidate-old", "reason":"old replay"}}
    result = daily_recommendation(forecast)
    assert result["rawValue"] == result["consumedValue"] == 14.
    assert result["rawRecommendation"] == result["recommendation"] == "Retain daily watch"
    assert result["correctionConsumed"] is False and result["decisionChanged"] is False
    assert result["correctionId"] is None and result["shadowCandidateId"] == "candidate-old"
    assert result["adoptionStatus"] == "NOT_ADOPTED"
    assert result["hourlyApproachEffect"].startswith("NONE")
