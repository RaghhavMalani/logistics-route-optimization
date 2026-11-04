"""Read-only public forecast inspection inside authenticated role workspaces."""
from pathlib import Path
import hashlib
import json
import re
from fastapi import APIRouter, HTTPException, Query

from src.portwatch_os.clock import world_now
from src.portwatch_os.ledger.store import SqliteLedgerStore
from src.portwatch_os.learning.weather_feedback import WeatherFeedback, instant
from src.portwatch_os.learning.weather_reconciliation import WeatherEvidenceStore, outcome_key, sampling_window, original_response_retained

router=APIRouter()


def inspection(port="INNSA", variable="wind_gust"):
    query_at = world_now()
    from src.portwatch_os.intelligence.current_environment import FEEDBACK_DB, ROOT
    if not FEEDBACK_DB.exists(): raise HTTPException(503,"Public weather archive unavailable")
    ledger=SqliteLedgerStore(FEEDBACK_DB); evidence=WeatherEvidenceStore(FEEDBACK_DB)
    try:
        feedback=WeatherFeedback(ledger)
        report=feedback.report(port,variable=variable,limit=10000,public_only=True,now=query_at)
        forecasts=report["forecasts"]
        cases=sorted((r for r in ledger.predictions(domain="weather",subject=port)
                      if r.target==variable and r.model in ("Open-Meteo surface","Open-Meteo marine")
                      and r.context.extra.get("horizonDays")==5 and instant(r.issued_at)<=query_at),
                     key=lambda r:(r.issued_at,r.prediction_id))
        def inspect_case(row):
            if row is None: return None
            original=feedback.report(port,variable=variable,limit=1,public_only=True,prediction_id=row.prediction_id,now=query_at)["forecasts"][0]
            original={**original,"forecastEvidence":evidence.get("weather_forecast_annotations",row.prediction_id),
                      "outcomeEvidence":evidence.get("weather_outcome_evidence",outcome_key(port,variable,original["validAt"]))}
            outcome = original["outcomeEvidence"]
            if outcome and instant(outcome["availableAt"]) > query_at:
                original["outcomeEvidence"] = None
            # A derived interval annotation also explains older immutable claims.
            if original["forecastEvidence"]:
                original["forecastEvidence"]={**original["forecastEvidence"],"measurementWindow":sampling_window(original["targetDate"],variable)}
            return original
        original=inspect_case(cases[0] if cases else None)
        retained=inspect_case(next((r for r in cases if (evidence.get("weather_forecast_annotations",r.prediction_id) or {}).get("complete") and original_response_retained(evidence.get("weather_forecast_annotations",r.prediction_id),ROOT)),None))
        matched=[r for r in ledger.predictions(domain="weather",subject=port,status="resolved")
            if r.target==variable and r.model=="Open-Meteo surface"
            and r.observation_source=="reanalysis: Open-Meteo ERA5 archive"
            and r.observed_at and instant(r.observed_at)<=query_at and instant(r.issued_at)<=query_at]
        latest_matched=None
        for row in sorted(matched,key=lambda r:(instant(r.observed_at),instant(r.issued_at),r.prediction_id),reverse=True):
            candidate=inspect_case(row)
            annotation=candidate["forecastEvidence"] or {}
            outcome=candidate["outcomeEvidence"] or {}
            digest=outcome.get("responseSha256","")
            raw=ROOT/"outcomes"/(digest+".response")
            if (annotation.get("complete") and original_response_retained(annotation,ROOT)
                    and re.fullmatch("[a-f0-9]{64}",digest) and raw.is_file()
                    and hashlib.sha256(raw.read_bytes()).hexdigest()==digest):
                latest_matched=candidate
                break
        status=ROOT/"reconciliation.json"
        next_rows=[f for f in forecasts if instant(f["validAt"])>query_at]
        subsequent=next((f for f in next_rows if f["horizonDays"]==5),next_rows[0] if next_rows else None)
        candidate=feedback.correction(port,variable,"Open-Meteo surface",5,query_at)
        candidate={**candidate,"candidateEligible":candidate.get("decisionEligible",False),
            "decisionEligible":False,"mode":"SHADOW_ONLY","adoptionStatus":"NOT_ADOPTED",
            "status":"SHADOW_VALIDATED" if candidate["status"]=="VALIDATED" else candidate["status"]}
        return {**report,"forecasts":forecasts[:100],"originalFiveDayCase":original,"retainedFiveDayCase":retained,
            "latestMatchedCase":latest_matched,
            "matchedContextCounts":{"portCode":port,"variable":variable,"forecastSnapshots":len(matched),
                "independentTargets":len({(r.model,r.valid_at,r.observation_source) for r in matched}),
                "targetMeaning":"One port, variable, daily UTC aggregate, provider and reanalysis outcome; repeated forecast snapshots share a target"},
            "currentCandidate":candidate,
            "subsequentRecommendation":daily_recommendation(subsequent),
            "reconciliation":json.loads(status.read_text()) if status.exists() else {"status":"NOT_RUN"}}
    finally: evidence.close();ledger.close()


