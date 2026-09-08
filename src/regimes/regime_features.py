"""Assemble the master feature panel.

This is the single place where the observed port series and all four expert
outputs are joined into one tidy table keyed by (port_id, date). The same panel
feeds both the HSMM (regime inference) and the forecasting layer, which keeps
the two perfectly time-aligned.

All joins are left-joins onto the observed grid, and missing expert values are
filled with neutral defaults so a missing source never crashes the pipeline
(it just lowers the relevant confidence column).
"""

from __future__ import annotations

import pandas as pd

from src.utils.config import DATE, PORT_ID
from src.utils.logging_utils import get_logger

log = get_logger(__name__)

# Columns the HSMM consumes (per the project spec). Any that are absent are
# created and filled with neutral values by `assemble_panel`.
HSMM_FEATURES = [
    # operational signals
    "queue_proxy", "turnaround_proxy", "WxImpactIndex", "geo_risk_score",
    "event_spike_score", "demand_pressure", "vessel_density", "throughput",
    "utilization",
    # macro / conditions signals (prices, currency, inflation, live news) -> the
    # HSMM now infers regimes from economic conditions, not just port ops.
    "oil_stress", "fx_stress", "inflation_stress", "news_stress",
    # specialist agents -- these are first-class regime evidence, not display
    # decoration: a capacity squeeze or an arrival burst is precisely the kind
    # of state change a semi-Markov model should be able to latch onto.
    "capacity_pressure", "queue_momentum", "anomaly_score",
    "arrival_clustering", "berth_pressure", "disruption_pressure",
    "weather_persistence",
]

# Neutral fill values used when a feature is missing.
_NEUTRAL = {
    "queue_proxy": 0.0, "turnaround_proxy": 0.0, "WxImpactIndex": 0.0,
    "geo_risk_score": 0.0, "event_spike_score": 0.0, "demand_pressure": 0.5,
    "vessel_density": 0.0, "throughput": 0.0, "utilization": 0.5,
    "oil_stress": 0.5, "fx_stress": 0.5, "inflation_stress": 0.5,
    "news_stress": 0.0,
    "capacity_pressure": 0.5, "queue_momentum": 0.5, "anomaly_score": 0.0,
    "arrival_clustering": 0.0, "berth_pressure": 0.0,
    "disruption_pressure": 0.0, "weather_persistence": 0.0,
}


def _prep(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or df.empty:
        return pd.DataFrame(columns=[PORT_ID, DATE])
    out = df.copy()
    if DATE in out.columns:
        out[DATE] = pd.to_datetime(out[DATE])
    return out


def assemble_panel(observed: pd.DataFrame,
                   weather_now: pd.DataFrame | None = None,
                   news: pd.DataFrame | None = None,
                   port_ops: pd.DataFrame | None = None,
                   trade: pd.DataFrame | None = None,
                   macro: pd.DataFrame | None = None,
                   extras: list | None = None) -> pd.DataFrame:
    """Left-join observed + expert features into one (port_id, date) panel.

    `macro` is a national daily conditions frame (oil/fx/inflation/news stress);
    it is broadcast across ports by date so the HSMM can use it.

    `extras` carries the specialist frames (capacity, anomaly, arrival dynamics,
    disruption propagation, weather persistence). They must be joined *here*,
    before the neutral fill below: several of their columns are HSMM features,
    and a later join would find the placeholder column already present and
    silently leave the model running on neutral defaults.
    """
    base = _prep(observed)
    if base.empty:
        raise ValueError("assemble_panel: observed frame is required and non-empty.")

    panel = base.copy()

    def join(other: pd.DataFrame | None, cols):
        nonlocal panel
        other = _prep(other)
        if other.empty:
            return
        keep = [PORT_ID, DATE] + [c for c in cols if c in other.columns]
        panel = panel.merge(other[keep].drop_duplicates([PORT_ID, DATE]),
                            on=[PORT_ID, DATE], how="left")

    # weather nowcast (horizon_day == 0 rows)
    if weather_now is not None and not weather_now.empty:
        w = weather_now
        if "horizon_day" in w.columns:
            w = w[w["horizon_day"] == 0]
        join(w, ["WxImpactIndex", "wind_risk", "rain_risk", "wave_risk",
                 "storm_risk", "weather_confidence"])
    join(news, ["geo_risk_score", "news_sentiment_score", "strike_risk",
                "policy_risk", "conflict_risk", "event_spike_score",
                "news_confidence"])
    join(port_ops, ["vessel_density", "avg_speed_near_port", "anchorage_count",
                    "arrival_count", "departure_count", "queue_proxy",
                    "turnaround_proxy", "ais_confidence"])
    join(trade, ["demand_index", "demand_pressure", "trade_trend",
                 "demand_confidence"])

    # Macro conditions are national (date-keyed) -> broadcast across ports.
    macro = _prep(macro)
    if not macro.empty:
        mcols = [c for c in ["oil_stress", "fx_stress", "inflation_stress",
                             "news_stress", "macro_pressure"] if c in macro.columns]
        panel = panel.merge(macro[[DATE] + mcols].drop_duplicates(DATE),
                            on=DATE, how="left")

    # Specialist experts, joined before the neutral fill (see the docstring).
    for extra in extras or []:
        extra = _prep(extra)
        if extra.empty:
            continue
        cols = [c for c in extra.columns if c not in (PORT_ID, DATE)]
        panel = panel.merge(
            extra[[PORT_ID, DATE] + cols].drop_duplicates([PORT_ID, DATE]),
            on=[PORT_ID, DATE], how="left", suffixes=("", "_dup"))
        panel = panel.drop(columns=[c for c in panel.columns if c.endswith("_dup")])

    # Ensure every HSMM feature exists and is filled with a neutral default.
    for col in HSMM_FEATURES:
        if col not in panel.columns:
            panel[col] = _NEUTRAL[col]
        panel[col] = pd.to_numeric(panel[col], errors="coerce").fillna(_NEUTRAL[col])

    panel = panel.sort_values([PORT_ID, DATE]).reset_index(drop=True)
    log.info("Assembled feature panel: %d rows x %d cols (%d ports).",
             len(panel), panel.shape[1], panel[PORT_ID].nunique())
    return panel


def select_hsmm_matrix(panel: pd.DataFrame):
    """Return (feature_matrix_df, feature_names) used by the HSMM."""
    feats = [c for c in HSMM_FEATURES if c in panel.columns]
    return panel[[PORT_ID, DATE] + feats].copy(), feats
