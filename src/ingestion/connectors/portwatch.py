"""IMF PortWatch connector.

PortWatch (IMF + University of Oxford) publishes daily port-activity and
chokepoint transit estimates for 2,065 ports and 28 chokepoints, derived from
satellite AIS on ~90k ships, hosted as ArcGIS feature layers. It even ships a
disruption-simulation tool -- conceptually the same thing as our scenario
engine, which makes it the ideal real-data backbone.

This module exposes:
  * CHOKEPOINTS            : metadata for the chokepoints relevant to India
                             (location, reroute penalty, commodities, coasts).
  * PORT_CHOKEPOINT_EXPOSURE: how exposed each of our ports is to each chokepoint.
  * fetch_chokepoint_status(): recent transit vs. baseline (live -> cache ->
                             synthetic), used by the terminal watchlist + scenario engine.

Live data: set PORTWATCH_CHOKEPOINTS_URL to the ArcGIS FeatureServer query URL
(see portwatch.imf.org "Data & Methodology"). If unset/unreachable we fall back
to a deterministic synthetic snapshot so the demo always works.

Source: https://portwatch.imf.org/pages/data-and-methodology
"""

from __future__ import annotations

from src.utils.settings import get_settings

from typing import Dict

import numpy as np
import pandas as pd

from src.ingestion.connectors.base import cached_json
from src.utils.logging_utils import get_logger

log = get_logger(__name__)

# Live IMF PortWatch ArcGIS endpoint (public, no key). Override via env if needed.
PORTWATCH_CHOKEPOINTS_URL = get_settings().get(
    "PORTWATCH_CHOKEPOINTS_URL",
    "https://services9.arcgis.com/weJ1QsnbMYJlCHdG/ArcGIS/rest/services/"
    "Daily_Chokepoints_Data/FeatureServer/0/query")

# Map PortWatch chokepoint names -> our internal ids.
_PW_NAME_MAP = {
    "suez": "SUEZ", "bab": "BAB_EL_MANDEB", "hormuz": "HORMUZ",
    "malacca": "MALACCA", "panama": "PANAMA", "good hope": "GOOD_HOPE",
}

# Chokepoints most relevant to Indian maritime trade.
# reroute_days = extra steaming time if the chokepoint is unusable.
CHOKEPOINTS: Dict[str, dict] = {
    "HORMUZ": {"name": "Strait of Hormuz", "lat": 26.6, "lon": 56.3,
               "reroute_days": 0, "no_alt": True,  # no maritime bypass for Gulf oil
               "commodities": ["crude_oil", "lng"], "coasts": ["West"]},
    "BAB_EL_MANDEB": {"name": "Bab-el-Mandeb / Red Sea", "lat": 12.6, "lon": 43.3,
                      "reroute_days": 12, "no_alt": False,  # via Cape of Good Hope
                      "commodities": ["crude_oil", "containers"], "coasts": ["West", "East"]},
    "SUEZ": {"name": "Suez Canal", "lat": 30.0, "lon": 32.55,
             "reroute_days": 12, "no_alt": False,
             "commodities": ["containers", "crude_oil"], "coasts": ["West", "East"]},
    "MALACCA": {"name": "Strait of Malacca", "lat": 2.5, "lon": 101.0,
                "reroute_days": 4, "no_alt": False,  # via Lombok/Sunda
                "commodities": ["containers", "crude_oil"], "coasts": ["East"]},
    "GOOD_HOPE": {"name": "Cape of Good Hope (reroute node)", "lat": -34.4, "lon": 18.5,
                  "reroute_days": 0, "no_alt": False,
                  "commodities": ["containers"], "coasts": []},
    "PANAMA": {"name": "Panama Canal", "lat": 9.1, "lon": -79.7,
               "reroute_days": 8, "no_alt": False,
               "commodities": ["containers"], "coasts": []},
}

# Exposure weight (0..1) of each of OUR ports to each chokepoint, by trade routes.
PORT_CHOKEPOINT_EXPOSURE: Dict[str, Dict[str, float]] = {
    "JNPT":    {"HORMUZ": 0.45, "SUEZ": 0.40, "BAB_EL_MANDEB": 0.40, "MALACCA": 0.20},
    "MUNDRA":  {"HORMUZ": 0.55, "SUEZ": 0.35, "BAB_EL_MANDEB": 0.35, "MALACCA": 0.15},
    "COCHIN":  {"HORMUZ": 0.40, "SUEZ": 0.30, "BAB_EL_MANDEB": 0.30, "MALACCA": 0.25},
    "CHENNAI": {"HORMUZ": 0.25, "SUEZ": 0.25, "BAB_EL_MANDEB": 0.25, "MALACCA": 0.55},
    "VIZAG":   {"HORMUZ": 0.25, "SUEZ": 0.20, "BAB_EL_MANDEB": 0.20, "MALACCA": 0.60},
    "KOLKATA": {"HORMUZ": 0.20, "SUEZ": 0.20, "BAB_EL_MANDEB": 0.20, "MALACCA": 0.65},
}


# Coast-based exposure templates for ports not explicitly listed above.
_COAST_EXPOSURE = {
    "West":  {"HORMUZ": 0.45, "SUEZ": 0.35, "BAB_EL_MANDEB": 0.35, "MALACCA": 0.18},
    "South": {"HORMUZ": 0.35, "SUEZ": 0.30, "BAB_EL_MANDEB": 0.30, "MALACCA": 0.35},
    "East":  {"HORMUZ": 0.22, "SUEZ": 0.22, "BAB_EL_MANDEB": 0.22, "MALACCA": 0.60},
}