def daily_recommendation(forecast):
    if not forecast: return {"status":"UNAVAILABLE","reason":"No subsequent archived daily forecast"}
    threshold, direction = {"wind_gust":(15,"above"),"wind_speed":(15,"above"),
        "rainfall":(20,"above"),"wave_height":(2,"above"),"visibility":(5,"below")}[forecast["variable"]]
    exposed = (lambda v:v>threshold) if direction=="above" else (lambda v:v<threshold)
    correction=forecast["correction"]
    from src.portwatch_os.learning.weather_feedback import consumed_value
    raw=forecast["original"]; value=consumed_value(raw, correction)
    use=False  # Shadow evaluation has no adoption contract or operational effect.
    return {"kind":"DAILY_WEATHER_WATCH","forecastId":forecast["id"],"targetDate":forecast["targetDate"],
        "variable":forecast["variable"],"unit":forecast["unit"],"statistic":forecast["statistic"],
        "rawValue":raw,"consumedValue":value,"correctionConsumed":use,"correctionId":None,
        "shadowCandidateId":(forecast.get("shadowCorrection") or {}).get("modelId") or correction.get("candidateModelId") or correction.get("modelId"),
        "consumptionMode":"SHADOW_ONLY","adoptionStatus":"NOT_ADOPTED",
        "correctionStatus":correction["status"],"threshold":threshold,"thresholdDirection":direction,"thresholdBasis":"operator research assumption; not a port operating limit",
        "rawRecommendation":"Review daily exposure" if exposed(raw) else "Retain daily watch",
        "recommendation":"Review daily exposure" if exposed(value) else "Retain daily watch",
        "decisionChanged":exposed(raw)!=exposed(value),
        "reason":correction["reason"],"hourlyApproachEffect":"NONE: daily correction is not applied to hourly gust or visibility",
        "operationalEffect":"Daily research watch only; no validated delay, berth, fuel or cost consequence"}


@router.get("/weather/verification")
def verification(portCode:str=Query("INNSA"),variable:str=Query("wind_gust")):
    from src.utils import port_registry
    from src.portwatch_os.learning.weather_feedback import VARIABLES
    port=port_registry.resolve(portCode)
    if not port or variable not in VARIABLES: raise HTTPException(422,"Registered port and supported weather variable required")
    return inspection(port.locode,variable)


@router.get("/weather/shadow")
def shadow_analysis(portCode: str | None = Query(None), variable: str | None = Query(None),
                    provider: str | None = Query(None, max_length=100),
                    horizon: int | None = Query(None, ge=0, le=366),
                    asOf: str | None = Query(None, max_length=50)):
    """Evidence-qualified daily error analysis; no collection or adoption writes."""
    from src.utils import port_registry
    from src.portwatch_os.intelligence.current_environment import FEEDBACK_DB, ROOT
    from src.portwatch_os.learning.weather_feedback import VARIABLES
    from src.portwatch_os.learning.weather_shadow import WeatherShadowAnalysis
    if not FEEDBACK_DB.exists():
        raise HTTPException(503, "Public weather archive unavailable")
    port = port_registry.resolve(portCode) if portCode else None
    if (portCode and not port) or (variable and variable not in VARIABLES):
        raise HTTPException(422, "Registered port and supported weather variable required")
    if provider and provider not in ("Open-Meteo surface", "Open-Meteo marine"):
        raise HTTPException(422, "Provider must identify a retained public forecast product")
    at = world_now()
    latest_query_at = at
    if asOf:
        try:
            at = instant(asOf)
        except (ValueError, TypeError, OverflowError):
            raise HTTPException(422, "asOf must be an aware ISO timestamp") from None
        if at > latest_query_at:
            raise HTTPException(422, "An analysis cannot use future evidence")
    ledger, evidence = SqliteLedgerStore(FEEDBACK_DB), WeatherEvidenceStore(FEEDBACK_DB)
    try:
        return WeatherShadowAnalysis(ledger, evidence, ROOT).report(
            now=at, port_code=port.locode if port else None, variable=variable,
            provider=provider, horizon=horizon)
    finally:
        evidence.close()
        ledger.close()


@router.get("/weather/evidence/{digest}")
def source_response(digest:str):
    from src.portwatch_os.intelligence.current_environment import ROOT
    if not re.fullmatch("[a-f0-9]{64}",digest): raise HTTPException(404,"Evidence unavailable")
    for folder in ("archive","outcomes"):
        path=ROOT/folder/(digest+".response")
        if path.is_file():
            raw=path.read_bytes()
            if hashlib.sha256(raw).hexdigest()!=digest: raise HTTPException(503,"Evidence hash mismatch")
            # Weather originals are JSON; unsupported XML is not returned here.
            try: data=json.loads(raw)
            except ValueError: raise HTTPException(422,"Not a weather response")
            return {"sha256":digest,"response":data}
    raise HTTPException(404,"Original response not available")
