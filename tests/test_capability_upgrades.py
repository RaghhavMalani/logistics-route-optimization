from datetime import datetime, timezone, timedelta
import json
import numpy as np
import pandas as pd
import pytest
from PIL import Image
from backend.app.services import cache_service
from src.forecasting.neural_fusion import predict, features, fit
from src.portwatch_os.twin.constrained_rl import MaskedQLearningPolicy
from src.portwatch_os.twin.rl import PortEnvironment, ScenarioSpec
from src.portwatch_os.intelligence.camera_cv import analyse


def test_current_provider_context_is_withheld_during_replay(monkeypatch):
    from types import SimpleNamespace
    from backend.app.routes import capabilities
    monkeypatch.setattr(capabilities, "get_clock", lambda: SimpleNamespace(state=SimpleNamespace(mode="REPLAY")))
    for name in ("aircraft", "satellites", "cyclones", "infrastructure"):
        result = capabilities.layer(name, "INNSA")
        assert result["status"] == "HISTORICAL_UNAVAILABLE"
        assert result["features"] == [] and result["records"] == [] and result["fetchedAt"] is None


def test_infrastructure_geometry_without_center_enters_the_globe_contract(monkeypatch):
    from unittest.mock import Mock
    from types import SimpleNamespace
    from backend.app.routes import capabilities
    monkeypatch.setattr(capabilities, "get_clock", lambda: SimpleNamespace(state=SimpleNamespace(mode=capabilities.LIVE)))
    monkeypatch.setattr(capabilities, "_CACHE", {})
    reply = Mock()
    reply.json.return_value = {"elements": [{"id": 123, "type": "way", "tags": {"railway": "rail"},
        "geometry": [{"lat": 18.9, "lon": 72.9}, {"lat": 19.0, "lon": 73.0}]}]}
    get = Mock(return_value=reply)
    monkeypatch.setattr(capabilities.requests, "get", get)
    data = capabilities.layer("infrastructure", "INNSA")
    assert data["status"] == "CACHED" and len(data["features"]) == 1
    feature = data["features"][0]
    assert feature["kind"] == "rail" and feature["geometry"] == [[72.9, 18.9], [73.0, 19.0]]
    assert feature["lat"] == pytest.approx(18.95) and feature["lon"] == pytest.approx(72.95)
    assert "out geom qt 600" in get.call_args.kwargs["params"]["data"]


def test_provider_failure_keeps_last_snapshot_stale_without_retiming_it(monkeypatch):
    from unittest.mock import Mock
    from types import SimpleNamespace
    import requests
    from backend.app.routes import capabilities
    monkeypatch.setattr(capabilities, "get_clock", lambda: SimpleNamespace(state=SimpleNamespace(mode=capabilities.LIVE)))
    fetched = capabilities.world_now() - timedelta(days=1)
    prior = {"status": "CACHED", "fetchedAt": fetched.isoformat(), "features": [{"id": "known"}], "records": []}
    monkeypatch.setattr(capabilities, "_CACHE", {("infrastructure", "INNSA"): (fetched, prior)})
    monkeypatch.setattr(capabilities.requests, "get", Mock(side_effect=requests.RequestException("unavailable")))
    response = capabilities.layer("infrastructure", "INNSA")
    assert response["status"] == "STALE" and response["features"] == prior["features"]
    assert response["fetchedAt"] == fetched.isoformat()


def test_generation_age_cannot_hide_old_source_and_ages_keep_advancing(tmp_path,monkeypatch):
    at=datetime(2026,10,9,tzinfo=timezone.utc)
    path=tmp_path/"status.json"
    path.write_text(json.dumps({"forecastOrigin":"2026-10-02T00:00:00Z","exportedAt":at.isoformat(),"forecastOriginAgeHours":0,"targetFrom":"2026-10-03","targetThrough":"2026-10-12"}))
    monkeypatch.setattr(cache_service,"STATUS_CACHE",path)
    monkeypatch.setattr(cache_service,"wall_now",lambda:at)
    status=cache_service.get_live_status()
    assert status["forecastOriginStatus"]=="STALE" and status["forecastOriginAgeHours"]==168
    assert status["generationStatus"]=="CURRENT"
    assert status["futureTargetDays"]==3 and status["targetStatus"]=="PARTIAL_HORIZON"
    monkeypatch.setattr(cache_service,"wall_now",lambda:at+timedelta(days=2))
    assert cache_service.get_live_status()["generationStatus"]=="STALE"
    assert cache_service.get_live_status()["forecastOriginAgeHours"]==216
    monkeypatch.setattr(cache_service,"wall_now",lambda:at+timedelta(days=4))
    assert cache_service.get_live_status()["targetStatus"]=="EXPIRED"
    assert cache_service.get_live_status()["futureTargetDays"]==0


def test_neural_gate_has_finite_quantiles_with_missing_specialists():
    base=pd.DataFrame({"port_id":["A","UNKNOWN"],"horizon_day":[1,5]})
    values=np.array([[[1,3,5],[np.nan,np.nan,np.nan],[2,4,7]],[[np.nan,np.nan,np.nan],[3,4,5],[np.nan,np.nan,np.nan]]])
    x,mask=features(base,values,["A"])
    model=fit(x,mask,values[:,:,1],np.array([4.,4.]),epochs=3)
    output,w=predict(base,values,{"ports":["A"],"network":model})
    assert np.isfinite(output).all() and (np.diff(output,axis=1)>=0).all()
    assert w[0,1]==0 and np.array_equal(w[1],[0,1,0])
    with pytest.raises(ValueError):features(base,np.full((2,3,3),np.nan),["A"])


def test_sequential_policy_never_submits_an_infeasible_joint_action():
    env=PortEnvironment(ScenarioSpec(berth_count=4,arrivals=10,horizon_hours=24))
    policy=MaskedQLearningPolicy(training=True,epsilon=1)
    for seed in (168,169,170):
        _,result=env.run_episode(policy,seed);policy.finish(result)
        assert not result.violations and not result.rejected_actions
    assert policy.table and any(any(q) for q in policy.table.values())
    before=json.dumps(policy.table,sort_keys=True)
    policy.training=False
    env.run_episode(policy,999)
    # Unknown evaluation contexts may get zero-initialised, never fitted values.
    assert all(policy.table[k]==v for k,v in json.loads(before).items())


def test_camera_evaluation_requires_authority_and_held_out_reviewed_labels(tmp_path):
    Image.fromarray(np.zeros((20,20),dtype=np.uint8)).save(tmp_path/"empty.png")
    frames=[]
    for i in range(20):
        occupied=bool(i%2)
        pixels=np.zeros((20,20),dtype=np.uint8)
        if occupied:pixels[4:16,4:16]=180
        name=f"frame{i}.png";Image.fromarray(pixels).save(tmp_path/name)
        frames.append({"path":name,"observedAt":f"2026-01-01T00:{i+1:02d}:00Z","berthOccupied":occupied})
    spec={"cameraId":"test-only","coverage":"synthetic test ROI; no real port footage","rightsBasis":"generated test frames", "roi":[0,0,20,20],"emptyReference":"empty.png","referenceAt":"2026-01-01T00:00:00Z","validationFrom":"2026-01-01T00:11:00Z","frames":frames}
    path=tmp_path/"manifest.json";path.write_text(json.dumps(spec))
    result=analyse(path)
    assert result["precision"]==1 and result["recall"]==1 and result["testFrames"]==10
    assert all(o["operationalUse"]=="needs_review" for o in result["observations"])
    spec["rightsBasis"]="";path.write_text(json.dumps(spec))
    with pytest.raises(ValueError,match="authorization"):analyse(path)
