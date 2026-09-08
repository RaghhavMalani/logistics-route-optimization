"""Weather Persistence Expert.

A single bad-weather day and a five-day monsoon system need opposite operational
responses: the first is absorbed by a berth window shuffle, the second needs
arrivals staggered and yard space reserved. The raw WxImpactIndex cannot tell
them apart, so this expert decomposes weather risk into three signals:

    weather_shock        today's risk relative to the port's recent norm
    weather_persistence  how sustained the elevated risk has been
    weather_forward_load the weather risk already in the known forecast window

``weather_forward_load`` is the one place the system deliberately looks forward,
and it is legitimate: a weather forecast issued today is available at the
forecast origin, which is exactly what makes it a known-future covariate. The
shock and persistence terms remain strictly backward-looking.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from src.utils.config import DATE, PORT_ID
from src.utils.logging_utils import get_logger

log = get_logger(__name__)

_BASELINE_WINDOW = 30
_PERSISTENCE_WINDOW = 5
_MIN_HISTORY = 7
_FORWARD_DAYS = 5

_OUT_COLS = [PORT_ID, DATE, "weather_shock", "weather_persistence",
             "weather_forward_load", "weather_regime",
             "weather_persistence_confidence"]


def _classify(shock: float, persistence: float) -> str:
    if persistence >= 0.55:
        return "PERSISTENT"
    if shock >= 0.6:
        return "SHOCK"
    if persistence >= 0.3 or shock >= 0.35:
        return "UNSETTLED"
    return "CALM"


def run(weather_features: pd.DataFrame,
        forward_weather: pd.DataFrame | None = None) -> pd.DataFrame:
    """Decompose the weather nowcast into shock vs persistent disruption.

    ``weather_features`` is the weather expert's nowcast table (horizon_day 0).
    ``forward_weather`` may carry future-dated rows from the same source; when
    present, the forward load is computed from them.
    """
    if weather_features is None or weather_features.empty:
        return pd.DataFrame(columns=_OUT_COLS)

    frame = weather_features.copy()
    frame[DATE] = pd.to_datetime(frame[DATE], errors="coerce")
    if "horizon_day" in frame.columns:
        frame = frame[frame["horizon_day"] == 0]
    if "WxImpactIndex" not in frame.columns:
        return pd.DataFrame(columns=_OUT_COLS)

    forward_lookup: dict[tuple[str, pd.Timestamp], float] = {}
    if forward_weather is not None and not forward_weather.empty:
        fw = forward_weather.copy()
        fw[DATE] = pd.to_datetime(fw[DATE], errors="coerce")
        if "WxImpactIndex" in fw.columns:
            forward_lookup = {
                (str(p), pd.Timestamp(d)): float(v)
                for p, d, v in zip(fw[PORT_ID], fw[DATE], fw["WxImpactIndex"])
                if pd.notna(v)
            }

    parts = []
    for port_id, group in frame.sort_values([PORT_ID, DATE]).groupby(PORT_ID, sort=False):
        g = group.copy()
        impact = pd.to_numeric(g["WxImpactIndex"], errors="coerce").fillna(0.0)

        past = impact.shift(1)
        baseline = past.rolling(_BASELINE_WINDOW, min_periods=_MIN_HISTORY).mean()
        spread = past.rolling(_BASELINE_WINDOW, min_periods=_MIN_HISTORY).std()
        # Shock: how far above its own recent norm today's weather risk sits.
        shock = ((impact - baseline) / spread.replace(0, np.nan)).clip(0, 3) / 3.0
        shock = shock.fillna((impact - baseline.fillna(impact)).clip(0, 1))

        elevated = (impact >= 0.45).astype(float)
        persistence = elevated.rolling(_PERSISTENCE_WINDOW, min_periods=1).mean()

        # Forward load: mean weather risk over the next few known-forecast days.
        forward_values = []
        for date in g[DATE]:
            window = [
                forward_lookup.get((str(port_id), pd.Timestamp(date) + pd.Timedelta(days=k)))
                for k in range(1, _FORWARD_DAYS + 1)
            ]
            present = [v for v in window if v is not None]
            forward_values.append(float(np.mean(present)) if present else np.nan)
        forward = pd.Series(forward_values, index=g.index)
        # With no forecast rows available, fall back to today's observation
        # rather than inventing a forward-looking number.
        forward_confidence = forward.notna().astype(float)
        forward = forward.fillna(impact)

        g["weather_shock"] = shock.clip(0, 1).round(4)
        g["weather_persistence"] = persistence.clip(0, 1).round(4)
        g["weather_forward_load"] = forward.clip(0, 1).round(4)
        g["weather_regime"] = [
            _classify(s, p) for s, p in zip(g["weather_shock"], g["weather_persistence"])
        ]
        base_conf = (pd.to_numeric(g["weather_confidence"], errors="coerce").fillna(0.5)
                     if "weather_confidence" in g.columns
                     else pd.Series(0.5, index=g.index))
        history_conf = past.notna().rolling(
            _BASELINE_WINDOW, min_periods=1).sum() / float(_MIN_HISTORY)
        g["weather_persistence_confidence"] = (
            base_conf * (0.7 + 0.3 * forward_confidence) * history_conf.clip(0, 1)
        ).clip(0, 1).round(3)
        parts.append(g)

    out = pd.concat(parts, ignore_index=True)
    log.info("Weather persistence expert produced %d rows across %d ports.",
             len(out), out[PORT_ID].nunique())
    return out[_OUT_COLS]
