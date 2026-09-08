"""Port-level event stream: global headlines and disasters mapped onto berths.

The news expert used to receive an empty frame on the PortWatch path, so the
"News / Geopolitical" node in the pipeline was decorative. This module gives it
a real, port-attributed input by fusing two sources that are already ingested:

    GDELT DOC 2.0    typed maritime shocks (chokepoint closure, conflict,
                     strike, sanctions, extreme weather) with a severity
    GDACS via IMF    disaster alerts already intersected with specific ports

Attribution is explicit, not vibes-based. A chokepoint event reaches a port in
proportion to that port's lane exposure; a GDACS alert reaches exactly the ports
the alert names. Severity decays with recency inside the news expert, so a
two-week-old headline no longer drives today's forecast.

The output has two products: ``build_news_raw`` for the modelling pipeline and
``build_event_catalogue`` for the terminal, which carries the headline, source
domain and URL so every alert on screen is traceable to a document.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from src.ingestion.connectors.portwatch import CHOKEPOINTS, port_exposure
from src.utils import provenance
from src.utils.config import DATA_DIR, DATE, PORT_ID
from src.utils.logging_utils import get_logger

log = get_logger(__name__)

DISRUPTIONS_PATH = DATA_DIR / "portwatch" / "disruptions.csv"

#: Shock types mapped onto the risk channels the news expert understands.
SHOCK_TO_CHANNEL = {
    "chokepoint_closure": "conflict",
    "conflict": "conflict",
    "sanctions": "policy",
    "strike": "strike",
    "weather_extreme": "weather",
}

#: A chokepoint event only counts for ports with at least this lane exposure.
MIN_EXPOSURE = 0.15

#: Weight for an event with no chokepoint attribution. A national headline is
#: real evidence, but it is not the same as a lane a port demonstrably depends
#: on, so it enters at a fraction of a lane-attributed event's weight.
NATIONAL_WEIGHT = 0.35

_GDACS_SEVERITY = {"RED": 1.0, "ORANGE": 0.6, "GREEN": 0.3}


def _portwatch_id_map() -> dict[str, str]:
    from src.ingestion.portwatch_source import PORTID_TO_CANON
    return PORTID_TO_CANON


def _gdacs_events(path: Path | None = None) -> pd.DataFrame:
    """Disaster alerts with the ports each one actually names."""
    path = path or DISRUPTIONS_PATH
    if not path.exists():
        return pd.DataFrame()
    try:
        events = pd.read_csv(path)
    except (OSError, pd.errors.EmptyDataError):
        return pd.DataFrame()
    if not {"fromdate", "affectedports"} <= set(events.columns):
        return pd.DataFrame()

    id_map = _portwatch_id_map()
    events["from"] = pd.to_datetime(events["fromdate"], unit="ms", errors="coerce")
    events["to"] = pd.to_datetime(events.get("todate"), unit="ms", errors="coerce")
    events["to"] = events["to"].fillna(events["from"] + pd.Timedelta(days=3))
    events["severity"] = (events.get("alertlevel", pd.Series(dtype=str))
                          .astype(str).str.upper().map(_GDACS_SEVERITY).fillna(0.3))

    rows = []
    for _, event in events.dropna(subset=["from"]).iterrows():
        raw_ports = {p.strip() for p in str(event.get("affectedports", "")).split(";")}
        canon = sorted({id_map[p] for p in raw_ports if p in id_map})
        if not canon:
            continue
        rows.append({
            "event_id": str(event.get("eventid", "")),
            "date": event["from"],
            "end_date": event["to"],
            "title": str(event.get("eventname", "Disaster alert")),
            "shock_type": "weather_extreme",
            "chokepoint": None,
            "severity": float(event["severity"]),
            "source": "GDACS via IMF PortWatch",
            "url": "",
            "ports": canon,
        })
    return pd.DataFrame(rows)


def _gdelt_events(max_records: int = 60) -> pd.DataFrame:
    """Typed maritime shocks from GDELT, attributed via lane exposure."""
    from src.ingestion.connectors.events import fetch_events

    try:
        events = fetch_events(max_records=max_records)
    except Exception as exc:  # pragma: no cover - connector already degrades
        log.warning("GDELT event fetch failed: %s", exc)
        return pd.DataFrame()
    if events is None or events.empty:
        return pd.DataFrame()

    rows = []
    for index, event in events.iterrows():
        chokepoint = event.get("chokepoint")
        if chokepoint:
            ports = [pid for pid in _all_model_ids()
                     if port_exposure(pid).get(chokepoint, 0.0) >= MIN_EXPOSURE]
        else:
            ports = _all_model_ids()
        if not ports:
            continue
        date = pd.to_datetime(event.get("date"), errors="coerce")
        if pd.isna(date):
            continue
        rows.append({
            "event_id": f"GDELT-{index}",
            "date": date.tz_localize(None) if date.tzinfo else date,
            "end_date": (date.tz_localize(None) if date.tzinfo else date)
            + pd.Timedelta(days=2),
            "title": str(event.get("title", "")),
            "shock_type": str(event.get("shock_type", "conflict")),
            "chokepoint": chokepoint,
            "severity": float(event.get("severity", 0.5)),
            "source": str(event.get("source", "gdelt")),
            "url": str(event.get("url", "")),
            "ports": ports,
        })
    return pd.DataFrame(rows)


def _all_model_ids() -> list[str]:
    from src.utils import port_registry
    return port_registry.model_ids()


def collect_events(max_records: int = 60) -> pd.DataFrame:
    """All attributable events from every wired source, newest first."""
    frames = [f for f in (_gdelt_events(max_records), _gdacs_events()) if not f.empty]
    if not frames:
        provenance.record(
            "Maritime events (GDELT + GDACS)", provenance.UNAVAILABLE,
            "No event source returned usable records; port-level news features "
            "are not produced and the news node reports as unavailable.",
            provider="GDELT DOC 2.0 / GDACS")
        return pd.DataFrame()

    events = pd.concat(frames, ignore_index=True).sort_values("date", ascending=False)
    newest = events["date"].max()
    provenance.record(
        "Maritime events (GDELT + GDACS)", provenance.CACHED_LIVE,
        f"{len(events)} attributable maritime events mapped onto "
        f"{len({p for ports in events['ports'] for p in ports})} ports.",
        provider="GDELT DOC 2.0 + GDACS (via IMF PortWatch)",
        observed_at=newest, rows=len(events), freshness_hours=72.0)
    return events.reset_index(drop=True)


def build_news_raw(grid: pd.DataFrame,
                   events: pd.DataFrame | None = None) -> pd.DataFrame:
    """Port/day event frame in the shape the news expert consumes.

    Columns: ``port_id, date, sentiment, event_type, event_severity``. Sentiment
    is derived from the day's attributed event severity (more severe -> more
    negative tone), which the news expert then converts into a 0..1 risk score.
    """
    if grid is None or grid.empty:
        return pd.DataFrame(columns=[PORT_ID, DATE])

    skeleton = grid[[PORT_ID, DATE]].drop_duplicates().copy()
    skeleton[DATE] = pd.to_datetime(skeleton[DATE], errors="coerce")
    skeleton = skeleton.dropna(subset=[DATE])

    events = collect_events() if events is None else events
    if events is None or events.empty:
        return pd.DataFrame(columns=[PORT_ID, DATE])

    # Expand each event across the ports it touches and the days it spans.
    expanded = []
    for _, event in events.iterrows():
        chokepoint = event.get("chokepoint")
        span = pd.date_range(pd.Timestamp(event["date"]).normalize(),
                             pd.Timestamp(event["end_date"]).normalize(), freq="D")
        for port_id in event["ports"]:
            weight = (port_exposure(port_id).get(chokepoint, MIN_EXPOSURE)
                      if chokepoint else NATIONAL_WEIGHT)
            severity = float(event["severity"]) * float(weight)
            channel = SHOCK_TO_CHANNEL.get(str(event["shock_type"]), "conflict")
            for day in span:
                expanded.append({PORT_ID: port_id, DATE: day,
                                 "event_type": channel,
                                 "event_severity": severity})
    if not expanded:
        return pd.DataFrame(columns=[PORT_ID, DATE])

    daily = pd.DataFrame(expanded)
    # One row per port-day: keep the dominant channel and the peak severity.
    dominant = (daily.sort_values("event_severity", ascending=False)
                .drop_duplicates([PORT_ID, DATE])[[PORT_ID, DATE, "event_type"]])
    peak = (daily.groupby([PORT_ID, DATE], as_index=False)["event_severity"].max())
    merged = peak.merge(dominant, on=[PORT_ID, DATE], how="left")

    out = skeleton.merge(merged, on=[PORT_ID, DATE], how="left")
    out["event_severity"] = out["event_severity"].fillna(0.0)
    out["event_type"] = out["event_type"].fillna("none")
    # Tone derived from attributed severity: 0 severity -> neutral, 1 -> -1.
    out["sentiment"] = (-2.0 * out["event_severity"]).clip(-1.0, 1.0).round(4)

    log.info("Port event stream: %d port-days, %d with an attributed event.",
             len(out), int((out["event_severity"] > 0).sum()))
    return out


def build_event_catalogue(events: pd.DataFrame | None = None,
                          limit: int = 40) -> list[dict]:
    """Traceable events for the terminal: headline, source, URL, ports hit."""
    from src.utils import port_registry

    events = collect_events() if events is None else events
    if events is None or events.empty:
        return []

    catalogue = []
    for _, event in events.head(limit).iterrows():
        chokepoint = event.get("chokepoint")
        affected = []
        for port_id in event["ports"]:
            port = port_registry.resolve(port_id)
            if port is None:
                continue
            weight = (port_exposure(port_id).get(chokepoint, MIN_EXPOSURE)
                      if chokepoint else NATIONAL_WEIGHT)
            affected.append({"portCode": port.locode, "name": port.short,
                             "exposure": round(float(weight), 3)})
        affected.sort(key=lambda row: row["exposure"], reverse=True)
        severity = float(event["severity"])
        catalogue.append({
            "id": str(event["event_id"]),
            "title": str(event["title"]),
            "timestamp": pd.Timestamp(event["date"]).isoformat(),
            "shockType": str(event["shock_type"]),
            "chokepoint": chokepoint,
            "chokepointName": (CHOKEPOINTS.get(chokepoint, {}).get("name")
                               if chokepoint else None),
            "severity": round(severity, 3),
            "severityLabel": _severity_label(severity),
            "source": str(event["source"]),
            "url": str(event.get("url", "")),
            "affectedPorts": affected[:6],
        })
    return catalogue


def _severity_label(severity: float) -> str:
    if severity >= 0.75:
        return "severe"
    if severity >= 0.55:
        return "high"
    if severity >= 0.35:
        return "watch"
    return "normal"


def national_event_pressure(news_raw: pd.DataFrame) -> float:
    """Mean attributed event severity on the most recent day, 0..1."""
    if news_raw is None or news_raw.empty or "event_severity" not in news_raw:
        return 0.0
    latest = news_raw[news_raw[DATE] == news_raw[DATE].max()]
    return float(np.clip(latest["event_severity"].mean(), 0, 1))
