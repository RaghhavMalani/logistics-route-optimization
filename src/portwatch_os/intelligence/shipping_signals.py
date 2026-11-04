"""Reported source evidence, inferred shipping exposure and explicit scenarios."""
from datetime import timedelta
import hashlib
import io
import json
import math
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
import pandas as pd
import requests

from src.portwatch_os.clock import wall_now, world_now, get_clock, LIVE
from src.portwatch_os.intelligence.current_environment import ROOT, refresh, instant
from src.portwatch_os.intelligence.context import SERIES
from src.utils import port_registry
EVIDENCE_LOCK=threading.RLock()


def preserve(body, raw=None):
    with EVIDENCE_LOCK:
        return _preserve(body,raw)


def _preserve(body, raw=None):
    root=ROOT/"shipping_intelligence";root.mkdir(parents=True,exist_ok=True)
    raw=raw or json.dumps(body,sort_keys=True).encode()
    digest=hashlib.sha256(raw).hexdigest()
    body={**body,"responseSha256":digest}
    key=hashlib.sha256(json.dumps({k:v for k,v in body.items() if k not in ("availableAt","fetchedAt")},sort_keys=True).encode()).hexdigest()
    path=root/(key+".json")
    if path.exists(): return json.loads(path.read_text())
    # wall-clock: first application receipt is immutable and distinct from publication or replay time.
    body.update(id=key,availableAt=wall_now().isoformat(),availabilityBasis="first receipt by PortWatch; publication vintage may be unknown")
    original=root/(digest+".response")
    if not original.exists(): original.write_bytes(raw)
    # Exclusive creation preserves the first receipt even under concurrent reads.
    try:
        with path.open("x") as f: json.dump(body,f)
    except FileExistsError: return json.loads(path.read_text())
    return body


def economic_signal(series):
    # wall-clock: a live provider request and its six-hour cache cadence follow the real collection date.
    checked_at = wall_now()
    key,label,sid,unit,mechanism=series
    root=ROOT/"shipping_intelligence";root.mkdir(parents=True,exist_ok=True)
    pointer=root/("economic-"+key+".json")
    old=json.loads(pointer.read_text()) if pointer.exists() else None
    if old and checked_at-instant(old["fetchedAt"])<timedelta(hours=6): return old
    try:
        # Use the CSV endpoint, never interpret the graph HTML as evidence.
        response=requests.get("https://fred.stlouisfed.org/graph/fredgraph.csv",params={"id":sid,"cosd":(checked_at-timedelta(days=120)).date().isoformat(),"coed":checked_at.date().isoformat()},timeout=(3,10))
        response.raise_for_status()
        frame=pd.read_csv(io.BytesIO(response.content));frame.columns=["date","value"]
        frame["date"]=pd.to_datetime(frame["date"],utc=True,errors="coerce");frame["value"]=pd.to_numeric(frame["value"],errors="coerce")
        frame=frame.dropna().sort_values("date");frame=frame[frame["date"]<=pd.Timestamp(checked_at)]
        if frame.empty: raise ValueError("No dated economic observation")
        last=frame.iloc[-1];previous=frame.iloc[-2] if len(frame)>1 else None
        body=preserve({"category":"economic","title":label,"source":f"https://fred.stlouisfed.org/series/{sid}",
            "fact":f"{label}: {last['value']:.4g} {unit} on {last['date'].date()}","observedAt":last["date"].isoformat(),
            "value":float(last["value"]),"previousValue":float(previous["value"]) if previous is not None else None,
            "changePct":100*(last["value"]/previous["value"]-1) if previous is not None and previous["value"] else None,
            "unit":unit,"mechanism":mechanism+". Crude is not a bunker quote; an exchange rate is not a freight cost.",
            "status":"CURRENT" if checked_at-last["date"].to_pydatetime()<timedelta(days=7 if key!="india_cpi" else 60) else "STALE",
            "relationship":"Indian destination/settlement exposure; vessel contract currency and bunker rates are unavailable"},response.content)
        # wall-clock: successful fetch completion is a receipt field, never the source observation date.
        body={**body,"fetchedAt":wall_now().isoformat()}
        temp=pointer.with_name(pointer.name+"."+uuid.uuid4().hex+".tmp");temp.write_text(json.dumps(body));temp.replace(pointer)
        return body
    except (requests.RequestException,ValueError,pd.errors.ParserError,KeyError):
        return {**old,"status":"STALE","reason":"Refresh failed; old receipt retained"} if old else {"category":"economic","title":label,"status":"UNAVAILABLE","reason":"Provider unavailable","source":f"https://fred.stlouisfed.org/series/{sid}"}


