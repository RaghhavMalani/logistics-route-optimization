"""Weather Expert Module.

Converts raw weather observations/forecasts into numerical weather-risk
features for each port and date.

Output columns (per the project spec)
-------------------------------------
    port_id, date, horizon_day,
    wind_risk, rain_risk, wave_risk, storm_risk,
    weather_confidence, WxImpactIndex   (0..1)

WxImpactIndex interpretation:  0.0-0.3 low | 0.3-0.6 moderate | 0.6-1.0 high.

Two products are exposed:
  * `run()`            -> nowcast table (horizon_day == 0), one row per port/date.
  * `build_future_known()` -> horizon-expanded table (horizon_day 0..H) used by
                              the TFT as **future-known covariates**: at a given
                              forecast origin we know the next 10 days of
                              weather *forecast*, so WxImpactIndex at the target
                              date is a legitimate known-future input.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from src.utils.config import DATE, FORECAST_HORIZON_DAYS, PORT_ID
from src.experts.base import row_confidence, sort_key, to_risk
from src.utils.logging_utils import get_logger

log = get_logger(__name__)

# Physical centres/scales for logistic risk transforms (used for raw inputs).
_WIND_CENTER, _WIND_SCALE = 25.0, 6.0      # knots: ~25kn is operationally risky
_RAIN_CENTER, _RAIN_SCALE = 25.0, 12.0     # mm/day
_WAVE_CENTER, _WAVE_SCALE = 2.0, 0.7       # metres
_VIS_CENTER, _VIS_SCALE = 4.0, 1.5         # km (low visibility -> high risk)

# Weights for the composite WxImpactIndex.
_WEIGHTS = {"wind_risk": 0.30, "rain_risk": 0.20, "wave_risk": 0.25,
            "storm_risk": 0.25}


def _compute_risks(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()

    out["wind_risk"] = (to_risk(out["wind_speed"], _WIND_CENTER, _WIND_SCALE)
                        if "wind_speed" in out else np.nan)
    out["rain_risk"] = (to_risk(out["rainfall"], _RAIN_CENTER, _RAIN_SCALE)
                        if "rainfall" in out else np.nan)

    if "wave_height" in out and out["wave_height"].notna().any():
        out["wave_risk"] = to_risk(out["wave_height"], _WAVE_CENTER, _WAVE_SCALE)
        # The marine endpoint does not cover every port-day (the reanalysis
        # archive carries no wave field at all), so fill the gaps per row with
        # the wind-derived proxy rather than leaving NaNs the models cannot use.
        out["wave_risk"] = out["wave_risk"].fillna(out["wind_risk"])
    else:
        out["wave_risk"] = out["wind_risk"]

    # Storm risk blends an explicit storm flag with a low-visibility signal.
    storm_flag = out["storm_flag"].fillna(0) if "storm_flag" in out else 0.0
    if "visibility" in out and out["visibility"].notna().any():
        vis_risk = 1.0 - to_risk(out["visibility"], _VIS_CENTER, _VIS_SCALE)
    else:
        vis_risk = 0.0
    out["storm_risk"] = np.clip(0.7 * np.asarray(storm_flag, dtype=float)
                                + 0.3 * np.asarray(vis_risk, dtype=float), 0, 1)

    # Composite index (0..1).
    comp = np.zeros(len(out))
    for col, w in _WEIGHTS.items():
        comp = comp + w * out[col].fillna(0).to_numpy()
    out["WxImpactIndex"] = np.clip(comp, 0, 1).round(4)

    # Confidence from how many physical inputs were actually present.
    inputs = [c for c in ["wind_speed", "rainfall", "wave_height", "visibility"]
              if c in df.columns]
    out["weather_confidence"] = row_confidence(df, inputs) if inputs else 0.5

    for c in ["wind_risk", "rain_risk", "wave_risk", "storm_risk"]:
        # A missing physical input means "no measured risk", not "unknown number
        # that crashes the model"; the drop is recorded in weather_confidence.
        out[c] = pd.to_numeric(out[c], errors="coerce").fillna(0.0).round(4)
    return out


def run(weather_raw: pd.DataFrame) -> pd.DataFrame:
    """Nowcast weather-risk features (horizon_day = 0)."""
    if weather_raw is None or weather_raw.empty:
        log.warning("weather_raw is empty; weather expert returns empty frame.")
        return pd.DataFrame(columns=[PORT_ID, DATE, "horizon_day", "wind_risk",
                                     "rain_risk", "wave_risk", "storm_risk",
                                     "weather_confidence", "WxImpactIndex"])
    df = sort_key(weather_raw)
    feats = _compute_risks(df)
    feats["horizon_day"] = 0
    cols = [PORT_ID, DATE, "horizon_day", "wind_risk", "rain_risk", "wave_risk",
            "storm_risk", "weather_confidence", "WxImpactIndex"]
    return feats[cols]


def build_future_known(weather_raw: pd.DataFrame,
                       horizon: int = FORECAST_HORIZON_DAYS) -> pd.DataFrame:
    """Horizon-expanded weather covariates for the TFT.

    For each (port, origin_date) and each horizon_day h in 0..horizon, attach the
    weather risk that will hold on target_date = origin_date + h. In production
    the +h values come from a weather *forecast* issued at origin_date, so this
    is a known-future covariate and not leakage.
    """
    now = run(weather_raw)
    if now.empty:
        return now.assign(forecast_origin_date=pd.NaT, target_date=pd.NaT)

    feat_cols = ["wind_risk", "rain_risk", "wave_risk", "storm_risk",
                 "weather_confidence", "WxImpactIndex"]
    base = now[[PORT_ID, DATE] + feat_cols].copy()
    base = base.rename(columns={DATE: "target_date"})

    frames = []
    for h in range(0, horizon + 1):
        shifted = base.copy()
        shifted["horizon_day"] = h
        shifted["forecast_origin_date"] = shifted["target_date"] - pd.to_timedelta(h, unit="D")
        frames.append(shifted)
    out = pd.concat(frames, ignore_index=True)
    return out[[PORT_ID, "forecast_origin_date", "target_date", "horizon_day"] + feat_cols]
