"""Deterministic provider fixtures validate reconciliation, not real model skill."""
from datetime import datetime, timedelta, timezone
import hashlib
import json
from unittest.mock import Mock
import pandas as pd
import pytest
from src.portwatch_os.ledger.store import SqliteLedgerStore
from src.portwatch_os.learning.weather_feedback import WeatherFeedback
from src.portwatch_os.learning.weather_reconciliation import reconcile, WeatherEvidenceStore, outcome_key
from src.utils import port_registry

ISSUE=datetime(2026,10,9,8,tzinfo=timezone.utc)
DAY="2026-10-14"
NOW=datetime(2026,10,20,12,tzinfo=timezone.utc)

def archive(tmp_path, *, complete=True, duplicates=False):
    db=tmp_path/"weather.db";root=tmp_path/"sources";(root/"archive").mkdir(parents=True)
    ledger=SqliteLedgerStore(db)
    for offset in ([0,1] if duplicates else [0]):
        issue=ISSUE+timedelta(minutes=offset)
        frame=pd.DataFrame([{"port_id":"JNPT","date":DAY,"wind_gust":10.,"wind_speed":8.,"rainfall":2.}])
        WeatherFeedback(ledger).record_frame(frame,issued_at=issue,provider="Open-Meteo surface",source_state="LIVE",now=issue)
        rows=[{"validAt":f"{DAY}T{h:02}:00:00+00:00","wind_gusts_10m":10.,"wind_speed_10m":8.,"precipitation":2/24} for h in range(24 if complete else 23)]
        raw=json.dumps({"fixtureOriginalHourlyValues":rows}).encode();digest=hashlib.sha256(raw).hexdigest()
        (root/"archive"/(digest+".response")).write_bytes(raw)
        body={"kind":"surface","portCode":"INNSA","availableAt":issue.isoformat(),"snapshotId":f"source-{offset}","responseSha256":digest,"request":{"latitude":18.95,"longitude":72.95},"rows":rows}
        (root/"archive"/f"forecast-{offset}.json").write_text(json.dumps(body))
    ledger.close();return db,root

def provider(*, hours=24, unit="kn", location=None):
    p=port_registry.resolve("INNSA")
    body={"utc_offset_seconds":0,"latitude":p.lat,"longitude":p.lon,
          "hourly_units":{"wind_speed_10m":unit,"wind_gusts_10m":"kn","precipitation":"mm"},
          "hourly":{"time":[f"{DAY}T{h:02}:00" for h in range(hours)],"wind_speed_10m":[9.]*hours,"wind_gusts_10m":[18.]*hours,"precipitation":[.5]*hours}}
    if location: body.update(latitude=location[0],longitude=location[1])
    r=Mock(content=json.dumps(body).encode());r.json.return_value=body;return r

def test_first_receipt_aggregation_originals_and_duplicate_counts(tmp_path):
    db,root=archive(tmp_path,duplicates=True);response=provider();fetch=Mock(return_value=response)
    report=reconcile(db=db,root=root,now=NOW,fetch=fetch)
    assert report["resolvedForecasts"]==6 and report["independentOutcomes"]==3
    assert fetch.call_args.kwargs["params"]["models"]=="era5"
    ledger=SqliteLedgerStore(db);data=WeatherFeedback(ledger).report(now=NOW,public_only=True)
    assert data["independentResolvedTargets"]==3 and data["resolved"]==6
    assert all(s["samples"]==1 and s["forecastSnapshots"]==2 for s in data["scores"])
    gust=next(r for r in ledger.predictions(domain="weather") if r.target=="wind_gust")
    assert gust.predicted_value==10 and gust.observed_value==18
    store=WeatherEvidenceStore(db);out=store.get("weather_outcome_evidence",outcome_key("INNSA","wind_gust",gust.valid_at))
    assert out["kind"]=="reanalysis" and out["availableAt"]==NOW.isoformat() and out["completeHours"]==24
    digest=hashlib.sha256(response.content).hexdigest()
    assert (root/"outcomes"/(digest+".response")).read_bytes()==response.content
    ledger.close();store.close()
    repeated=reconcile(db=db,root=root,now=NOW+timedelta(days=1),fetch=fetch)
    assert repeated["resolvedForecasts"]==0 and fetch.call_count==1
    store=WeatherEvidenceStore(db);assert store.get("weather_outcome_evidence",out["id"])["availableAt"]==NOW.isoformat();store.close()