def distance(a,b):
    lat1,lon1,lat2,lon2=map(math.radians,(*a,*b)); x=math.sin((lat2-lat1)/2)**2+math.cos(lat1)*math.cos(lat2)*math.sin((lon2-lon1)/2)**2
    return 6371*2*math.asin(min(1,math.sqrt(x)))


def signals_for(world, *, now=None):
    query_at = world_now() if now is None else instant(now)
    if get_clock().state.mode != LIVE or now is not None:
        # Historical inspection consumes retained vintages only; it never fetches
        # today's providers and labels their later responses as earlier knowledge.
        retained = []
        for path in (ROOT / "shipping_intelligence").glob("*.json"):
            try:
                row = json.loads(path.read_text())
                if row.get("id") and row.get("category") and row.get("availableAt") and instant(row["availableAt"]) <= query_at:
                    retained.append(row)
            except (OSError, ValueError, TypeError, AttributeError):
                continue
        retained = list({row["id"]: row for row in retained}.values())
        return _project_signals(world, retained, query_at)
    port=port_registry.resolve("INNSA")
    hazards=refresh("hazards",port)
    signals=[]
    for h in hazards["rows"]:
        near=[p for p in port_registry.all_ports() if distance((h["lat"],h["lon"]),(p.lat,p.lon))<=750]
        if not near: continue
        mechanism={"DR":"Drought may affect water supply, agricultural cargo or landside capacity; confirm local restrictions and cargo dependency before changing a port plan.",
            "EQ":"An earthquake may damage quays, roads or rail; confirm infrastructure inspections and access restrictions.",
            "FL":"Flooding may affect landside roads, rail and cargo evacuation; confirm affected links and available capacity.",
            "TC":"A tropical cyclone may affect coastal approaches and terminal operations; confirm approach limits and local port notices."}.get(h["kind"],"Regional hazard may affect coastal approaches or landside infrastructure; confirm a relevant port notice.")
        signals.append(preserve({"category":"hazard","title":h["title"],"fact":f"GDACS reports {h['alertLevel']} {h['kind']}; {h['title']}",
            "source":h["source"],"publishedAt":h["publishedAt"],"validFrom":h["validFrom"],"validThrough":h["validThrough"],
            "status":hazards["status"] if instant(h["validThrough"])>=query_at else "STALE",
            "sourceReceiptStatus":hazards["status"],"active":instant(h["validThrough"])>=query_at,"portCodes":[p.locode for p in near],
            "location":{"lat":h["lat"],"lon":h["lon"]},"parentResponseSha256":hazards.get("responseSha256"),
            "mechanism":mechanism+" Geographic proximity identifies a review subject, not a port closure.",
            "relationship":"Inferred exposure within 750 km; historical validity remains explicit; no event-caused delay inferred"}))
    with ThreadPoolExecutor(max_workers=3) as pool:
        signals.extend(pool.map(economic_signal,SERIES))
    try:
        from backend.app.services.cache_service import get_news_bundle, CacheNotReadyError
        from src.portwatch_os.global_eye.ingest import from_news_bundle
        bundle=get_news_bundle();events,_=from_news_bundle(bundle)
        raw_news=json.dumps(bundle,sort_keys=True,default=str).encode()
        from src.portwatch_os.global_eye.exposure import build_impact
        for event in events[:30]:
            impact=build_impact(event).to_dict();codes=[p["portCode"] for p in impact["ports"]]
            if not codes: continue
            article=next((s for s in event.sources if s.url and s.title==event.title),None) or next((s for s in event.sources if s.url),None)
            if not article: continue
            source=article.url;published=article.published_at
            state="UNDATED" if not published else "STALE" if query_at-instant(published)>timedelta(days=3) else "CACHED"
            if published and instant(published)>query_at: state="FUTURE_DATED"
            signals.append(preserve({"category":"news","title":event.title,"fact":"Source headline: "+event.title,
                "source":source,"publishedAt":published,"status":state,
                "portCodes":codes,"laneCodes":[x["laneCode"] for x in impact["lanes"]],
                "mechanism":"Reported maritime event → named lane/port in the exposure graph → voyage and cargo requiring confirmation.",
                "relationship":"Headline is reported evidence; extracted entities and geographic shipping exposure are inference, not confirmed delay",
                "responseBasis":"Preserved cache-service news bundle; original publisher article body is not collected"},raw_news))
    except (ValueError,KeyError,CacheNotReadyError) as exc:
        # No news substitute: the provider state remains explicit.
        signals.append({"category":"news","title":"Shipping news","status":"UNAVAILABLE","reason":str(exc)[:160]})
    signals.append(preserve({"category":"infrastructure","title":"JNPA landside infrastructure review","fact":"OSM road/rail/warehouse catalogue is a reference layer, not an outage feed",
        "source":"https://www.openstreetmap.org/copyright","status":"REFERENCE_ONLY","portCodes":["INNSA"],
        "mechanism":"A confirmed road, rail or power outage could affect cargo evacuation and yard occupancy; duration and available capacity must be supplied before calculating delay.",
        "relationship":"No reported outage is asserted; infrastructure event feed unavailable"}))
    return _project_signals(world, signals, query_at)


