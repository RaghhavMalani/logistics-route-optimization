"""Port Ops / AIS-Proxy Expert Module.

Converts AIS-like (or satellite-derived) vessel-activity data into port
congestion features. Three modes, chosen automatically from the input columns:

  * REAL      : `port_ops_raw` has full vessel-activity columns. We compute
                queue / turnaround proxies directly, high ais_confidence (0.9).
  * PORTWATCH : `port_ops_raw` has PortWatch columns (portcalls/import/export)
                -- real satellite-AIS-derived daily aggregates from the IMF
                PortWatch feed. Features are derived from call pressure vs. each
                port's own (strictly backward) baseline. ais_confidence 0.75:
                real measurements, but daily aggregates rather than raw tracks.
  * PROXY     : `port_ops_raw` is missing/empty. We synthesise plausible vessel
                activity from the observed congestion series and report low
                ais_confidence (0.35) so the rest of the system knows the AIS
                signal is imputed.

Output columns (per the project spec)
-------------------------------------
    port_id, date, vessel_density, avg_speed_near_port, anchorage_count,
    arrival_count, departure_count, queue_proxy, turnaround_proxy, ais_confidence
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from src.utils.config import DATE, PORT_ID, RANDOM_SEED
from src.experts.base import logistic, minmax01, sort_key
from src.utils.logging_utils import get_logger

log = get_logger(__name__)

_OUT_COLS = [PORT_ID, DATE, "vessel_density", "avg_speed_near_port",
             "anchorage_count", "arrival_count", "departure_count",
             "queue_proxy", "turnaround_proxy", "ais_confidence"]

_AIS_COLS = ["vessel_density", "avg_speed_near_port", "anchorage_count",
             "arrival_count", "departure_count"]

# Columns that identify the IMF PortWatch satellite-AIS daily feed.
_PORTWATCH_COLS = ["portcalls", "import", "export"]


def _derive_proxies(df: pd.DataFrame) -> pd.DataFrame:
    """Given real-ish AIS columns, compute queue/turnaround proxies (0..1-ish)."""
    out = df.copy()

    # queue_proxy: pressure from anchored vessels relative to arrivals.
    anch = out["anchorage_count"].astype(float)
    arr = out["arrival_count"].astype(float).clip(lower=1)
    out["queue_proxy"] = (anch / (arr + anch)).clip(0, 1)

    # turnaround_proxy: slow average speed + many anchored => slow turnaround.
    speed_term = 1.0 - minmax01(out["avg_speed_near_port"])
    queue_term = minmax01(anch)
    out["turnaround_proxy"] = (0.6 * speed_term + 0.4 * queue_term).clip(0, 1)

    for c in ["queue_proxy", "turnaround_proxy"]:
        out[c] = out[c].round(4)
    return out


def _features_from_portwatch(raw: pd.DataFrame) -> pd.DataFrame:
    """PORTWATCH mode: real AIS-derived daily aggregates -> expert features.

    All baselines are expanding statistics shifted one day, so the feature for
    day t never uses information from day t or later (leakage-safe).
    """
    parts = []
    for pid, g in sort_key(raw).groupby(PORT_ID, sort=False):
        g = g.copy()
        calls = g["portcalls"].astype(float)
        tonnes = (g["import"].astype(float).fillna(0)
                  + g["export"].astype(float).fillna(0))

        calls7 = calls.rolling(7, min_periods=1).mean()
        base = calls7.expanding(min_periods=14).mean().shift(1)
        ratio = (calls7 / base).replace([np.inf, -np.inf], np.nan)

        g["arrival_count"] = calls
        # PortWatch counts completed calls; use them for departures too (a call
        # implies both an arrival and, shortly after, a departure).
        g["departure_count"] = calls
        g["vessel_density"] = calls7
        # Queue buildup: calls in excess of the port's usual level.
        g["anchorage_count"] = (calls - base).clip(lower=0).fillna(0)
        g["avg_speed_near_port"] = np.nan  # not observable from daily counts

        # queue_proxy: 0.5 at baseline pressure, ->1 as calls approach ~2x usual.
        g["queue_proxy"] = logistic(ratio.fillna(1.0), center=1.15, scale=0.25)
        # turnaround_proxy: efficiency drop = fewer tonnes moved per call than
        # the port's own historical norm while pressure is elevated.
        eff7 = (tonnes / calls.clip(lower=1)).rolling(7, min_periods=1).mean()
        eff_base = eff7.expanding(min_periods=14).mean().shift(1)
        eff_ratio = (eff_base / eff7.clip(lower=1)).replace(
            [np.inf, -np.inf], np.nan)
        slow = logistic(eff_ratio.fillna(1.0), center=1.10, scale=0.25)
        g["turnaround_proxy"] = (0.6 * g["queue_proxy"] + 0.4 * slow).clip(0, 1)
        parts.append(g)
    out = pd.concat(parts, ignore_index=True)
    for c in ["queue_proxy", "turnaround_proxy"]:
        out[c] = out[c].astype(float).round(4)
    return out


def _synthesise_from_congestion(observed: pd.DataFrame, seed: int) -> pd.DataFrame:
    """PROXY fallback: build AIS-like activity from observed congestion."""
    rng = np.random.default_rng(seed)
    df = sort_key(observed)[[PORT_ID, DATE, "congestion_index"]].copy()
    c = df["congestion_index"].astype(float).fillna(df["congestion_index"].median())

    df["anchorage_count"] = np.clip(np.round(2 + 0.18 * c
                                             + rng.normal(0, 1.0, len(df))), 0, None)
    df["vessel_density"] = np.clip(10 + 0.25 * c + rng.normal(0, 2, len(df)), 0, None)
    df["avg_speed_near_port"] = np.clip(9 - 0.05 * c + rng.normal(0, 0.5, len(df)),
                                        1, None)
    df["arrival_count"] = np.clip(np.round(6 + rng.normal(0, 1.5, len(df))), 0, None)
    df["departure_count"] = np.clip(np.round(df["arrival_count"]
                                             + rng.normal(0, 1, len(df))), 0, None)
    df = df.drop(columns=["congestion_index"])
    return df


def run(port_ops_raw: pd.DataFrame | None,
        observed: pd.DataFrame | None = None,
        seed: int = RANDOM_SEED) -> pd.DataFrame:
    """Produce port-ops features. Falls back to a congestion-derived proxy when
    no AIS data is available.
    """
    from src.utils import provenance
    have_ais = (port_ops_raw is not None and not port_ops_raw.empty
                and all(c in port_ops_raw.columns for c in _AIS_COLS))
    have_portwatch = (not have_ais and port_ops_raw is not None
                      and not port_ops_raw.empty
                      and all(c in port_ops_raw.columns for c in _PORTWATCH_COLS))
    latest_observation = None
    if port_ops_raw is not None and not port_ops_raw.empty and DATE in port_ops_raw:
        latest_observation = pd.to_datetime(
            port_ops_raw[DATE], errors="coerce").max()

    if have_portwatch:
        provenance.record(
            "AIS / vessel activity", provenance.CACHED_LIVE,
            "Measured daily port calls and trade tonnage per Indian port.",
            provider="IMF PortWatch (satellite-AIS)",
            observed_at=latest_observation,
            rows=len(port_ops_raw),
            fallback=None)
    elif have_ais:
        provenance.record(
            "AIS / vessel activity", provenance.SYNTHETIC,
            "AIS-like sample bundle used for the offline demo.",
            provider="local sample generator",
            observed_at=latest_observation,
            rows=len(port_ops_raw),
            fallback="sample bundle")
    else:
        provenance.record(
            "AIS / vessel activity", provenance.SYNTHETIC,
            "No AIS feed available; vessel activity is imputed from observed "
            "congestion and reported at low confidence.",
            provider="derived proxy",
            fallback="congestion-derived proxy")

    if have_ais:
        log.info("Port-ops expert: using REAL/sample AIS-like data.")
        df = sort_key(port_ops_raw)
        feats = _derive_proxies(df)
        feats["ais_confidence"] = 0.9
    elif have_portwatch:
        log.info("Port-ops expert: PORTWATCH mode (real satellite-AIS "
                 "daily port calls + trade volumes).")
        feats = _features_from_portwatch(port_ops_raw)
        feats["ais_confidence"] = 0.75
    elif observed is not None and not observed.empty and "congestion_index" in observed:
        log.warning("Port-ops expert: no AIS data -> PROXY mode "
                    "(synthesising vessel activity from observed congestion).")
        df = _synthesise_from_congestion(observed, seed)
        feats = _derive_proxies(df)
        feats["ais_confidence"] = 0.35  # imputed -> low confidence
    else:
        log.error("Port-ops expert: no AIS data and no observed congestion; "
                  "returning empty frame.")
        return pd.DataFrame(columns=_OUT_COLS)

    feats["ais_confidence"] = feats["ais_confidence"].astype(float).round(3)
    for c in _AIS_COLS:
        feats[c] = feats[c].round(3)
    return feats[_OUT_COLS]
