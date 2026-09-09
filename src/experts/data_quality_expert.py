"""Data Quality / Provenance Expert.

Every other expert answers "what is happening at the port?". This one answers
"how much should you trust the answer?" -- and it does so per port and per day,
not as a single global banner.

It measures four things that actually degrade a forecast:

    completeness   share of the model's input columns present on the day
    freshness      how far the row sits behind the newest data for that port
    continuity     whether the port's recent history has gaps
    source_trust   the confidence the upstream feeds themselves declared,
                   combined with the global provenance registry

The composite ``data_quality_score`` (1.0 = pristine) is consumed by the
forecast confidence discount, so degraded inputs visibly widen uncertainty
instead of silently producing a confident wrong answer.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from src.utils import provenance
from src.utils.config import DATE, PORT_ID
from src.utils.logging_utils import get_logger

log = get_logger(__name__)

#: Columns whose presence materially changes forecast quality.
_CRITICAL_COLUMNS = [
    "congestion_index", "delay_hours", "throughput", "utilization",
    "queue_proxy", "turnaround_proxy", "arrival_count", "WxImpactIndex",
    "demand_pressure", "capacity_pressure", "anomaly_score",
]

#: Confidence columns the upstream experts publish.
_CONFIDENCE_COLUMNS = [
    "ais_confidence", "weather_confidence", "demand_confidence",
    "capacity_confidence", "anomaly_confidence", "news_confidence",
    "arrival_confidence", "disruption_confidence",
]

_STALE_AFTER_DAYS = 3.0
_CONTINUITY_WINDOW = 14

_OUT_COLS = [PORT_ID, DATE, "data_completeness", "data_freshness",
             "data_continuity", "source_trust", "data_quality_score",
             "data_quality_confidence"]


def run(panel: pd.DataFrame) -> pd.DataFrame:
    """Per (port_id, date) data-quality features derived from the merged panel."""
    if panel is None or panel.empty:
        return pd.DataFrame(columns=_OUT_COLS)

    frame = panel.copy()
    frame[DATE] = pd.to_datetime(frame[DATE], errors="coerce")

    critical = [c for c in _CRITICAL_COLUMNS if c in frame.columns]
    confidence_cols = [c for c in _CONFIDENCE_COLUMNS if c in frame.columns]

    # Global provenance readiness acts as a ceiling: if the registry says a feed
    # is synthetic, no port-day can claim pristine data.
    registry_readiness = provenance.readiness_score()
    ceiling = registry_readiness if registry_readiness > 0 else 1.0

    parts = []
    for _, group in frame.sort_values([PORT_ID, DATE]).groupby(PORT_ID, sort=False):
        g = group.copy()

        completeness = (g[critical].notna().mean(axis=1) if critical
                        else pd.Series(1.0, index=g.index))

        newest = g[DATE].max()
        age_days = (newest - g[DATE]).dt.total_seconds() / 86400.0
        # Only the trailing rows are "current"; older rows are historical and
        # legitimately so, hence freshness is reported, not penalised as error.
        freshness = (1.0 - (age_days / (_STALE_AFTER_DAYS * 30.0))).clip(0, 1)

        expected = pd.Series(1.0, index=g.index)
        observed = g[DATE].diff().dt.days.fillna(1.0)
        gap_penalty = ((observed - 1.0) / 7.0).clip(0, 1)
        continuity = (expected - gap_penalty).rolling(
            _CONTINUITY_WINDOW, min_periods=1).mean().clip(0, 1)

        if confidence_cols:
            trust = g[confidence_cols].apply(
                pd.to_numeric, errors="coerce").mean(axis=1).fillna(0.5)
        else:
            trust = pd.Series(0.5, index=g.index)
        trust = (trust * ceiling).clip(0, 1)

        score = (0.35 * completeness + 0.20 * freshness
                 + 0.15 * continuity + 0.30 * trust).clip(0, 1)

        g["data_completeness"] = completeness.round(4)
        g["data_freshness"] = freshness.round(4)
        g["data_continuity"] = continuity.round(4)
        g["source_trust"] = trust.round(4)
        g["data_quality_score"] = score.round(4)
        # How confident we are in the quality assessment itself: high when we
        # actually had columns to inspect.
        g["data_quality_confidence"] = round(
            min(1.0, (len(critical) + len(confidence_cols)) /
                float(len(_CRITICAL_COLUMNS) + len(_CONFIDENCE_COLUMNS))), 3)
        parts.append(g)

    out = pd.concat(parts, ignore_index=True)
    log.info("Data quality expert produced %d rows (mean score %.3f, registry "
             "readiness %.2f).", len(out), float(out["data_quality_score"].mean()),
             registry_readiness)
    return out[_OUT_COLS]


def degraded_ports(features: pd.DataFrame, threshold: float = 0.6) -> list[str]:
    """Ports whose latest data quality is below the usable threshold."""
    if features is None or features.empty:
        return []
    latest = (features.sort_values([PORT_ID, DATE])
              .groupby(PORT_ID, as_index=False).tail(1))
    flagged = latest[latest["data_quality_score"] < threshold]
    return sorted(flagged[PORT_ID].astype(str).tolist())
