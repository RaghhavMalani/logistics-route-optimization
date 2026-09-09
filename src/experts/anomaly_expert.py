"""Leakage-safe anomaly and drift expert for port operations.

The expert asks a simple question for every port-day: *is today's operating
signal unusual relative to what was knowable before today?* It uses robust
rolling median/MAD baselines, shifted by one day, so current and future values
never leak into the reference distribution.

Outputs are bounded 0..1 risk features consumed by the HSMM and TFT.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from src.utils.config import DATE, PORT_ID
from src.utils.logging_utils import get_logger

log = get_logger(__name__)

_WINDOW = 28
_MIN_HISTORY = 7
_SIGNAL_MAP = {
    "congestion_index": "congestion_anomaly",
    "delay_hours": "delay_anomaly",
    "throughput": "throughput_anomaly",
    "queue_proxy": "queue_anomaly",
    "turnaround_proxy": "turnaround_anomaly",
}


def _robust_surprise(series: pd.Series) -> tuple[pd.Series, pd.Series]:
    """Return (surprise, history confidence), using observations before t only."""
    x = pd.to_numeric(series, errors="coerce")
    past = x.shift(1)
    median = past.rolling(_WINDOW, min_periods=_MIN_HISTORY).median()
    mad = past.rolling(_WINDOW, min_periods=_MIN_HISTORY).apply(
        lambda a: float(np.median(np.abs(a - np.median(a)))), raw=True
    )
    robust_z = (x - median).abs() / (1.4826 * mad.replace(0, np.nan))
    fallback_scale = (median.abs() * 0.05).clip(lower=1e-3)
    robust_z = robust_z.fillna((x - median).abs() / fallback_scale)
    surprise = (robust_z / 6.0).clip(0, 1).fillna(0.0)
    history = (
        past.notna().rolling(_WINDOW, min_periods=1).sum() / float(_MIN_HISTORY)
    ).clip(0, 1)
    return surprise, history


def run(
    observed: pd.DataFrame,
    port_ops: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """Build per-port anomaly features from observed and port-operations data."""
    if observed is None or observed.empty:
        return pd.DataFrame(columns=[PORT_ID, DATE, "anomaly_score", "anomaly_confidence"])

    obs_cols = [PORT_ID, DATE] + [
        c for c in ("congestion_index", "delay_hours", "throughput")
        if c in observed.columns
    ]
    frame = observed[obs_cols].copy()
    frame[DATE] = pd.to_datetime(frame[DATE], errors="coerce")

    if port_ops is not None and not port_ops.empty:
        ops_cols = [PORT_ID, DATE] + [
            c for c in ("queue_proxy", "turnaround_proxy", "ais_confidence")
            if c in port_ops.columns
        ]
        ops = port_ops[ops_cols].copy()
        ops[DATE] = pd.to_datetime(ops[DATE], errors="coerce")
        frame = frame.merge(
            ops.drop_duplicates([PORT_ID, DATE]), on=[PORT_ID, DATE], how="left"
        )

    parts = []
    for _, group in frame.sort_values([PORT_ID, DATE]).groupby(PORT_ID, sort=False):
        g = group.copy()
        history_terms = []
        score_cols = []
        for source, target in _SIGNAL_MAP.items():
            if source not in g.columns:
                continue
            score, history = _robust_surprise(g[source])
            g[target] = score.round(4)
            history_terms.append(history)
            score_cols.append(target)

        if score_cols:
            mx = g[score_cols].max(axis=1)
            avg = g[score_cols].mean(axis=1)
            g["anomaly_score"] = (0.65 * mx + 0.35 * avg).clip(0, 1).round(4)
            history_conf = pd.concat(history_terms, axis=1).mean(axis=1)
        else:
            g["anomaly_score"] = 0.0
            history_conf = pd.Series(0.0, index=g.index)

        source_conf = (
            pd.to_numeric(g["ais_confidence"], errors="coerce")
            if "ais_confidence" in g.columns
            else pd.Series(1.0, index=g.index)
        )
        g["anomaly_confidence"] = (
            history_conf * source_conf.fillna(0.5)
        ).clip(0, 1).round(3)
        parts.append(g)

    out = pd.concat(parts, ignore_index=True)
    keep = [PORT_ID, DATE] + [
        c for c in _SIGNAL_MAP.values() if c in out.columns
    ] + ["anomaly_score", "anomaly_confidence"]
    log.info("Anomaly expert produced %d rows across %d ports.", len(out), out[PORT_ID].nunique())
    return out[keep]
