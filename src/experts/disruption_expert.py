"""Disruption Propagation Expert.

Global chokepoint stress does not stay global -- it lands on specific Indian
ports through specific sea lanes. This expert closes that loop:

    chokepoint daily transits (IMF PortWatch)
        -> disruption index vs the chokepoint's own backward baseline
        -> lane exposure weight per port
        -> per-port disruption pressure, with a transit lag

The baseline is an expanding mean shifted by one day, so a given day's index
never uses that day's own value or anything later. The lane lag reflects that a
Hormuz or Suez disruption reaches an Indian berth days later, not instantly.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from src.ingestion.connectors.portwatch import CHOKEPOINTS, port_exposure
from src.utils.config import DATA_DIR, DATE, PORT_ID
from src.utils.logging_utils import get_logger

log = get_logger(__name__)

CHOKEPOINT_HISTORY = DATA_DIR / "portwatch" / "chokepoints.csv"

#: Approximate steaming lag, in days, from each chokepoint to an Indian port.
LANE_LAG_DAYS = {
    "HORMUZ": 3,
    "BAB_EL_MANDEB": 7,
    "SUEZ": 9,
    "MALACCA": 5,
    "PANAMA": 21,
    "GOOD_HOPE": 16,
}

_BASELINE_MIN_DAYS = 21
_SMOOTH_DAYS = 7

_OUT_COLS = [PORT_ID, DATE, "disruption_exposure", "disruption_pressure",
             "disruption_lead_chokepoint", "disruption_confidence"]


def _match_chokepoint(name: str) -> str | None:
    key = (name or "").lower()
    for cid, meta in CHOKEPOINTS.items():
        label = meta["name"].lower()
        head = label.split()[0]
        if head and head in key:
            return cid
    for cid, token in (("HORMUZ", "hormuz"), ("BAB_EL_MANDEB", "bab"),
                       ("SUEZ", "suez"), ("MALACCA", "malacca"),
                       ("PANAMA", "panama"), ("GOOD_HOPE", "good hope")):
        if token in key:
            return cid
    return None


def chokepoint_disruption(history: pd.DataFrame | None = None) -> pd.DataFrame:
    """Daily 0..1 disruption index per chokepoint, leakage-safe.

    1.0 means transits have collapsed relative to the chokepoint's own history;
    0.0 means transits are at or above baseline.
    """
    if history is None:
        if not CHOKEPOINT_HISTORY.exists():
            return pd.DataFrame(columns=["chokepoint", DATE, "disruption_index"])
        history = pd.read_csv(CHOKEPOINT_HISTORY)

    if history.empty or "portname" not in history.columns:
        return pd.DataFrame(columns=["chokepoint", DATE, "disruption_index"])

    frame = history.copy()
    frame[DATE] = pd.to_datetime(frame["date"], errors="coerce")
    frame["n_total"] = pd.to_numeric(frame["n_total"], errors="coerce")
    frame["chokepoint"] = frame["portname"].map(_match_chokepoint)
    frame = frame.dropna(subset=[DATE, "n_total", "chokepoint"])
    if frame.empty:
        return pd.DataFrame(columns=["chokepoint", DATE, "disruption_index"])

    parts = []
    for cid, group in frame.sort_values(DATE).groupby("chokepoint", sort=False):
        g = group.drop_duplicates(subset=[DATE]).sort_values(DATE).copy()
        smoothed = g["n_total"].rolling(_SMOOTH_DAYS, min_periods=1).mean()
        baseline = smoothed.expanding(min_periods=_BASELINE_MIN_DAYS).mean().shift(1)
        ratio = (smoothed / baseline).replace([np.inf, -np.inf], np.nan)
        # A 30% shortfall against baseline reads as full disruption.
        g["disruption_index"] = ((1.0 - ratio) / 0.30).clip(0, 1).fillna(0.0)
        g["has_baseline"] = baseline.notna().astype(float)
        parts.append(g[["chokepoint", DATE, "disruption_index", "has_baseline"]])

    out = pd.concat(parts, ignore_index=True)
    log.info("Chokepoint disruption index: %d rows across %d chokepoints.",
             len(out), out["chokepoint"].nunique())
    return out


def run(grid: pd.DataFrame,
        history: pd.DataFrame | None = None) -> pd.DataFrame:
    """Per (port_id, date) disruption exposure and pressure.

    ``grid`` supplies the port/date skeleton (normally the observed frame).
    """
    if grid is None or grid.empty:
        return pd.DataFrame(columns=_OUT_COLS)

    skeleton = grid[[PORT_ID, DATE]].drop_duplicates().copy()
    skeleton[DATE] = pd.to_datetime(skeleton[DATE], errors="coerce")

    disruption = chokepoint_disruption(history)
    if disruption.empty:
        skeleton["disruption_exposure"] = 0.0
        skeleton["disruption_pressure"] = 0.0
        skeleton["disruption_lead_chokepoint"] = "none"
        skeleton["disruption_confidence"] = 0.0
        return skeleton[_OUT_COLS]

    # Lag each chokepoint's index so it lands on the day it reaches the coast.
    lagged = []
    for cid, group in disruption.groupby("chokepoint", sort=False):
        g = group.sort_values(DATE).copy()
        g[DATE] = g[DATE] + pd.to_timedelta(LANE_LAG_DAYS.get(cid, 7), unit="D")
        lagged.append(g)
    lagged_frame = pd.concat(lagged, ignore_index=True)

    wide = lagged_frame.pivot_table(index=DATE, columns="chokepoint",
                                    values="disruption_index", aggfunc="max")
    coverage = lagged_frame.pivot_table(index=DATE, columns="chokepoint",
                                        values="has_baseline", aggfunc="max")
    # Carry the last known chokepoint reading forward over its transit window.
    wide = wide.sort_index().ffill(limit=14)
    coverage = coverage.sort_index().ffill(limit=14)

    rows = []
    for port_id, group in skeleton.groupby(PORT_ID, sort=False):
        exposure = port_exposure(str(port_id))
        weights = {cid: float(w) for cid, w in exposure.items() if cid in wide.columns}
        total_weight = sum(weights.values()) or 1.0

        aligned = wide.reindex(pd.DatetimeIndex(group[DATE].sort_values())).ffill()
        cover = coverage.reindex(aligned.index).ffill()

        pressure = np.zeros(len(aligned))
        for cid, weight in weights.items():
            pressure = pressure + weight * aligned[cid].fillna(0.0).to_numpy()
        pressure = pressure / total_weight

        if weights:
            weighted = aligned[list(weights)].mul(pd.Series(weights)).fillna(0.0)
            lead = weighted.idxmax(axis=1).where(weighted.max(axis=1) > 0, "none")
        else:
            lead = pd.Series("none", index=aligned.index)
        confidence = (cover[list(weights)].fillna(0.0).mean(axis=1)
                      if weights else pd.Series(0.0, index=aligned.index))

        rows.append(pd.DataFrame({
            PORT_ID: port_id,
            DATE: aligned.index,
            "disruption_exposure": round(sum(weights.values()) / max(len(weights), 1), 4),
            "disruption_pressure": np.round(np.clip(pressure, 0, 1), 4),
            "disruption_lead_chokepoint": lead.fillna("none").astype(str).to_numpy(),
            "disruption_confidence": np.round(confidence.to_numpy(), 3),
        }))

    out = pd.concat(rows, ignore_index=True)
    log.info("Disruption expert produced %d rows across %d ports (mean pressure %.3f).",
             len(out), out[PORT_ID].nunique(), float(out["disruption_pressure"].mean()))
    return out[_OUT_COLS]
