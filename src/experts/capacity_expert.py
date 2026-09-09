"""Capacity-pressure expert for berth and yard stress.

This separates *what vessels are doing* from *how close the terminal is to a
capacity squeeze*. It combines utilization, queue pressure, turnaround stress,
queue acceleration and throughput degradation into a leakage-safe 0..1 signal.
"""

from __future__ import annotations

import pandas as pd

from src.utils.config import DATE, PORT_ID
from src.utils.logging_utils import get_logger

log = get_logger(__name__)


def _to_unit_interval(series: pd.Series, neutral: float = 0.5) -> pd.Series:
    x = pd.to_numeric(series, errors="coerce")
    if x.dropna().empty:
        return pd.Series(neutral, index=series.index, dtype=float)
    if x.quantile(0.95) > 1.5:
        x = x / 100.0
    return x.clip(0, 1).fillna(neutral)


def run(
    observed: pd.DataFrame,
    port_ops: pd.DataFrame | None = None,
) -> pd.DataFrame:
    if observed is None or observed.empty:
        return pd.DataFrame(
            columns=[PORT_ID, DATE, "capacity_pressure", "queue_momentum",
                     "throughput_stress", "capacity_confidence"]
        )

    obs_cols = [PORT_ID, DATE] + [
        c for c in ("utilization", "throughput", "congestion_index")
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
        queue = _to_unit_interval(
            g["queue_proxy"] if "queue_proxy" in g else pd.Series(0.0, index=g.index),
            neutral=0.0,
        )
        turnaround = _to_unit_interval(
            g["turnaround_proxy"] if "turnaround_proxy" in g else pd.Series(0.0, index=g.index),
            neutral=0.0,
        )

        if "utilization" in g.columns:
            utilization = _to_unit_interval(g["utilization"])
        elif "congestion_index" in g.columns:
            utilization = (
                pd.to_numeric(g["congestion_index"], errors="coerce") / 100.0
            ).clip(0, 1).fillna(0.5)
        else:
            utilization = pd.Series(0.5, index=g.index)

        queue_baseline = queue.shift(1).rolling(14, min_periods=3).mean()
        queue_momentum = (
            0.5 + (queue - queue_baseline.fillna(queue)) / 0.6
        ).clip(0, 1)

        if "throughput" in g.columns:
            throughput = pd.to_numeric(g["throughput"], errors="coerce")
            prior = throughput.shift(1).rolling(14, min_periods=5).median()
            throughput_stress = (
                (prior - throughput) / prior.abs().clip(lower=1e-6)
            ).clip(lower=0, upper=1).fillna(0.0)
        else:
            throughput_stress = pd.Series(0.0, index=g.index)

        pressure = (
            0.40 * utilization
            + 0.27 * queue
            + 0.18 * turnaround
            + 0.10 * queue_momentum
            + 0.05 * throughput_stress
        ).clip(0, 1)

        present = pd.DataFrame(
            {"util": utilization.notna(), "queue": queue.notna(), "turn": turnaround.notna()}
        ).mean(axis=1)
        ais_conf = (
            pd.to_numeric(g["ais_confidence"], errors="coerce").fillna(0.5)
            if "ais_confidence" in g.columns
            else pd.Series(0.5, index=g.index)
        )
        confidence = (0.55 * present + 0.45 * ais_conf).clip(0, 1)

        g["capacity_pressure"] = pressure.round(4)
        g["queue_momentum"] = queue_momentum.round(4)
        g["throughput_stress"] = throughput_stress.round(4)
        g["capacity_confidence"] = confidence.round(3)
        parts.append(g)

    out = pd.concat(parts, ignore_index=True)
    log.info("Capacity expert produced %d rows across %d ports.", len(out), out[PORT_ID].nunique())
    return out[[PORT_ID, DATE, "capacity_pressure", "queue_momentum",
                "throughput_stress", "capacity_confidence"]]