@pytest.mark.parametrize("kind",["early","incomplete_original","missing_hours","wrong_units","wrong_location","null"])
def test_ineligible_or_bad_outcomes_never_verify(tmp_path,kind):
    db,root=archive(tmp_path,complete=kind!="incomplete_original")
    response=provider(hours=23 if kind=="missing_hours" else 24,unit="m/s" if kind=="wrong_units" else "kn",location=(0,0) if kind=="wrong_location" else None)
    if kind=="null":response.json.return_value["hourly"]["wind_gusts_10m"][0]=None
    fetch=Mock(return_value=response)
    result=reconcile(db=db,root=root,now=NOW-timedelta(days=1) if kind=="early" else NOW,fetch=fetch)
    ledger=SqliteLedgerStore(db);gust=next(r for r in ledger.predictions(domain="weather") if r.target=="wind_gust")
    assert gust.status=="open" and gust.observed_value is None
    if kind in ("early","incomplete_original"):assert fetch.call_count==0
    elif kind=="missing_hours": assert result["status"]=="WAITING_FOR_COMPLETE_OUTCOMES"
    elif kind in ("wrong_units","wrong_location"): assert result["status"]=="PROVIDER_UNAVAILABLE"
    ledger.close()

def test_daily_watch_consumes_frozen_validated_version_only():
    from backend.app.routes.weather_verification import daily_recommendation
    f={"id":"forecast","targetDate":DAY,"variable":"wind_gust","statistic":"maximum","unit":"kn","original":14.,"corrected":18.,"correction":{"status":"COLLECTING","decisionEligible":False,"reason":"Insufficient","modelId":None}}
    assert daily_recommendation(f)["consumedValue"]==14
    f["correction"].update(status="VALIDATED",decisionEligible=True,modelId="version-1")
    result=daily_recommendation(f)
    assert result["decisionChanged"] and result["correctionId"]=="version-1"
    assert result["hourlyApproachEffect"].startswith("NONE") and f["original"]==14

def test_precipitation_interval_preserves_preceding_hour_bins():
    from src.portwatch_os.learning.weather_reconciliation import sampling_window
    window=sampling_window(DAY,"rainfall")
    assert window["from"]=="2026-10-13T23:00:00+00:00"
    assert window["through"]=="2026-10-14T23:00:00+00:00"
    assert "not a midnight-to-midnight" in window["definition"]

def test_legacy_claim_without_original_response_is_preserved_but_ineligible(tmp_path):
    db,root=archive(tmp_path)
    for path in (root/"archive").glob("forecast-*.json"):
        path.unlink()
    fetch=Mock(return_value=provider())
    result=reconcile(db=db,root=root,now=NOW,fetch=fetch)
    assert result["nextEligibleAt"] is None and result["unverifiableOriginals"]==3
    assert fetch.call_count==0 and result["resolvedForecasts"]==0
    ledger=SqliteLedgerStore(db)
    expected={"wind_gust":10.,"wind_speed":8.,"rainfall":2.}
    assert all(row.status=="open" and row.predicted_value==expected[row.target] for row in ledger.predictions(domain="weather"))
    ledger.close()

def test_live_outcome_availability_is_receipt_after_provider_returns(tmp_path,monkeypatch):
    db,root=archive(tmp_path)
    moments=iter([NOW,NOW+timedelta(minutes=2),NOW+timedelta(minutes=3)])
    monkeypatch.setattr("src.portwatch_os.learning.weather_reconciliation.wall_now",lambda:next(moments))
    result=reconcile(db=db,root=root,fetch=Mock(return_value=provider()))
    assert result["requests"][0]["receivedAt"]==(NOW+timedelta(minutes=2)).isoformat()
    store=WeatherEvidenceStore(db)
    assert all(o["availableAt"]==result["requests"][0]["receivedAt"] for o in store.outcomes())
    store.close()

@pytest.mark.parametrize("missing",[True,False])
def test_missing_or_corrupt_original_response_never_enters_learning(tmp_path,missing):
    db,root=archive(tmp_path)
    for path in (root/"archive").glob("*.response"):
        if missing:path.unlink()
        else:path.write_bytes(b"corrupt fixture")
    fetch=Mock(return_value=provider())
    result=reconcile(db=db,root=root,now=NOW,fetch=fetch)
    assert result["unverifiableOriginals"]==3 and result["nextEligibleAt"] is None
    assert result["resolvedForecasts"]==0 and fetch.call_count==0

def test_legacy_daily_ingestion_cannot_bypass_verification(tmp_path,monkeypatch):
    from src.ingestion.connectors import weather_live
    db,root=archive(tmp_path);ledger=SqliteLedgerStore(db)
    monkeypatch.setattr("src.portwatch_os.ledger.store.get_ledger",lambda:ledger)
    monkeypatch.setattr("src.portwatch_os.clock.world_now",lambda:NOW+timedelta(days=2))
    monkeypatch.setattr(weather_live,"FORECAST_CACHE",tmp_path/"not-present.json")
    fetch=Mock(side_effect=AssertionError("Daily feature cache cannot verify claims"))
    monkeypatch.setattr(weather_live,"fetch_archive_weather",fetch)
    weather_live._weather_feedback(pd.DataFrame(),"unavailable","unavailable")
    assert fetch.call_count==0 and all(r.status=="open" for r in ledger.predictions(domain="weather"))
    ledger.close()
