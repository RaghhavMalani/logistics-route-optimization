"""Independent public weather/hazard snapshots, with immutable receipt clocks.

These do not re-date the IMF inputs or silently retrain the congestion model.
Open-Meteo forecasts have no issue/observation instant in this response; null
is intentional. Retrieval is availability, never a model-run issue time.
"""
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
import hashlib
import json
import math
import os
import shutil
from pathlib import Path
from threading import RLock
from concurrent.futures import ThreadPoolExecutor
import xml.etree.ElementTree as ET
import requests
from src.utils import port_registry
from src.portwatch_os.clock import wall_now

PACKAGED = Path(__file__).resolve().parents[3] / "data/cache/current_environment"
ROOT = Path(os.getenv("PORTWATCH_CURRENT_ENVIRONMENT_DIR") or PACKAGED)
FEEDBACK_DB = Path(os.getenv("PORTWATCH_WEATHER_FEEDBACK_DB") or PACKAGED.parents[2]/"work/capability-upgrades/learning-state/portwatch_ledger.db")
FEEDBACK_REPORT = Path(os.getenv("PORTWATCH_WEATHER_FEEDBACK_REPORT") or PACKAGED.parent/"public_weather_feedback.json")
# On a hosted persistent volume, seed public receipts once. Never replace a
# newer durable receipt or alter any archived bytes during a redeployment.
if ROOT != PACKAGED:
    for source in PACKAGED.rglob("*"):
        if source.is_file():
            target = ROOT/source.relative_to(PACKAGED)
            if not target.exists():
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(source, target)
    seed = PACKAGED.parent/"public_weather_forecasts.sqlite3"
    if seed.exists() and not FEEDBACK_DB.exists():
        FEEDBACK_DB.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(seed, FEEDBACK_DB)
    elif seed.exists():
        # An older deployment may already have collected new public forecasts.
        # Merge missing historical claims; never replace its durable database.
        from src.portwatch_os.ledger.store import SqliteLedgerStore
        packaged_ledger, durable_ledger = SqliteLedgerStore(seed), SqliteLedgerStore(FEEDBACK_DB)
        for prediction in packaged_ledger.predictions(domain="weather"):
            if durable_ledger.get_prediction(prediction.prediction_id) is None:
                durable_ledger.record_prediction(prediction)
        packaged_ledger.close(); durable_ledger.close()
LOCK = RLock()
REFRESH_WORKERS = ThreadPoolExecutor(max_workers=3, thread_name_prefix="public-environment")
PENDING = set()
ATTEMPTED = {}
TTL = {"surface": 3600, "marine": 3600, "hazards": 1800}
URLS = {"surface": "https://api.open-meteo.com/v1/forecast",
        "marine": "https://marine-api.open-meteo.com/v1/marine",
        "hazards": "https://www.gdacs.org/xml/rss.xml"}


def instant(value):
    dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt.astimezone(timezone.utc)


