"""Geopolitical event connector (GDELT-style typed shocks).

Pulls recent maritime/geopolitical news from the free GDELT DOC 2.0 API and
classifies each item into a *typed shock* the scenario engine understands
(chokepoint_closure, conflict, strike, sanctions, weather_extreme), tagged with
the chokepoint it affects and an estimated severity. Offline, it returns a
realistic synthetic feed (incl. a live-style Red Sea / Hormuz item) so the
terminal and scenario engine always have something to show.

Source: https://www.gdeltproject.org/  (DOC 2.0 API, no key required)
"""

from __future__ import annotations

from typing import List

import pandas as pd

from src.ingestion.connectors.base import cached_json
from src.utils.logging_utils import get_logger

log = get_logger(__name__)

GDELT_DOC = "https://api.gdeltproject.org/api/v2/doc/doc"

# keyword -> (shock_type, chokepoint)
_RULES = [
    (["strait of hormuz", "hormuz"], "chokepoint_closure", "HORMUZ"),
    (["red sea", "bab-el-mandeb", "houthi"], "chokepoint_closure", "BAB_EL_MANDEB"),
    (["suez canal", "suez"], "chokepoint_closure", "SUEZ"),
    (["strait of malacca", "malacca"], "chokepoint_closure", "MALACCA"),
    (["panama canal", "panama drought"], "chokepoint_closure", "PANAMA"),
    (["port strike", "dock workers", "labour strike", "labor strike"], "strike", None),
    (["sanction", "embargo", "tariff"], "sanctions", None),
    (["missile", "attack", "war", "conflict", "naval"], "conflict", None),
    (["cyclone", "typhoon", "hurricane", "storm surge"], "weather_extreme", None),
]


def fetch_events(max_records: int = 40) -> pd.DataFrame:
    query = ('("strait of hormuz" OR "red sea" OR "suez canal" OR "malacca" '
             'OR "panama canal" OR "port strike" OR "shipping disruption") '
             'sourcelang:eng')
    data = cached_json(GDELT_DOC, key="gdelt_maritime", ttl=3 * 3600,
                       params={"query": query, "mode": "artlist",
                               "maxrecords": max_records, "format": "json",
                               "timespan": "14d", "sort": "datedesc"})
    from src.utils import provenance
    arts = (data or {}).get("articles")
    if arts:
        rows = []
        for a in arts:
            title = a.get("title", "")
            stype, cp = _classify(title)
            if stype is None:
                continue
            rows.append({
                "date": pd.to_datetime(a.get("seendate"), errors="coerce"),
                "title": title, "url": a.get("url", ""),
                "source": a.get("domain", ""),
                "shock_type": stype, "chokepoint": cp,
                "severity": _severity(title, stype)})
        if rows:
            provenance.record("Geopolitical events (GDELT)", provenance.LIVE,
                              f"{len(rows)} classified maritime items from the DOC 2.0 API",
                              provider="GDELT DOC 2.0", rows=len(rows))
            return pd.DataFrame(rows)
        log.info("GDELT returned no classifiable items; using synthetic feed.")
    provenance.record("Geopolitical events (GDELT)", provenance.SYNTHETIC,
                      "GDELT unreachable", provider="GDELT DOC 2.0", fallback="synthetic feed")
    return _synthetic_events()


def _classify(text: str):
    t = (text or "").lower()
    for kws, stype, cp in _RULES:
        if any(k in t for k in kws):
            return stype, cp
    return None, None


def _severity(text: str, stype: str) -> float:
    t = (text or "").lower()
    sev = {"chokepoint_closure": 0.7, "conflict": 0.6, "sanctions": 0.5,
           "strike": 0.5, "weather_extreme": 0.5}.get(stype, 0.4)
    for w, bump in [("clos", 0.2), ("block", 0.2), ("halt", 0.2),
                    ("attack", 0.15), ("escalat", 0.15), ("shut", 0.2)]:
        if w in t:
            sev = min(1.0, sev + bump)
    return round(sev, 2)


def _synthetic_events() -> pd.DataFrame:
    today = pd.Timestamp.today().normalize()
    data = [
        (0, "Red Sea attacks force carriers to divert around Cape of Good Hope",
         "chokepoint_closure", "BAB_EL_MANDEB", 0.85, "reuters.com"),
        (1, "Tensions in Strait of Hormuz raise tanker insurance premiums",
         "conflict", "HORMUZ", 0.7, "bloomberg.com"),
        (3, "Panama Canal maintains draft restrictions amid low water levels",
         "chokepoint_closure", "PANAMA", 0.5, "splash247.com"),
        (5, "Suez Canal transit volumes remain below pre-crisis baseline",
         "chokepoint_closure", "SUEZ", 0.55, "lloydslist.com"),
        (7, "Container spot freight rates climb on extended diversions",
         "sanctions", None, 0.4, "freightwaves.com"),
    ]
    rows = [{"date": today - pd.Timedelta(days=d), "title": t, "shock_type": st,
             "chokepoint": cp, "severity": sev, "source": src, "url": ""}
            for d, t, st, cp, sev, src in data]
    return pd.DataFrame(rows)
