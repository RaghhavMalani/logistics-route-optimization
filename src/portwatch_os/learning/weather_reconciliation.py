"""Prospective weather verification against explicitly selected ERA5 reanalysis.

The archive forecast is never fetched again to manufacture its original value.
Outcome receipt is first availability to this application, not publication time.
"""
from __future__ import annotations

from datetime import timedelta
import hashlib
import json
import sqlite3
import threading
import math
import re
from pathlib import Path

import requests

from src.portwatch_os.clock import wall_now
from src.portwatch_os.ledger.store import SqliteLedgerStore
from src.portwatch_os.learning.weather_feedback import WeatherFeedback, WeatherObservation, instant
from src.utils import port_registry

URL = "https://archive-api.open-meteo.com/v1/archive"
FIELDS = {"wind_speed": "wind_speed_10m", "wind_gust": "wind_gusts_10m", "rainfall": "precipitation"}
UNITS = {"wind_speed_10m": "kn", "wind_gusts_10m": "kn", "precipitation": "mm"}
LAG_DAYS = 6  # Conservative ERA5 availability; still require 24 actual non-null hours.
RUN_LOCK = threading.Lock()
STOP = threading.Event()
WORKER = None


def complete_day(times, day):
    return set(times) == {f"{day}T{hour:02}:00" for hour in range(24)} and len(times)==24


def measurement(value):
    return isinstance(value,(int,float)) and not isinstance(value,bool) and math.isfinite(value) and value>=0


def sampling_window(day, variable):
    """Keep the restored aggregator's exact UTC-labelled bins inspectable.

    Open-Meteo precipitation at 00:00 is the preceding hour's accumulation,
    so the existing sum of labels 00–23 spans 23:00 to 23:00, not midnight
    to midnight. Reanalysis uses those same bins; originals are not rewritten.
    """
    start=instant(day+"T00:00:00+00:00")
    if variable=="rainfall":
        return {"from":(start-timedelta(hours=1)).isoformat(),"through":(start+timedelta(hours=23)).isoformat(),
            "definition":"Sum of preceding-hour precipitation bins labelled 00–23 UTC; nominal archive date is not a midnight-to-midnight rain total"}
    return {"from":start.isoformat(),"through":(start+timedelta(hours=23)).isoformat(),
        "definition":"24 hourly samples labelled 00–23 UTC; maximum or mean of samples, not continuous station extrema"}


class WeatherEvidenceStore:
    def __init__(self, path):
        self.path = Path(path)
        self.conn = sqlite3.connect(str(path), timeout=30)
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript("""
          CREATE TABLE IF NOT EXISTS weather_outcome_evidence
            (id TEXT PRIMARY KEY, body TEXT NOT NULL);
          CREATE TABLE IF NOT EXISTS weather_forecast_annotations
            (id TEXT PRIMARY KEY, body TEXT NOT NULL);
          CREATE TABLE IF NOT EXISTS weather_correction_versions
            (id TEXT PRIMARY KEY, cohort TEXT NOT NULL, body TEXT NOT NULL);
        """)
        self.conn.commit()

    def close(self):
        self.conn.close()

    def put(self, table, key, body):
        assert table in ("weather_outcome_evidence", "weather_forecast_annotations")
        with self.conn:
            self.conn.execute(f"INSERT OR IGNORE INTO {table}(id,body) VALUES (?,?)", (key,json.dumps(body)))
        return self.get(table,key)

    def get(self, table, key):
        assert table in ("weather_outcome_evidence", "weather_forecast_annotations")
        row = self.conn.execute(f"SELECT body FROM {table} WHERE id=?", (key,)).fetchone()
        return json.loads(row[0]) if row else None

    def outcomes(self):
        return [json.loads(r[0]) for r in self.conn.execute("SELECT body FROM weather_outcome_evidence")]


def outcome_key(port, variable, valid, source="Open-Meteo ERA5 archive"):
    return hashlib.sha256(f"reanalysis:{source}:{port}:{variable}:{valid}".encode()).hexdigest()


def original_response_retained(annotation, root):
    digest=(annotation or {}).get("responseSha256","")
    if not re.fullmatch("[a-f0-9]{64}",digest): return False
    path=Path(root)/"archive"/(digest+".response")
    return path.is_file() and hashlib.sha256(path.read_bytes()).hexdigest()==digest


