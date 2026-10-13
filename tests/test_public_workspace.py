"""Public scene availability, private boundaries and real constrained scenarios."""
import json
from datetime import datetime, timezone
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from backend.app.main import app
from backend.app.services import public_workspace as public
from src.portwatch_os.clock import get_clock
from src.portwatch_os.decision.actions import REROUTE
from src.portwatch_os.intelligence.cameras import Camera, CameraRegistry

T = datetime(2026, 10, 8, 12, tzinfo=timezone.utc)
INPUT = dict(lane_code="EUR_IND", port_code="INNSA", hours_to_risk=24,
    speed=16, closure_hours=72, severity=1, wave_m=2, charter_day=30000,
    bunker_price=650, fuel_burn=45, at=T)

@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("PORTWATCH_IDENTITY_MODE", "verified")
    c = TestClient(app)  # No lifespan: never starts provider jobs.
    yield c
    c.close()


def test_actual_branches_geometry_constraints_and_no_shared_writes(tmp_path):
    state = get_clock().state
    with patch("src.portwatch_os.ledger.store.get_ledger", side_effect=AssertionError("Public simulation must not open ledger")):
        result = public.simulate(**INPUT)
        longer = public.simulate(**(INPUT | {"closure_hours":120}))
        unsafe = public.simulate(**(INPUT | {"wave_m":9}))
        inside = public.simulate(**(INPUT | {"hours_to_risk":-12}))
    assert get_clock().state == state
    assert result["observedOutcome"] is None
    assert len(result["options"]) >= 5
    assert result["options"][0]["evaluation"]["objectives"]["eta"]["value"] != longer["options"][0]["evaluation"]["objectives"]["eta"]["value"]
    cape = next(o for o in result["options"] if o["action"] == REROUTE)
    assert cape["geometry"] != result["options"][0]["geometry"]
    assert all(not o["feasible"] and any(c["key"]=="weather_safety" for c in o["rejectedBy"]) for o in unsafe["options"])
    assert not any(o["action"] == REROUTE for o in inside["options"])
    assert result["options"][0]["evaluation"]["financial"]["complete"] is False
    assert result["recommendation"]["rankingBasis"]["objectivesDropped"]
    red_sea = public.simulate(**(INPUT | {"risk_chokepoint":"BAB_EL_MANDEB"}))
    assert red_sea["inputs"]["riskChokepoint"] == "BAB_EL_MANDEB"
    assert "BAB_EL_MANDEB" in red_sea["doNothingStatement"]
    # 24 h to Bab-el-Mandeb puts the preceding Suez window behind this
    # approximate vessel. The Cape cannot be offered as an instant diversion.
    assert not any(o["action"] == REROUTE for o in red_sea["options"])


def test_anonymous_simulation_is_bounded_and_does_not_authorize_operator_routes(client):
    assert client.get("/api/public/scenario").status_code == 200
    for query in ("speedKn=NaN", "speedKn=100", "closureHours=inf", "laneCode=BAD", "portCode=INMAA&laneCode=EUR_IND", "riskChokepoint=MALACCA", "at=2026-10-08T12:00:00"):
        assert client.get("/api/public/scenario?"+query).status_code == 422
    for path in ("/api/public/workspace", "/api/public/scenario", "/api/public/weather-feedback?portCode=INNSA"):
        assert client.post(path,headers={"X-PortWatch-Role":"NATIONAL_ADMIN"}).status_code == 401
    assert client.get("/api/intelligence/cameras",headers={"X-PortWatch-Role":"NATIONAL_ADMIN"}).status_code == 401
    assert client.get("/api/public/workspace?mode=replay&at=2026-10-08T12:00:00").status_code == 422
    assert client.get("/api/public/weather-feedback?portCode=INNSA&at=2026-10-08T12:00:00").status_code == 422


def test_replay_withholds_rewritten_cache_and_private_live_media(tmp_path,monkeypatch):
    registry = CameraRegistry(tmp_path/"camera.db")
    for cid,access in (("private","port_authority"),("public","public")):
        registry.register(Camera(id=cid,portCode="INNSA",name=cid,lat=19,lon=73,coverage="Test viewpoint",mediaUrl="https://example.com/"+cid,source="Test",rightsBasis="Authorized test",access=access), "Reviewer")
    before = registry.path.read_bytes()
    monkeypatch.setattr("src.portwatch_os.intelligence.cameras.CameraRegistry",lambda:registry)
    monkeypatch.setattr(public,"wall_now",lambda:T)
    keys = ("Maritime events (GDELT + GDACS)","Port activity (IMF PortWatch)","Marine weather (Open-Meteo)")
    monkeypatch.setattr(public.cache,"get_provenance",lambda:{"sources":{k:{"isReal":True,"fetched_at":"2026-10-08T04:00:00Z"} for k in keys}})
    monkeypatch.setattr(public.cache,"get_news_bundle",lambda:{"refreshedAt":"2026-10-08T11:00:00Z","events":[]})
    monkeypatch.setattr(public.cache,"get_live_status",lambda:{"exportedAt":"2026-10-08T11:00:00Z"})
    monkeypatch.setattr(public.cache,"get_weather_by_port",lambda:{"INNSA":{"observedAt":"2026-10-08T00:00:00","windKnots":10}})
    monkeypatch.setattr(public,"explore",lambda:{"ports":[{"code":"INNSA","forecasts":[{"originDate":"2026-10-02T00:00:00Z"}],"congestionIndex":10}],"events":[{"eventId":"later-cache","firstSeen":"2026-10-07T00:00:00Z"}]})
    replay = public.workspace("replay","2026-10-08T08:00:00Z")
    assert not replay["events"] and not replay["weather"] and not replay["ports"][0]["forecasts"]
    assert not replay["cameras"] and not replay["economics"]
    current = public.workspace()
    assert len(current["weather"]) == 1 and current["ports"][0]["forecasts"]
    assert [c["id"] for c in current["cameras"]] == ["public"]
    assert "registeredBy" not in current["cameras"][0]
    assert registry.path.read_bytes() == before
    assert not public.workspace("projection","2026-10-09T00:00:00Z")["cameras"]
    # The initial pipeline bundle predates the independent refresh field.
    # Its enclosing export clock still withholds the entire later vintage.
    monkeypatch.setattr(public.cache,"get_news_bundle",lambda:{"events":[]})
    assert len(public.workspace()["events"]) == 1
    assert not public.workspace("replay","2026-10-08T08:00:00Z")["events"]
    # A first deployment or absent cache has no export/refresh clock. It must
    # remain explorable with an unavailable feed, not fail on instant(None).
    monkeypatch.setattr(public.cache,"get_live_status",lambda:{})
    monkeypatch.setattr(public.cache,"get_news_bundle",lambda:{})
    missing = public.workspace()
    assert not missing["events"] and not missing["weather"]
    assert not missing["ports"][0]["forecasts"] and missing["routes"]
