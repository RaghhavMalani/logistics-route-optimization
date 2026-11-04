"""Normalized public capability snapshots. Ingesters call collect; API reads call retained."""
import json
import os
from pathlib import Path
from tempfile import NamedTemporaryFile

import requests

from src.portwatch_os.clock import wall_now, world_now
from src.portwatch_os.intelligence import current_environment

TTL = {"aircraft": 60, "satellites": 7200, "cyclones": 1800, "infrastructure": 21600}
SOURCES = {
    "aircraft": (
        'https://api.adsb.lol/docs',
        'Volunteer ADS-B coverage within 250 nautical miles of the selected port; not complete airspace coverage. ODbL.',
    ),
    "satellites": (
        'https://celestrak.org/NORAD/documentation/gp-data-formats.php',
        'Stations catalogue only. SGP4 positions are computed from published orbital elements at the current UTC time, not observations of port activity. Elements older than seven days are withheld from the globe.',
    ),
    "cyclones": (
        'https://www.nhc.noaa.gov/productexamples/',
        'NHC Atlantic and eastern/central Pacific coverage; Indian Ocean storms remain in the GDACS/event adapter.',
    ),
    "infrastructure": (
        'https://www.openstreetmap.org/copyright',
        'Mapped roads, rail, industrial land, warehouses and power infrastructure within 0.18° of the port; map coverage is not current congestion. OSM contributors / ODbL.',
    ),
}


def _path(layer, port):
    scope = port.locode if layer in ("aircraft", "infrastructure") else "global"
    return current_environment.ROOT / "capability_layers" / f"{layer}-{scope}.json"


def _empty(layer, port, reason):
    source, coverage = SOURCES[layer]
    return {"status": "UNAVAILABLE", "features": [], "records": [], "source": source,
            "coverage": coverage, "layer": layer, "portCode": port.locode, "fetchedAt": None,
            "reason": reason}


def retained(layer, port):
    try:
        packet = json.loads(_path(layer, port).read_text(encoding="utf-8"))
        fetched = current_environment.instant(packet["fetchedAt"])
        now = world_now()
        if fetched > now or not isinstance(packet["features"], list) or not isinstance(packet["records"], list):
            raise ValueError("Invalid snapshot or future receipt")
    except (OSError, ValueError, TypeError, KeyError):
        return _empty(layer, port, "No usable retained provider snapshot")
    packet["portCode"] = port.locode
    if (now - fetched).total_seconds() >= TTL[layer]:
        return {**packet, "status": "STALE", "reason": "Retained snapshot exceeded its refresh interval"}
    return packet


def collect(layer, port):
    """Fetch from the fixed reviewed provider and atomically publish a normalized snapshot."""
    features = []
    records = []
    source, coverage = SOURCES[layer]
    try:
        if layer == "aircraft":
            response=requests.get(f"https://api.adsb.lol/v2/point/{port.lat}/{port.lon}/250",timeout=(3,8)); response.raise_for_status()
            data=response.json()
            if not isinstance(data.get("ac"),list): raise ValueError("Malformed ADS-B response")
            for a in (data.get("ac") or [])[:1500]:
                if isinstance(a.get("lat"),(int,float)) and isinstance(a.get("lon"),(int,float)):
                    features.append({"id":a.get("hex"),"name":(a.get("flight") or a.get("hex") or "Aircraft").strip(),
                        "lat":a["lat"],"lon":a["lon"],"altitudeFt":a.get("alt_baro"),"ageSeconds":a.get("seen_pos"),"kind":"aircraft"})
        elif layer == "satellites":
            response=requests.get("https://celestrak.org/NORAD/elements/gp.php?GROUP=stations&FORMAT=json",timeout=(3,8))
            response.raise_for_status(); records=response.json()
            if not isinstance(records,list): raise ValueError("Malformed orbital elements")
            fields=("EPOCH","MEAN_MOTION","ECCENTRICITY","INCLINATION","RA_OF_ASC_NODE","ARG_OF_PERICENTER","MEAN_ANOMALY","BSTAR","NORAD_CAT_ID","MEAN_MOTION_DOT","MEAN_MOTION_DDOT","ELEMENT_SET_NO","OBJECT_NAME","OBJECT_ID")
            records=[r for r in records[:100] if isinstance(r,dict) and all(k in r for k in fields)]
            if not records: raise ValueError("No usable orbital elements")
        elif layer == "cyclones":
            response=requests.get("https://www.nhc.noaa.gov/CurrentStorms.json",timeout=(3,8)); response.raise_for_status()
            for s in response.json().get("activeStorms",[]):
                if isinstance(s.get("latitude"),(int,float)) and isinstance(s.get("longitude"),(int,float)):
                    features.append({"id":s.get("id"),"name":s.get("name"),"lat":s["latitude"],"lon":s["longitude"],"kind":"cyclone","observedAt":s.get("lastUpdate")})
        else:
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
        result = {"status": "CACHED", "fetchedAt": wall_now().isoformat(), "source": source,
                  "coverage": coverage, "features": features, "records": records,
                  "layer": layer, "portCode": port.locode}
        path = _path(layer, port)
        path.parent.mkdir(parents=True, exist_ok=True)
        with NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent, delete=False) as stream:
            temporary = Path(stream.name)
            try:
                json.dump(result, stream, allow_nan=False)
            except Exception:
                stream.close()
                temporary.unlink(missing_ok=True)
                raise
        try:
            os.replace(temporary, path)
        finally:
            temporary.unlink(missing_ok=True)
        return result
    except (requests.RequestException, OSError, ValueError, TypeError, KeyError):
        return retained(layer, port)
