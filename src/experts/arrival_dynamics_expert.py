"""Arrival Dynamics Expert.

Congestion is usually visible in *how* vessels arrive before it is visible in
how long they wait. This expert reads the arrival stream and separates three
distinct failure modes that a single "queue" number hides:

    arrival_acceleration  arrivals rising faster than the port's own trend
    arrival_clustering    the same weekly volume compressed into fewer days
    anchorage_buildup     vessels accumulating outside the berth line
    berth_pressure        the composite: demand for berths vs the port's own
                          demonstrated handling rate

Every statistic compares today against a backward window that ends yesterday, so
nothing here can see the future.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from src.utils.config import DATE, PORT_ID
from src.utils.logging_utils import get_logger

log = get_logger(__name__)

_TREND_WINDOW = 21
_SHORT_WINDOW = 3
_MIN_HISTORY = 7

_OUT_COLS = [PORT_ID, DATE, "arrival_acceleration", "arrival_clustering",
             "anchorage_buildup", "berth_pressure", "arrival_confidence"]


def _safe_ratio(numerator: pd.Series, denominator: pd.Series) -> pd.Series:
    ratio = numerator / denominator.replace(0, np.nan)
    return ratio.replace([np.inf, -np.inf], np.nan)


def run(observed: pd.DataFrame,
        port_ops: pd.DataFrame | None = None) -> pd.DataFrame:
    """Build arrival-dynamics features from the AIS-derived activity stream."""
    if observed is None or observed.empty:
        return pd.DataFrame(columns=_OUT_COLS)

    frame = observed[[PORT_ID, DATE]].copy()
    frame[DATE] = pd.to_datetime(frame[DATE], errors="coerce")

    if port_ops is not None and not port_ops.empty:
        ops_cols = [PORT_ID, DATE] + [
            c for c in ("arrival_count", "anchorage_count", "vessel_density",
                        "queue_proxy", "ais_confidence")
            if c in port_ops.columns
        ]
        ops = port_ops[ops_cols].copy()
        ops[DATE] = pd.to_datetime(ops[DATE], errors="coerce")
        frame = frame.merge(ops.drop_duplicates([PORT_ID, DATE]),
                            on=[PORT_ID, DATE], how="left")

    if "arrival_count" not in frame.columns:
        # Without an arrival stream there is nothing honest to report.
        frame["arrival_acceleration"] = 0.5
        frame["arrival_clustering"] = 0.0
        frame["anchorage_buildup"] = 0.0
        frame["berth_pressure"] = 0.0
        frame["arrival_confidence"] = 0.0
        return frame[_OUT_COLS]

    parts = []
    for _, group in frame.sort_values([PORT_ID, DATE]).groupby(PORT_ID, sort=False):
        g = group.copy()
        arrivals = pd.to_numeric(g["arrival_count"], errors="coerce").fillna(0.0)

        past = arrivals.shift(1)
        trend = past.rolling(_TREND_WINDOW, min_periods=_MIN_HISTORY).mean()
        recent = arrivals.rolling(_SHORT_WINDOW, min_periods=1).mean()

        # Acceleration: recent arrival rate against the port's own trend,
        # centred at 0.5 so "no change" is neutral rather than alarming.
        acceleration = (0.5 + 0.5 * (_safe_ratio(recent, trend) - 1.0)).clip(0, 1)

        # Clustering: within the trailing week, how much of the volume lands on
        # the busiest days. A flat week scores ~0, a single-day burst scores ~1.
        weekly_sum = arrivals.rolling(7, min_periods=3).sum()
        weekly_max = arrivals.rolling(7, min_periods=3).max()
        clustering = ((_safe_ratio(weekly_max * 7.0, weekly_sum) - 1.0) / 4.0).clip(0, 1)

        if "anchorage_count" in g.columns:
            anchorage = pd.to_numeric(g["anchorage_count"], errors="coerce").fillna(0.0)
            anchorage_base = anchorage.shift(1).rolling(
                _TREND_WINDOW, min_periods=_MIN_HISTORY).mean()
            buildup = ((anchorage - anchorage_base)
                       / anchorage_base.clip(lower=0.5)).clip(0, 2) / 2.0
            buildup = buildup.fillna(0.0)
        else:
            anchorage = pd.Series(0.0, index=g.index)
            buildup = pd.Series(0.0, index=g.index)

        queue = (pd.to_numeric(g["queue_proxy"], errors="coerce").fillna(0.0)
                 if "queue_proxy" in g.columns else pd.Series(0.0, index=g.index))

        berth_pressure = (0.38 * acceleration.fillna(0.5)
                          + 0.24 * clustering.fillna(0.0)
                          + 0.23 * buildup
                          + 0.15 * queue).clip(0, 1)

        history = past.notna().rolling(
            _TREND_WINDOW, min_periods=1).sum() / float(_MIN_HISTORY)
        ais_conf = (pd.to_numeric(g["ais_confidence"], errors="coerce").fillna(0.5)
                    if "ais_confidence" in g.columns
                    else pd.Series(0.5, index=g.index))
        confidence = (history.clip(0, 1) * ais_conf).clip(0, 1)

        g["arrival_acceleration"] = acceleration.fillna(0.5).round(4)
        g["arrival_clustering"] = clustering.fillna(0.0).round(4)
        g["anchorage_buildup"] = buildup.round(4)
        g["berth_pressure"] = berth_pressure.round(4)
        g["arrival_confidence"] = confidence.round(3)
        parts.append(g)

    out = pd.concat(parts, ignore_index=True)
    log.info("Arrival dynamics expert produced %d rows across %d ports.",
             len(out), out[PORT_ID].nunique())
    return out[_OUT_COLS]