def annotate_forecasts(ledger, evidence, root):
    """Attach old claims to their preserved response, without editing the claim."""
    receipts = {}
    for path in (root/"archive").glob("*.json"):
        body = json.loads(path.read_text())
        if body.get("kind") in ("surface","marine"):
            receipts[(body["portCode"],body["kind"],body["availableAt"])] = body
    for row in ledger.predictions(domain="weather"):
        if evidence.get("weather_forecast_annotations",row.prediction_id): continue
        kind = "marine" if row.model == "Open-Meteo marine" else "surface"
        snapshot = receipts.get((row.subject,kind,row.issued_at))
        if not snapshot: continue
        day = row.context.extra["targetDate"]
        field = {**FIELDS,"visibility":"visibility","wave_height":"wave_height"}.get(row.target)
        hours = [h for h in snapshot["rows"] if h["validAt"].startswith(day)]
        complete = complete_day([instant(h["validAt"]).strftime("%Y-%m-%dT%H:%M") for h in hours],day) and all(measurement(h.get(field)) for h in hours)
        evidence.put("weather_forecast_annotations",row.prediction_id,{
            "snapshotId":snapshot["snapshotId"],"responseSha256":snapshot["responseSha256"],
            "requestLocation":{"lat":snapshot["request"]["latitude"],"lon":snapshot["request"]["longitude"]},
            "aggregation":"daily UTC", "statistic": {"rainfall":"sum","visibility":"mean"}.get(row.target,"maximum"),
            "targetStart":day+"T00:00:00+00:00", "targetEnd":row.valid_at,
            "measurementWindow":sampling_window(day,row.target),
            "completeHours":24 if complete else len(hours),"complete":complete,
            "availabilityBasis":"original forecast response receipt; provider issue time unknown"})


