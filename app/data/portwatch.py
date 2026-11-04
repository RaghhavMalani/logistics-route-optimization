"""IMF PortWatch connector -- pulls the real datasets that power PortWatch.

Public ArcGIS feature services (no key). We use:
  * Daily_Ports_Data          -> daily per-port vessel port-calls (by type) +
                                 import/export trade-volume estimates (the real
                                 AIS-proxy + trade signal, satellite-derived).
  * Daily_Chokepoints_Data    -> daily transit calls for 28 chokepoints
                                 (Hormuz/Suez/Malacca...) vs baseline.
  * portwatch_disruptions_database / gdacs_events -> GDACS climate/disaster
                                 alerts intersected with ports (the climate layer).
  * PortWatch_ports_database  -> port metadata (embedded below for India).

Everything is fetched on your machine (where the network is open), cached to
data/portwatch/, and falls back to the cache if a refresh fails.

    python -m app.data.portwatch           # fetch + cache all India PortWatch data

Source: https://portwatch.imf.org/pages/data-and-methodology
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
CACHE = ROOT / "data" / "portwatch"
CACHE.mkdir(parents=True, exist_ok=True)
ORG = "https://services9.arcgis.com/weJ1QsnbMYJlCHdG/ArcGIS/rest/services"

# Real India ports (portid -> name, lat, lon) from PortWatch_ports_database.
INDIA_PORTS = {
    "port207": ("Kolkata (Syama Prasad Mookerjee)", 22.536, 88.300),
    "port235": ("Chennai", 13.100, 80.294),
    "port271": ("Dahej", 21.703, 72.575),
    "port290": ("Dhamra", 20.828, 86.960),
    "port442": ("Haldia", 22.058, 88.104),
    "port511": ("Jaigad", 17.295, 73.219),
    "port529": ("Kakinada", 16.987, 82.272),
    "port534": ("Kamarajar (Ennore)", 13.279, 80.339),
    "port540": ("Deendayal (Kandla)", 23.009, 70.216),
    "port544": ("Karaikal", 10.841, 79.843),
    "port583": ("Cochin (Kochi)", 9.969, 76.259),
    "port599": ("Krishnapatnam", 14.261, 80.118),
    "port679": ("Magdalla", 21.134, 72.677),
    "port709": ("Mormugao", 15.407, 73.802),
    "port776": ("Jawaharlal Nehru (Nhava Sheva)", 18.917, 72.940),
    "port777": ("Mundra", 22.763, 69.622),
    "port801": ("Navlakhi", 22.957, 70.452),
    "port811": ("New Mangalore", 12.938, 74.819),
    "port883": ("Paradip", 20.280, 86.649),
    "port907": ("Pipavav", 20.908, 71.466),
    "port1199": ("Sikka", 22.365, 69.808),
    "port1331": ("V.O. Chidambaranar (Tuticorin)", 8.766, 78.189),
    "port1367": ("Visakhapatnam", 17.655, 83.231),
    "port2038": ("Kattupalli", 13.303, 80.348),
    "port2039": ("Hazira", 21.087, 72.646),
    "port2150": ("Vizhinjam", 8.369, 76.994),
    "port2151": ("Karwar", 14.770, 74.134),
    "port2152": ("Port Blair", 11.677, 92.722),
    "port2299": ("Gopalpur", 19.291, 84.957),
    "port2344": ("Tuna", 22.906, 70.109),
    "port2378": ("Dabhol LNG", 17.534, 73.147),
    "port2430": ("Alang", 21.411, 72.198),
    "port2481": ("Chhara LNG", 20.720, 70.744),
}
# Short canonical ids for the systemic ports (used to join with the pipeline).
CANON = {
    "port776": "JNPT", "port777": "MUNDRA", "port540": "DEENDAYAL",
    "port235": "CHENNAI", "port207": "KOLKATA", "port442": "HALDIA",
    "port1367": "VIZAG", "port883": "PARADIP", "port583": "COCHIN",
    "port1331": "TUTICORIN", "port534": "KAMARAJAR", "port811": "NEW_MANGALORE",
    "port709": "MORMUGAO", "port599": "KRISHNAPATNAM", "port2038": "KATTUPALLI",
    "port2039": "HAZIRA",
}


def _requests():
    try:
        import requests
        return requests
    except Exception:
        return None


def _query(svc, where, order=None, fields="*", page=1000, max_records=200000, receipt_sink=None):
    """Paged ArcGIS query -> DataFrame (network required).

    NOTE: ArcGIS servers cap each response at their own maxRecordCount (1000
    for PortWatch) regardless of resultRecordCount, and signal a truncated
    page with `exceededTransferLimit`. The old loop stopped when a page came
    back smaller than *our* page size, which silently truncated every dataset
    to 1000 rows. We now keep paging while the server says there is more.
    Deterministic paging needs a stable sort -> daily layers order by date.
    """
    req = _requests()
    if req is None:
        raise RuntimeError("install requests: pip install requests")
    url = f"{ORG}/{svc}/FeatureServer/0/query"
    rows, offset = [], 0
    while True:
        params = {"where": where, "outFields": fields, "f": "json",
                  "returnGeometry": "false", "resultOffset": offset,
                  "resultRecordCount": page}
        if order:
            params["orderByFields"] = order
        elif svc.startswith("Daily_"):
            params["orderByFields"] = "date"
        r = req.get(url, params=params, timeout=60)
        if receipt_sink is not None:
            receipt_sink(r, dict(params))
        r.raise_for_status()
        body = r.json()
        if body.get("error"):
            raise RuntimeError("PortWatch ArcGIS source error: " + str(body["error"]))
        if not isinstance(body.get("features"), list):
            raise ValueError("PortWatch response lacks a features array")
        feats = body["features"]
        rows += [f.get("attributes", {}) for f in feats]
        more = body.get("exceededTransferLimit", False) and feats
        if len(rows) > max_records or (len(rows) >= max_records and more):
            raise ValueError("PortWatch response exceeds the bounded collection limit; truncated data was not accepted")
        if not more:
            break
        offset += len(feats)
    return pd.DataFrame(rows)


def _save(df, name):
    if df is not None and not df.empty:
        df.to_csv(CACHE / name, index=False)
    return df


def _cached(name):
    p = CACHE / name
    return pd.read_csv(p) if p.exists() else pd.DataFrame()


# ---------------------------------------------------------------------------
def fetch_port_activity(days: int = 400) -> pd.DataFrame:
    """Daily India port activity + trade (vessel calls by type, import/export).

    Also refreshes the per-port history files under data/portwatch/history/
    (date,portcalls,import,export per canonical pipeline port) that the
    forecasting pipeline's `--source portwatch` mode consumes.
    """
    since = (pd.Timestamp.today() - pd.Timedelta(days=days)).strftime("%Y-%m-%d")
    where = f"country='India' AND date>=DATE '{since}'"
    try:
        df = _query("Daily_Ports_Data", where, order="date")
        if not df.empty:
            df["canon"] = df["portid"].map(CANON).fillna(df["portid"])
            _save(df, "port_activity.csv")
            hist_dir = CACHE / "history"
            hist_dir.mkdir(exist_ok=True)
            for pid in CANON:
                g = df[df["portid"] == pid]
                if not g.empty:
                    (g[["date", "portcalls", "import", "export"]]
                       .sort_values("date")
                       .to_csv(hist_dir / f"{pid}.csv", index=False))
            return df
    except Exception as exc:
        print("port activity fetch failed:", exc)
    return _cached("port_activity.csv")


def fetch_chokepoints(days: int = 400) -> pd.DataFrame:
    since = (pd.Timestamp.today() - pd.Timedelta(days=days)).strftime("%Y-%m-%d")
    try:
        df = _query("Daily_Chokepoints_Data", f"date>=DATE '{since}'",
                    order="date", fields="date,portname,n_total")
        if not df.empty:
            return _save(df, "chokepoints.csv")
    except Exception as exc:
        print("chokepoint fetch failed:", exc)
    return _cached("chokepoints.csv")


def fetch_disruptions() -> pd.DataFrame:
    """GDACS climate/disaster disruptions intersected with ports."""
    for svc in ("portwatch_disruptions_database", "disruptions_with_ports",
                "gdacs_events"):
        try:
            df = _query(svc, "1=1", order="eventid", max_records=10000)
            if not df.empty:
                return _save(df, "disruptions.csv")
        except Exception as exc:
            print(f"disruptions ({svc}) failed:", exc)
    return _cached("disruptions.csv")


def port_activity_summary(df: pd.DataFrame | None = None) -> pd.DataFrame:
    """Latest + 30-day-trend activity per India port (for the pipeline / UI)."""
    df = df if df is not None else _cached("port_activity.csv")
    if df.empty:
        return pd.DataFrame()
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    rows = []
    for pid, g in df.sort_values("date").groupby("portid"):
        g = g.tail(60)
        last = g.iloc[-1]
        base = g["portcalls"].tail(30).mean() if "portcalls" in g else float("nan")
        name, lat, lon = INDIA_PORTS.get(pid, (pid, None, None))
        rows.append({
            "portid": pid, "canon": CANON.get(pid, pid), "name": name,
            "lat": lat, "lon": lon,
            "portcalls": int(last.get("portcalls", 0) or 0),
            "portcalls_baseline": round(float(base), 1) if base == base else None,
            "import_tonnes": int(last.get("import", 0) or 0),
            "export_tonnes": int(last.get("export", 0) or 0),
            "containers": int(last.get("portcalls_container", 0) or 0),
            "tankers": int(last.get("portcalls_tanker", 0) or 0),
            "dry_bulk": int(last.get("portcalls_dry_bulk", 0) or 0),
            "as_of": str(last["date"].date()) if pd.notna(last["date"]) else None,
        })
    return pd.DataFrame(rows)


def fetch_all(days: int = 400) -> dict:
    out = {"port_activity": fetch_port_activity(days),
           "chokepoints": fetch_chokepoints(),
           "disruptions": fetch_disruptions()}
    summ = port_activity_summary(out["port_activity"])
    _save(summ, "port_activity_summary.csv")
    out["summary"] = summ
    for k, v in out.items():
        print(f"{k}: {0 if v is None else len(v)} rows")
    return out


if __name__ == "__main__":
    fetch_all()