def finite(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def _path(kind, port):
    return ROOT / (kind + ("" if kind == "hazards" else "-" + port.locode) + ".json")


def dated(snapshot, now=None):
    now = now or wall_now()
    age = max(0, (now - instant(snapshot["availableAt"])).total_seconds())
    return {**snapshot, "ageHours": round(age/3600, 2),
            "status": "CURRENT" if age <= TTL[snapshot["kind"]] else "STALE"}


def read(kind, port):
    path = _path(kind, port)
    return dated(json.loads(path.read_text(encoding="utf-8"))) if path.exists() else {
        "kind": kind, "status": "UNAVAILABLE", "rows": [], "availableAt": None,
        "issuedAt": None, "observedAt": None, "source": URLS[kind]}


def _hazards(text, now):
    rows = {}
    for item in ET.fromstring(text).findall(".//item"):
        fields = {e.tag.split("}")[-1]: (e.text or "").strip() for e in item}
        try:
            published = parsedate_to_datetime(fields["pubDate"])
            start = parsedate_to_datetime(fields["fromdate"])
            end = parsedate_to_datetime(fields["todate"])
            lat, lon = map(float, fields["point"].split())
            if not (-90 <= lat <= 90 and -180 <= lon <= 180) or published > now or end < now-timedelta(days=7):
                continue
            identifier = fields["eventtype"] + ":" + fields["eventid"]
            row = {"id": identifier, "title": fields["title"], "lat": lat, "lon": lon,
                   "kind": fields["eventtype"], "alertLevel": fields["alertlevel"],
                   "publishedAt": published.isoformat(), "validFrom": start.isoformat(), "validThrough": end.isoformat(),
                   "observedAt": start.isoformat(), "source": fields.get("link"),
                   "relationship": "Regional hazard context; no port closure or shipping delay inferred."}
            if identifier not in rows or row["publishedAt"] > rows[identifier]["publishedAt"]:
                rows[identifier] = row
        except (KeyError, ValueError, TypeError):
            continue
    return list(rows.values())


def refresh(kind, port, *, force=False):
    """Fixed providers only, bounded calls, retain old timestamps on failure."""
    with LOCK:
        previous = read(kind, port)
        if not force and previous["status"] == "CURRENT":
            return previous
    params = {}
    if kind == "surface":
        params = {"latitude": port.lat, "longitude": port.lon, "timezone": "GMT", "wind_speed_unit": "kn",
                  "hourly": "wind_speed_10m,wind_gusts_10m,wind_direction_10m,precipitation,visibility", "forecast_days": 10}
    elif kind == "marine":
        params = {"latitude": port.lat-.15, "longitude": port.lon+(.15 if port.coast == "east" else -.15),
                  "timezone": "GMT", "hourly": "wave_height", "forecast_days": 8}
    try:
        response = requests.get(URLS[kind], params=params, headers={"User-Agent": "PortWatch-Capstone/1.0"}, timeout=(4, 18))
        response.raise_for_status()
        at = wall_now()
        if kind == "hazards":
            rows = _hazards(response.text, at)
            units = {}
        else:
            data = response.json(); hourly = data["hourly"]; units = data["hourly_units"]
            expected = {"wind_speed_10m":"kn", "wind_gusts_10m":"kn", "wind_direction_10m":"°", "precipitation":"mm", "visibility":"m"} if kind == "surface" else {"wave_height":"m"}
            fields = list(expected)
            if not hourly["time"] or any(field not in hourly or units.get(field) != unit for field, unit in expected.items()):
                raise ValueError("No hourly weather response")
            rows = [{"validAt": instant(t).isoformat(), **{
                f: hourly[f][i] if i < len(hourly[f]) and finite(hourly[f][i]) else None for f in fields}}
                for i, t in enumerate(hourly["time"])][:240]
        snapshot = {"kind": kind, "portCode": port.locode if kind != "hazards" else None,
                    "source": URLS[kind], "issuedAt": None, "observedAt": None,
                    "availableAt": at.isoformat(), "fetchedAt": at.isoformat(), "rows": rows, "units": units,
                    "request": params, "responseSha256": hashlib.sha256(response.content).hexdigest(),
                    "timeBasis": "Forecast issue time unavailable; response receipt is availability. Hazard event/publication clocks are retained per item.",
                    "rights": "Open-Meteo non-commercial API / CC BY 4.0" if kind != "hazards" else "GDACS public alert feed; linked source notices apply."}
        snapshot["snapshotId"] = hashlib.sha256(json.dumps(snapshot, sort_keys=True).encode()).hexdigest()
        with LOCK:
            ROOT.mkdir(parents=True, exist_ok=True)
            archive = ROOT / "archive"; archive.mkdir(exist_ok=True)
            (archive/(snapshot["snapshotId"]+".json")).write_text(json.dumps(snapshot), encoding="utf-8")
            (archive/(snapshot["responseSha256"]+".response")).write_bytes(response.content)
            path = _path(kind, port); temp = path.with_suffix(".tmp")
            temp.write_text(json.dumps(snapshot), encoding="utf-8"); temp.replace(path)
        return dated(snapshot)
    except (requests.RequestException, ValueError, KeyError, TypeError, ET.ParseError):
        return {**previous, "status": "STALE" if previous.get("availableAt") else "UNAVAILABLE",
                "reason": "Provider refresh failed; previous receipt time retained."}


def bundle(port, *, allow_fetch=True):
    snapshots = {kind: refresh(kind, port) if allow_fetch else read(kind, port) for kind in TTL}
    waves = {r["validAt"]: r["wave_height"] for r in snapshots["marine"]["rows"]}
    hourly = [{**r, "wave_height": waves.get(r["validAt"])} for r in snapshots["surface"]["rows"]]
    regional = [r for r in snapshots["hazards"]["rows"] if 0 <= r["lat"] <= 35 and 45 <= r["lon"] <= 100]
    days = {}
    for row in hourly:
        day = row["validAt"][:10]
        group = days.setdefault(day, [])
        group.append(row)
    daily = []
    for day, rows in sorted(days.items()):
        def aggregate(field, method):
            values = [r[field] for r in rows if finite(r.get(field))]
            return method(values) if len(values) == 24 and len({r['validAt'] for r in rows}) == 24 else None
        daily.append({"date": day, "wind_speed": aggregate("wind_speed_10m", max),
            "wind_gust": aggregate("wind_gusts_10m", max), "rainfall": aggregate("precipitation", sum),
            "visibility": aggregate("visibility", lambda v: sum(v)/len(v)/1000),
            "wave_height": aggregate("wave_height", max), "observed": None, "error": None,
            "matchStatus": "UNMATCHED", "correctionStatus": "COLLECTING"})
    return {"portCode": port.locode, "portName": port.name, "sources": snapshots,
            "hourly": hourly, "daily": daily, "regionalHazards": regional,
            "note": "Current forecasts and dated hazard context are independent of lagging IMF activity. No forecast is an observation."}


def map_signals():
    """The original renderer's contract, with actual hourly forecast fields."""
    signals = []
    for port in port_registry.PORTS:
        data = bundle(port, allow_fetch=False)
        if data["sources"]["surface"]["status"] != "CURRENT":
            continue
        rows = [r for r in data["hourly"] if instant(r["validAt"]) >= wall_now().replace(minute=0, second=0, microsecond=0)]
        if not rows: continue
        first = rows[0]
        signals.append({"portCode": port.locode, "name": port.name, "observedAt": None,
            "forecastFrom": first["validAt"], "availableAt": data["sources"]["surface"]["availableAt"],
            "sourceState": "FORECAST", "hourly": rows, "forecast": [], "impactScore": 0,
            "windKnots": first["wind_speed_10m"], "gustKnots": first["wind_gusts_10m"],
            "rainfallMm24h": data["daily"][0]["rainfall"], "waveHeightM": first.get("wave_height"),
            "visibilityKm": first["visibility"]/1000 if finite(first["visibility"]) else None,
            "seaState": None, "windRisk": None, "rainRisk": None, "waveRisk": None, "stormRisk": None,
            "confidence": None, "weatherRegime": None, "shockScore": None, "persistenceScore": None,
            "forwardLoad": None, "advisory": "Hourly public forecast, not a station observation or congestion forecast input.",
            "dataSource": "Open-Meteo independently refreshed surface/marine forecasts"})
    return signals


def ensure_current():
    """Warm expired fixed public sources without blocking the original map contract.

    Three workers, one task per port, five-minute retry backoff after failures.
    Old receipt times survive refresh errors and are never presented as current.
    """
    now = wall_now()
    def collect(port):
        try:
            refresh("surface", port)
            refresh("marine", port)
            # Archive future forecast targets prospectively. No outcomes are invented.
            retain_feedback(port)
        finally:
            with LOCK: PENDING.discard(port.locode)
    for port in port_registry.PORTS:
        with LOCK:
            expired = any(read(kind, port)["status"] != "CURRENT" for kind in ("surface", "marine"))
            attempted = ATTEMPTED.get(port.locode)
            if not expired or port.locode in PENDING or (attempted and now-attempted < timedelta(minutes=5)):
                continue
            PENDING.add(port.locode); ATTEMPTED[port.locode] = now
        REFRESH_WORKERS.submit(collect, port)
    with LOCK:
        attempted = ATTEMPTED.get("hazards")
        needed = read("hazards", port_registry.PORTS[0])["status"] != "CURRENT"
        if needed and (not attempted or now-attempted >= timedelta(minutes=5)):
            ATTEMPTED["hazards"] = now
            REFRESH_WORKERS.submit(refresh, "hazards", port_registry.PORTS[0])


def retain_feedback(port):
    """Receipt clock is the archive's available forecast origin, not provider issue time."""
    import pandas as pd
    from src.portwatch_os.ledger.store import SqliteLedgerStore
    from src.portwatch_os.learning.weather_feedback import WeatherFeedback
    from src.utils.config import PORT_ID, DATE
    data = bundle(port, allow_fetch=False)
    frame = pd.DataFrame([{PORT_ID: port.model_id, DATE: r["date"], **r} for r in data["daily"]])
    if frame.empty: return
    with LOCK:
        ledger = SqliteLedgerStore(FEEDBACK_DB)
        feedback = WeatherFeedback(ledger)
        for kind, provider, variables in (("surface", "Open-Meteo surface", ("wind_speed", "wind_gust", "rainfall", "visibility")), ("marine", "Open-Meteo marine", ("wave_height",))):
            source = data["sources"][kind]
            if source["status"] == "CURRENT":
                feedback.record_frame(frame, issued_at=instant(source["availableAt"]), provider=provider,
                    source_state="CACHED_LIVE", variables=variables, now=wall_now(),provenance={
                        "snapshotId":source.get("snapshotId"),"responseSha256":source.get("responseSha256"),
                        "requestLocation":{k:source.get("request",{}).get(v) for k,v in (("lat","latitude"),("lon","longitude"))},
                        "completeHours":24,"aggregation":"complete UTC day"})
        report = feedback.report(limit=10000, public_only=True)
        report["scope"] = "Public forecast archive. Origin is receipt availability; provider issue/observation times unavailable. No observation match is inferred."
        ledger.close()
        target = FEEDBACK_REPORT
        target.parent.mkdir(parents=True, exist_ok=True)
        temporary = target.with_suffix(".tmp")
        temporary.write_text(json.dumps(report, indent=2), encoding="utf-8"); temporary.replace(target)
