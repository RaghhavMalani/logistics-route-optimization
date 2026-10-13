"""Bounded intelligence adapters and measured candidate results in the terminal."""
from __future__ import annotations
import json
import os
from datetime import timedelta
from pathlib import Path
from threading import RLock
from typing import Literal
import requests
from fastapi import APIRouter, Query, HTTPException
from backend.app.services import cache_service as cache
from src.portwatch_os.clock import world_now, get_clock, LIVE
from src.utils import port_registry
from src.utils.config import FORECASTS_DIR

router = APIRouter()
_CACHE = {}
_LOCK = RLock()


@router.get("/learning/experiments")
def experiments():
    results = {}
    for key in ("neural_fusion", "constrained_rl"):
        path = Path(os.getenv("PORTWATCH_EXPERIMENT_DIR") or FORECASTS_DIR) / (key+"_report.json")
        results[key] = json.loads(path.read_text()) if path.exists() else {"status":"UNTRAINED"}
    inference = FORECASTS_DIR / "neural_fusion_live.csv"
    results["neural_fusion"]["shadowInferenceAvailable"] = inference.exists()
    results["freshness"] = cache.get_live_status()
    return results


@router.get("/intelligence/layer/{layer}")
def layer(layer: Literal["aircraft", "satellites", "cyclones", "infrastructure"],
          portCode: str = Query("INNSA")):
    port = port_registry.resolve(portCode)
    if port is None:
        raise HTTPException(404,"Port is not registered")
    if get_clock().state.mode != LIVE:
        return {"status":"HISTORICAL_UNAVAILABLE","features":[],"records":[],
                "source":"", "coverage":"Current provider data is withheld during replay.",
                "layer":layer,"portCode":port.locode,"fetchedAt":None,
                "reason":"No issue-time archive for this layer"}
    key = (layer,port.locode if layer in ("aircraft","infrastructure") else "global")
    now = world_now()
    ttl = {"aircraft":60,"satellites":7200,"cyclones":1800,"infrastructure":21600}[layer]
    with _LOCK:
        before = _CACHE.get(key)
        if before and (now-before[0]).total_seconds()<ttl:
            return before[1]
    features=[]; records=[]; source=""; coverage=""
    try:
        if layer == "aircraft":
            source="https://api.adsb.lol/docs"
            coverage="Volunteer ADS-B coverage within 250 nautical miles of the selected port; not complete airspace coverage. ODbL."
            response=requests.get(f"https://api.adsb.lol/v2/point/{port.lat}/{port.lon}/250",timeout=(3,8)); response.raise_for_status()
            data=response.json()
            if not isinstance(data.get("ac"),list): raise ValueError("Malformed ADS-B response")
            for a in (data.get("ac") or [])[:1500]:
                if isinstance(a.get("lat"),(int,float)) and isinstance(a.get("lon"),(int,float)):
                    features.append({"id":a.get("hex"),"name":(a.get("flight") or a.get("hex") or "Aircraft").strip(),
                        "lat":a["lat"],"lon":a["lon"],"altitudeFt":a.get("alt_baro"),"ageSeconds":a.get("seen_pos"),"kind":"aircraft"})
        elif layer == "satellites":
            source="https://celestrak.org/NORAD/documentation/gp-data-formats.php"
            coverage="Stations catalogue only. SGP4 positions are computed from published orbital elements at the current UTC time, not observations of port activity. Elements older than seven days are withheld from the globe."
            response=requests.get("https://celestrak.org/NORAD/elements/gp.php?GROUP=stations&FORMAT=json",timeout=(3,8))
            response.raise_for_status(); records=response.json()
            if not isinstance(records,list): raise ValueError("Malformed orbital elements")
            fields=("EPOCH","MEAN_MOTION","ECCENTRICITY","INCLINATION","RA_OF_ASC_NODE","ARG_OF_PERICENTER","MEAN_ANOMALY","BSTAR","NORAD_CAT_ID","MEAN_MOTION_DOT","MEAN_MOTION_DDOT","ELEMENT_SET_NO","OBJECT_NAME","OBJECT_ID")
            records=[r for r in records[:100] if isinstance(r,dict) and all(k in r for k in fields)]
            if not records: raise ValueError("No usable orbital elements")
        elif layer == "cyclones":
            source="https://www.nhc.noaa.gov/productexamples/"
            coverage="NHC Atlantic and eastern/central Pacific coverage; Indian Ocean storms remain in the GDACS/event adapter."
            response=requests.get("https://www.nhc.noaa.gov/CurrentStorms.json",timeout=(3,8)); response.raise_for_status()
            for s in response.json().get("activeStorms",[]):
                if isinstance(s.get("latitude"),(int,float)) and isinstance(s.get("longitude"),(int,float)):
                    features.append({"id":s.get("id"),"name":s.get("name"),"lat":s["latitude"],"lon":s["longitude"],"kind":"cyclone","observedAt":s.get("lastUpdate")})
        else:
            source="https://www.openstreetmap.org/copyright"
            coverage="Mapped roads, rail, industrial land, warehouses and power infrastructure within 0.18° of the port; map coverage is not current congestion. OSM contributors / ODbL."
            lat,lon=port.lat,port.lon
            box=f"{lat-.18},{lon-.18},{lat+.18},{lon+.18}"
            query=f'[out:json][timeout:8];(way[highway~"^(motorway|trunk|primary|secondary)$"]({box});way[railway=rail]({box});way[landuse=industrial]({box});way[building=warehouse]({box});way[power=substation]({box}); );out geom qt 600;'
            response=requests.get("https://overpass.private.coffee/api/interpreter",params={"data":query},
                headers={"Accept":"application/json","User-Agent":"PortWatch-Capstone/1.0"},timeout=(3,12));response.raise_for_status()
            for e in response.json().get("elements",[])[:600]:
                geometry=[p for p in e.get("geometry",[]) if isinstance(p.get("lat"),(int,float))
                          and isinstance(p.get("lon"),(int,float)) and -90<=p["lat"]<=90 and -180<=p["lon"]<=180]
                c=e.get("center") or {}
                if not c and geometry:
                    # out geom returns bounds/geometry, not a centre. Match the
                    # documented bounding-box midpoint; not a surveyed centroid.
                    c={"lat":(min(p["lat"] for p in geometry)+max(p["lat"] for p in geometry))/2,
                       "lon":(min(p["lon"] for p in geometry)+max(p["lon"] for p in geometry))/2}
                tags=e.get("tags") or {}
                if "lat" in c and "lon" in c:
                    features.append({"id":str(e["id"]),"name":tags.get("name") or tags.get("highway") or tags.get("railway") or "Infrastructure",
                        "lat":c["lat"],"lon":c["lon"],"kind":"rail" if tags.get("railway") else "infrastructure",
                        "geometry":[[p["lon"],p["lat"]] for p in geometry],"tags":tags})
        result={"status":"CACHED","fetchedAt":now.isoformat(),"source":source,"coverage":coverage,
                "features":features,"records":records,"layer":layer,"portCode":port.locode}
        with _LOCK: _CACHE[key]=(now,result)
        return result
    except (requests.RequestException,ValueError,TypeError,KeyError) as exc:
        if before:
            return {**before[1],"status":"STALE","reason":"Provider refresh failed"}
        return {"status":"UNAVAILABLE","features":[],"records":[],"source":source,"coverage":coverage,"reason":"Provider returned no usable response"}