def _project_signals(world, signals, query_at):
    signals = [dict(s) for s in signals if not s.get("availableAt") or instant(s["availableAt"]) <= query_at]
    for s in signals:
        if s["category"]=="economic" and s.get("observedAt") and s["status"]!="UNAVAILABLE":
            budget=60 if "CPI" in s["title"] else 7
            if query_at-instant(s["observedAt"])>=timedelta(days=budget): s["status"]="STALE"
        codes=s.get("portCodes") or ([v["portCode"] for v in world["fleet"]] if s["category"]=="economic" else [])
        vessels=[v for v in world["fleet"] if v["portCode"] in codes and (not s.get("laneCodes") or v["laneCode"] in s["laneCodes"])]
        s["exposure"]={"basis":"Contextual destination/lane association only; it does not demonstrate passage through an affected asset", "status":"NO_DEMONSTRATED_EXPOSURE", "ports":sorted(set(codes)),
            "routes":sorted({v["laneCode"] for v in vessels}),"vessels":[{"id":v["id"],"name":v["name"]} for v in vessels],
            "cargo":[{"vesselId":v["id"],"description":v["cargo"]} for v in vessels],"cargoBasis":"Visitor manifest; no independent cargo tracking or measured loss"}
        s["comparisonAvailable"]=False
        s["reviewTaskAvailable"]=bool(s['category'] in ('news','hazard') and s.get('id') and s['status'] not in ('UNAVAILABLE','FUTURE_DATED','REFERENCE_ONLY'))
        s["reviewTaskReason"]='Verify the attributed report, precise asset and passage timing; no numerical event-to-delay inputs are available'
        if s['category']=='economic':
            s['decisionLimitation']='Reference quotes need declared currency amounts and settlement dates for valuation; they do not justify a vessel hold'
    return {"asOf":query_at.isoformat(),"signals":signals,
        "note":"Reported facts, inferred exposure and scenario assumptions stay separate. Missing causal inputs produce unavailable delay/cost, not zero."}
