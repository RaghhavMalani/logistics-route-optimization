"""TFT-ready dataset builder.

Two products
------------
1. `build_supervised(...)` -> a single long, leakage-safe table where each row is
   one (port, forecast_origin_date, horizon_day) example with:
       * past-observed features  (target value at origin + lags + rolling mean)
       * origin-time expert + regime features
       * known-future features   (calendar of target_date, weather forecast at
                                   target_date)
       * static port features
   plus the label columns y_<target> = observed target at target_date.
   This is exactly the matrix the baseline forecaster trains on, and it makes
   the train/known-future/static split explicit.

2. `tft_spec()` -> the column-role metadata (static / time-varying-known /
   time-varying-unknown / targets) that a `pytorch_forecasting.TimeSeriesDataSet`
   needs. tft_model.py consumes this to build the real TFT.

Leakage rules enforced here
---------------------------
  * Every feature attached to an example is known at `forecast_origin_date`,
    EXCEPT the explicitly known-future covariates (calendar + weather forecast),
    which in production are available at origin time.
  * Labels are the only values read from `target_date`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List

import numpy as np
import pandas as pd

from src.utils.config import (
    DATE,
    FORECAST_HORIZON_DAYS,
    FORECAST_TARGETS,
    PORT_ID,
    PRIMARY_TARGET,
    static_features_frame,
)
from src.utils.logging_utils import get_logger

log = get_logger(__name__)


# ---------------------------------------------------------------------------
# Calendar features (known-future)
# ---------------------------------------------------------------------------
def add_calendar_features(df: pd.DataFrame, date_col: str,
                          prefix: str = "cal_") -> pd.DataFrame:
    out = df.copy()
    d = pd.to_datetime(out[date_col])
    out[f"{prefix}dow"] = d.dt.dayofweek
    out[f"{prefix}is_weekend"] = (d.dt.dayofweek >= 5).astype(int)
    out[f"{prefix}month"] = d.dt.month
    out[f"{prefix}day"] = d.dt.day
    # cyclical encodings help the model treat month/dow as periodic
    out[f"{prefix}month_sin"] = np.sin(2 * np.pi * d.dt.month / 12)
    out[f"{prefix}month_cos"] = np.cos(2 * np.pi * d.dt.month / 12)
    return out


CALENDAR_COLS = ["cal_dow", "cal_is_weekend", "cal_month", "cal_day",
                 "cal_month_sin", "cal_month_cos"]


# ---------------------------------------------------------------------------
# Origin-time feature frame
# ---------------------------------------------------------------------------
_LAGS = [1, 3, 7]
_ROLL = 7

# Origin-time expert/regime columns to carry (those present are used).
_ORIGIN_FEATURES = [
    "WxImpactIndex", "wind_risk", "rain_risk", "wave_risk", "storm_risk",
    "geo_risk_score", "news_sentiment_score", "strike_risk", "policy_risk",
    "conflict_risk", "event_spike_score",
    "queue_proxy", "turnaround_proxy", "vessel_density", "avg_speed_near_port",
    "anchorage_count", "demand_pressure", "trade_trend", "utilization",
    # specialist agents -- wired directly into the forecaster's feature space so
    # capacity, anomaly, arrival-dynamics, disruption and weather-persistence
    # evidence changes the forecast itself, not just the dashboard.
    "capacity_pressure", "queue_momentum", "throughput_stress",
    "anomaly_score", "congestion_anomaly", "delay_anomaly",
    "arrival_acceleration", "arrival_clustering", "anchorage_buildup",
    "berth_pressure", "disruption_exposure", "disruption_pressure",
    "weather_shock", "weather_persistence", "weather_forward_load",
    "data_quality_score", "specialist_stress",
    # macro / conditions (oil, currency, inflation, live news) -> the forecast
    # itself now reacts to economic conditions, not just the regime label.
    "oil_stress", "fx_stress", "inflation_stress", "news_stress",
    # regime outputs
    "p_normal", "p_congested", "p_severe", "days_in_state",
    "expected_remaining_days", "transition_risk", "regime_confidence",
]


def _build_origin_features(panel: pd.DataFrame, targets: List[str]) -> pd.DataFrame:
    df = panel.sort_values([PORT_ID, DATE]).copy()
    g = df.groupby(PORT_ID, sort=False)

    # Past-observed target features (all known at origin date).
    for tgt in targets:
        if tgt not in df.columns:
            continue
        df[f"{tgt}_now"] = df[tgt]
        for lag in _LAGS:
            df[f"{tgt}_lag{lag}"] = g[tgt].shift(lag)
        df[f"{tgt}_roll{_ROLL}"] = (g[tgt]
                                    .rolling(_ROLL, min_periods=1)
                                    .mean().reset_index(level=0, drop=True))
    return df


def origin_feature_columns(df: pd.DataFrame, targets: List[str]) -> List[str]:
    cols = []
    for tgt in targets:
        if tgt in df.columns:
            cols += [f"{tgt}_now"] + [f"{tgt}_lag{l}" for l in _LAGS] + [f"{tgt}_roll{_ROLL}"]
    cols += [c for c in _ORIGIN_FEATURES if c in df.columns]
    return cols


# ---------------------------------------------------------------------------
# Supervised builder
# ---------------------------------------------------------------------------
@dataclass
class SupervisedData:
    frame: pd.DataFrame
    feature_cols: List[str]
    target_cols: List[str]          # y_<target>
    available_targets: List[str]
    static_cols: List[str]
    known_future_cols: List[str]
    meta_cols: List[str] = field(default_factory=lambda: [
        PORT_ID, "forecast_origin_date", "target_date", "horizon_day"])


def build_supervised(panel: pd.DataFrame,
                     weather_now: pd.DataFrame | None = None,
                     horizon: int = FORECAST_HORIZON_DAYS,
                     targets: List[str] | None = None) -> SupervisedData:
    targets = targets or FORECAST_TARGETS
    # Keep only targets that exist AND have at least some observed values
    # (e.g. throughput is all-NaN in the DGQI-only real dataset).
    available = [t for t in targets
                 if t in panel.columns and panel[t].notna().any()]
    if PRIMARY_TARGET not in available and available:
        log.warning("Primary target '%s' missing; using '%s'.",
                    PRIMARY_TARGET, available[0])
    if not available:
        raise ValueError("No forecast targets present in panel.")

    df = _build_origin_features(panel, available)
    origin_cols = origin_feature_columns(df, available)

    origins = df[[PORT_ID, DATE] + origin_cols].rename(
        columns={DATE: "forecast_origin_date"})

    # Known-future weather at the target date (forecast available at origin).
    wx_future = None
    wx_cols: List[str] = []
    if weather_now is not None and not weather_now.empty:
        w = weather_now.copy()
        if "horizon_day" in w.columns:
            w = w[w["horizon_day"] == 0]
        wx_cols = [c for c in ["WxImpactIndex", "wind_risk", "rain_risk",
                               "wave_risk", "storm_risk"] if c in w.columns]
        wx_future = (w[[PORT_ID, DATE] + wx_cols]
                     .rename(columns={DATE: "target_date",
                                      **{c: f"future_{c}" for c in wx_cols}}))
        wx_cols = [f"future_{c}" for c in wx_cols]

    # Labels per horizon.
    label_src = panel[[PORT_ID, DATE] + available].copy()
    rows = []
    for h in range(1, horizon + 1):
        lab = label_src.rename(columns={DATE: "target_date",
                                        **{t: f"y_{t}" for t in available}})
        lab["forecast_origin_date"] = lab["target_date"] - pd.to_timedelta(h, unit="D")
        lab["horizon_day"] = h
        merged = origins.merge(
            lab, on=[PORT_ID, "forecast_origin_date"], how="inner")
        rows.append(merged)
    out = pd.concat(rows, ignore_index=True)

    # Attach known-future calendar + weather.
    out = add_calendar_features(out, "target_date")
    if wx_future is not None:
        out = out.merge(wx_future, on=[PORT_ID, "target_date"], how="left")

    # Static port features.
    static = static_features_frame()
    static = pd.get_dummies(static, columns=["region"], prefix="region")
    static_cols = [c for c in static.columns if c not in (PORT_ID, "name")]
    out = out.merge(static[[PORT_ID] + static_cols], on=PORT_ID, how="left")

    known_future_cols = CALENDAR_COLS + wx_cols
    feature_cols = origin_cols + known_future_cols + static_cols + ["horizon_day"]
    target_cols = [f"y_{t}" for t in available]

    # Safe NA handling: fill remaining feature NaNs (early lags) with 0.
    out[feature_cols] = out[feature_cols].apply(pd.to_numeric, errors="coerce").fillna(0.0)
    out = out.dropna(subset=target_cols, how="all").reset_index(drop=True)

    log.info("Supervised set: %d rows, %d features, targets=%s.",
             len(out), len(feature_cols), available)
    return SupervisedData(frame=out, feature_cols=feature_cols,
                          target_cols=target_cols, available_targets=available,
                          static_cols=static_cols, known_future_cols=known_future_cols)


def build_inference(panel: pd.DataFrame,
                    weather_now: pd.DataFrame | None = None,
                    horizon: int = FORECAST_HORIZON_DAYS,
                    origins: Dict[str, pd.Timestamp] | None = None,
                    targets: List[str] | None = None) -> SupervisedData:
    """Build prediction rows (no labels required) for a live forecast.

    Mirrors `build_supervised` feature construction but does NOT inner-join
    labels, so it works for the most recent origin whose future is unobserved.
    If `origins` is None, the latest available date per port is used as origin.
    """
    targets = targets or FORECAST_TARGETS
    available = [t for t in targets
                 if t in panel.columns and panel[t].notna().any()]
    df = _build_origin_features(panel, available)
    origin_cols = origin_feature_columns(df, available)

    if origins is None:
        origins = (df.groupby(PORT_ID)[DATE].max().to_dict())

    origin_rows = []
    for pid, odate in origins.items():
        row = df[(df[PORT_ID] == pid) & (df[DATE] == pd.to_datetime(odate))]
        if not row.empty:
            origin_rows.append(row.iloc[[-1]])
    if not origin_rows:
        raise ValueError("build_inference: no matching origin rows found.")
    origins_df = pd.concat(origin_rows, ignore_index=True)[
        [PORT_ID, DATE] + origin_cols].rename(columns={DATE: "forecast_origin_date"})

    # expand horizons
    frames = []
    for h in range(1, horizon + 1):
        f = origins_df.copy()
        f["horizon_day"] = h
        f["target_date"] = f["forecast_origin_date"] + pd.to_timedelta(h, unit="D")
        frames.append(f)
    out = pd.concat(frames, ignore_index=True)

    out = add_calendar_features(out, "target_date")

    wx_cols: List[str] = []
    if weather_now is not None and not weather_now.empty:
        w = weather_now.copy()
        if "horizon_day" in w.columns:
            w = w[w["horizon_day"] == 0]
        base_cols = [c for c in ["WxImpactIndex", "wind_risk", "rain_risk",
                                 "wave_risk", "storm_risk"] if c in w.columns]
        wx_future = (w[[PORT_ID, DATE] + base_cols]
                     .rename(columns={DATE: "target_date",
                                      **{c: f"future_{c}" for c in base_cols}}))
        out = out.merge(wx_future, on=[PORT_ID, "target_date"], how="left")
        wx_cols = [f"future_{c}" for c in base_cols]

    static = static_features_frame()
    static = pd.get_dummies(static, columns=["region"], prefix="region")
    static_cols = [c for c in static.columns if c not in (PORT_ID, "name")]
    out = out.merge(static[[PORT_ID] + static_cols], on=PORT_ID, how="left")

    known_future_cols = CALENDAR_COLS + wx_cols
    feature_cols = origin_cols + known_future_cols + static_cols + ["horizon_day"]
    out[feature_cols] = out[feature_cols].apply(pd.to_numeric, errors="coerce").fillna(0.0)

    return SupervisedData(frame=out, feature_cols=feature_cols, target_cols=[],
                          available_targets=available, static_cols=static_cols,
                          known_future_cols=known_future_cols)


# ---------------------------------------------------------------------------
# TFT column-role metadata (for pytorch-forecasting)
# ---------------------------------------------------------------------------
def tft_spec(sup: SupervisedData) -> Dict[str, object]:
    """Return the column roles a TimeSeriesDataSet would be configured with.

    time_varying_unknown_reals are the past-observed signals (targets + experts);
    time_varying_known_reals are calendar + weather forecast; static_reals are
    the port attributes. This dict documents exactly how tft_model.py should map
    our panel onto pytorch_forecasting.TimeSeriesDataSet.
    """
    past_observed = [c for c in sup.feature_cols
                     if c not in sup.known_future_cols
                     and c not in sup.static_cols
                     and c != "horizon_day"]
    return {
        "time_idx": "time_idx",
        "group_ids": [PORT_ID],
        "targets": sup.available_targets,
        "static_reals": sup.static_cols,
        "time_varying_known_reals": sup.known_future_cols + ["horizon_day"],
        "time_varying_unknown_reals": past_observed,
        "max_encoder_length": 30,
        "max_prediction_length": FORECAST_HORIZON_DAYS,
    }