def reconcile(*, db=None, root=None, now=None, fetch=None):
    from src.portwatch_os.intelligence.current_environment import FEEDBACK_DB, ROOT, FEEDBACK_REPORT, LOCK
    live_clock = now is None
    # wall-clock: default worker eligibility is the real collection present; explicit now is a deterministic query.
    db, root, now = Path(db or FEEDBACK_DB), Path(root or ROOT), instant(wall_now() if now is None else now)
    fetch = fetch or requests.get
    if not RUN_LOCK.acquire(blocking=False): return {"status":"RUNNING"}
    try:
        db.parent.mkdir(parents=True,exist_ok=True)
        ledger, evidence = SqliteLedgerStore(db), WeatherEvidenceStore(db)
        try:
            annotate_forecasts(ledger,evidence,root)
            rows = [r for r in ledger.predictions(domain="weather",status="open")
                    if r.model == "Open-Meteo surface" and r.target in FIELDS]
            retained={}
            eligible_rows=[]
            for row in rows:
                annotation=evidence.get("weather_forecast_annotations",row.prediction_id) or {}
                if not annotation.get("complete"): continue
                digest=annotation.get("responseSha256")
                if digest not in retained: retained[digest]=original_response_retained(annotation,root)
                if retained[digest]: eligible_rows.append(row)
            cutoff = (now-timedelta(days=LAG_DAYS)).date().isoformat()
            due = [r for r in eligible_rows if r.context.extra["targetDate"] <= cutoff]
            report = {"status":"WAITING_FOR_REANALYSIS" if not due else "COMPLETE",
                "checkedAt":now.isoformat(),"source":"Open-Meteo ERA5 archive","kind":"reanalysis",
                "availabilityBasis":"first successful receipt by PortWatch; provider publication time unknown",
                "conservativeLagDays":LAG_DAYS,"dueForecasts":len(due),"resolvedForecasts":0,
                "independentOutcomes":0,"requests":[],"failures":[],"incompleteTargets":[],
                "unsupportedVariables":["visibility","wave_height"],
                "nextEligibleAt":min(((instant(r.valid_at)+timedelta(days=LAG_DAYS-1)).isoformat() for r in eligible_rows),default=None),
                "unverifiableOriginals":len(rows)-len(eligible_rows)}
            for code in sorted({r.subject for r in due})[:13]:
                port = port_registry.resolve(code)
                days = sorted({r.context.extra["targetDate"] for r in due if r.subject == code})
                start, end = days[0], min(days[-1],(instant(days[0]+"T00:00:00+00:00")+timedelta(days=30)).date().isoformat())
                params = {"latitude":port.lat,"longitude":port.lon,"start_date":start,"end_date":end,
                    "hourly":",".join(FIELDS.values()),"models":"era5","timezone":"GMT","wind_speed_unit":"kn"}
                try:
                    response = fetch(URL,params=params,timeout=(4,25))
                    response.raise_for_status(); body=response.json()
                    if body.get("utc_offset_seconds") != 0 or any(body.get("hourly_units",{}).get(k)!=v for k,v in UNITS.items()):
                        raise ValueError("ERA5 hourly UTC units do not match")
                    from src.portwatch_os.intelligence.shipping_signals import distance
                    lat,lon=body.get("latitude"),body.get("longitude")
                    if not all(isinstance(v,(int,float)) and not isinstance(v,bool) and math.isfinite(v) for v in (lat,lon)) or not -90<=lat<=90 or not -180<=lon<=180 or distance((lat,lon),(port.lat,port.lon))>50:
                        raise ValueError("ERA5 response location is not a nearby grid cell")
                    hourly=body["hourly"]; times=hourly["time"]
                    # wall-clock: live provider availability starts after response return; explicit-time fixture runs retain their supplied clock.
                    receipt=(instant(wall_now()) if live_clock else now).isoformat()
                    digest=hashlib.sha256(response.content).hexdigest()
                    archive=root/"outcomes"; archive.mkdir(parents=True,exist_ok=True)
                    raw=archive/(digest+".response")
                    if not raw.exists(): raw.write_bytes(response.content)
                    report["requests"].append({"portCode":code,"params":params,"responseSha256":digest,"receivedAt":receipt})
                    for day in days:
                        indexes=[i for i,t in enumerate(times) if t[:10]==day]
                        if not complete_day([times[i] for i in indexes],day):
                            report["incompleteTargets"].append({"portCode":code,"day":day,"reason":"24 exact UTC hours unavailable"})
                            continue
                        valid=(instant(day+"T00:00:00+00:00")+timedelta(days=1)).isoformat()
                        for variable,field in FIELDS.items():
                            values=[hourly.get(field,[])[i] for i in indexes]
                            if any(not measurement(v) for v in values):
                                report["incompleteTargets"].append({"portCode":code,"day":day,"variable":variable,"reason":"Complete finite hourly measurements unavailable"})
                                continue
                            value=sum(values) if variable=="rainfall" else max(values)
                            key=outcome_key(code,variable,valid)
                            outcome=evidence.put("weather_outcome_evidence",key,{
                                "id":key,"portCode":code,"variable":variable,"value":value,"unit":"mm/day" if variable=="rainfall" else "kn",
                                "aggregation":"daily UTC","statistic":"sum" if variable=="rainfall" else "maximum",
                                "targetStart":day+"T00:00:00+00:00","validAt":valid,"availableAt":receipt,
                                "measurementWindow":sampling_window(day,variable),
                                "providerPublishedAt":None,"kind":"reanalysis","source":"Open-Meteo ERA5 archive",
                                "url":URL,"model":"era5","request":params,"responseSha256":digest,
                                "location":{"lat":body["latitude"],"lon":body["longitude"]},
                                "requestedLocation":{"lat":port.lat,"lon":port.lon},"completeHours":24,
                                "representativeness":"ERA5 grid cell at requested port coordinate; not a port station measurement"})
                            observation=WeatherObservation(code,variable,valid,outcome["availableAt"],outcome["value"],outcome["source"],"reanalysis",outcome["unit"],statistic=outcome["statistic"])
                            # Resolve only complete original aggregates, not partial old claims.
                            allowed={r.prediction_id for r in due if r.subject==code and r.target==variable and r.valid_at==valid}
                            report["resolvedForecasts"]+=WeatherFeedback(ledger).observe(observation,now=max(now,instant(receipt)),prediction_ids=allowed)
                except (requests.RequestException,ValueError,KeyError,IndexError,TypeError) as exc:
                    report["failures"].append({"portCode":code,"reason":str(exc)[:200]})
            report["independentOutcomes"]=len(evidence.outcomes())
            if report["failures"]: report["status"]="PROVIDER_UNAVAILABLE" if not report["resolvedForecasts"] else "PARTIAL"
            elif report["incompleteTargets"]: report["status"]="WAITING_FOR_COMPLETE_OUTCOMES" if not report["resolvedForecasts"] else "PARTIAL"
            # wall-clock: this live-worker completion report includes receipts obtained during this run; explicit queries stay pinned.
            feedback=WeatherFeedback(ledger).report(limit=10000,public_only=True,now=instant(wall_now()) if live_clock else now)
            feedback["reconciliation"]=report
            # Reconciliation and request-driven retention share the same report-file lock.
            target=FEEDBACK_REPORT if db==FEEDBACK_DB else db.with_suffix('.feedback.json')
            with LOCK:
                target.parent.mkdir(parents=True,exist_ok=True)
                temp=target.with_suffix('.tmp');temp.write_text(json.dumps(feedback,indent=2));temp.replace(target)
                status=root/"reconciliation.json";status.parent.mkdir(parents=True,exist_ok=True)
                temp=status.with_suffix('.tmp');temp.write_text(json.dumps(report,indent=2));temp.replace(status)
            return report
        finally:
            evidence.close();ledger.close()
    finally: RUN_LOCK.release()


def start():
    """An independent worker runs even when the original fabric scheduler is off."""
    import os
    global WORKER
    if os.getenv("PORTWATCH_WEATHER_RECONCILIATION","1").lower() in ("0","false","off"): return
    if WORKER and WORKER.is_alive(): return
    STOP.clear()
    def run():
        import logging
        while not STOP.is_set():
            try: reconcile()
            except Exception: logging.getLogger(__name__).exception("Weather reconciliation failed; retained evidence unchanged")
            STOP.wait(6*3600)
    WORKER=threading.Thread(target=run,name="weather-reconciliation",daemon=True);WORKER.start()


def stop():
    STOP.set()