def port_exposure(port_id: str) -> Dict[str, float]:
    """Explicit exposure if known, else derive from the port's coast/region."""
    pid = port_id.upper()
    if pid in PORT_CHOKEPOINT_EXPOSURE:
        return PORT_CHOKEPOINT_EXPOSURE[pid]
    try:
        from src.utils.config import PORT_BY_ID
        region = PORT_BY_ID[pid].region if pid in PORT_BY_ID else "West"
    except Exception:
        region = "West"
    return _COAST_EXPOSURE.get(region, _COAST_EXPOSURE["West"])


def fetch_chokepoint_status(days: int = 30) -> pd.DataFrame:
    """Recent transit calls vs. baseline per chokepoint.

    Returns columns: chokepoint, name, date, transit_calls, baseline,
    vs_baseline_pct, status. Tries the live ArcGIS layer, else synthesises a
    plausible, deterministic snapshot.
    """
    from src.utils import provenance
    if PORTWATCH_CHOKEPOINTS_URL:
        data = cached_json(
            PORTWATCH_CHOKEPOINTS_URL, key="portwatch_chokepoints", ttl=6 * 3600,
            params={"where": "1=1", "outFields": "date,portname,n_total",
                    "orderByFields": "date DESC", "resultRecordCount": 4000,
                    "f": "json"})
        df = _parse_live(data)
        if df is not None and not df.empty:
            provenance.record("Chokepoints (IMF PortWatch)", provenance.LIVE)
            log.info("PortWatch: live chokepoint data (%d points).", len(df))
            return df
        log.warning("PortWatch live parse empty; using synthetic snapshot.")
    provenance.record("Chokepoints (IMF PortWatch)", provenance.SYNTHETIC,
                      "PortWatch unreachable")
    return _synthetic_status(days)


def _parse_live(data) -> pd.DataFrame | None:
    """Parse the live PortWatch schema into latest transit vs. baseline."""
    if not data or not data.get("features"):
        return None
    rows = [f.get("attributes", {}) for f in data["features"]]
    raw = pd.DataFrame(rows)
    if raw.empty or "portname" not in raw.columns or "n_total" not in raw.columns:
        return None
    raw["date"] = pd.to_datetime(raw["date"], errors="coerce")
    raw["n_total"] = pd.to_numeric(raw["n_total"], errors="coerce")
    raw = raw.dropna(subset=["date", "n_total"])
    out = []
    for name, g in raw.groupby("portname"):
        g = g.sort_values("date")
        baseline = float(g["n_total"].tail(90).mean())
        latest = float(g["n_total"].iloc[-1])
        cur7 = float(g["n_total"].tail(7).mean())   # smooth the latest reading
        factor = cur7 / baseline if baseline else 1.0
        cid = _match_id(name)
        out.append({"chokepoint": cid or name, "name": name,
                    "date": g["date"].iloc[-1], "transit_calls": round(cur7, 1),
                    "baseline": round(baseline, 1),
                    "vs_baseline_pct": round((factor - 1) * 100, 1),
                    "status": _status(factor)})
    return pd.DataFrame(out)


def _match_id(name: str):
    n = (name or "").lower()
    for key, cid in _PW_NAME_MAP.items():
        if key in n:
            return cid
    return None


def _parse_arcgis(data) -> pd.DataFrame | None:
    if not data or "features" not in data:
        return None
    rows = [f.get("attributes", {}) for f in data["features"]]
    if not rows:
        return None
    df = pd.DataFrame(rows)
    # PortWatch field names vary; best-effort normalisation.
    rename = {}
    for c in df.columns:
        lc = c.lower()
        if "portname" in lc or "chokepoint" in lc or lc == "name":
            rename[c] = "name"
        elif "date" in lc:
            rename[c] = "date"
        elif "transit" in lc or "n_calls" in lc or "calls" in lc:
            rename[c] = "transit_calls"
    df = df.rename(columns=rename)
    if "date" in df.columns:
        df["date"] = pd.to_datetime(df["date"], unit="ms", errors="ignore")
    return df


def _synthetic_status(days: int) -> pd.DataFrame:
    rng = np.random.default_rng(7)
    end = pd.Timestamp.today().normalize()
    dates = pd.date_range(end - pd.Timedelta(days=days - 1), end, freq="D")
    rows = []
    # Reflect the real-world Red Sea disruption: Bab/Suez running below baseline.
    stress = {"BAB_EL_MANDEB": 0.45, "SUEZ": 0.55, "HORMUZ": 0.95,
              "MALACCA": 1.02, "PANAMA": 0.8, "GOOD_HOPE": 1.6}
    for cp, meta in CHOKEPOINTS.items():
        baseline = 40 + 30 * abs(hash(cp) % 5) / 5
        for d in dates:
            factor = stress.get(cp, 1.0) + rng.normal(0, 0.03)
            calls = max(0, baseline * factor)
            rows.append({"chokepoint": cp, "name": meta["name"], "date": d,
                         "transit_calls": round(calls, 1),
                         "baseline": round(baseline, 1),
                         "vs_baseline_pct": round((factor - 1) * 100, 1),
                         "status": _status(factor)})
    return pd.DataFrame(rows)


def _status(factor: float) -> str:
    if factor < 0.6:
        return "DISRUPTED"
    if factor < 0.85:
        return "STRAINED"
    return "NORMAL"
