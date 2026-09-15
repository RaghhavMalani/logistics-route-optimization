"""Macro-conditions connector: the economic context the HSMM now reacts to.

Pulls daily macro series that drive India's maritime-trade conditions:
  * Brent crude (FRED DCOILBRENTEU)        -> energy / oil shock pressure
  * USD/INR     (FRED DEXINUS)             -> currency / import-cost pressure
  * India CPI   (FRED INDCPIALLMINMEI)     -> inflation pressure (YoY)

All free (FRED public CSV, no key). Offline -> deterministic synthetic series.
Combined with the GDELT event feed, these become the "current conditions" that
the macro expert turns into stress features for the regime (HSMM) model.

Source: https://fred.stlouisfed.org/
"""

from __future__ import annotations

import io

import numpy as np
import pandas as pd

from src.ingestion.connectors.base import cached_text
from src.utils.logging_utils import get_logger

log = get_logger(__name__)

FRED = "https://fred.stlouisfed.org/graph/fredgraph.csv?id={sid}"
_SERIES = {"brent_usd": "DCOILBRENTEU", "usd_inr": "DEXINUS",
           "cpi_index": "INDCPIALLMINMEI"}


def _fred(sid: str, name: str) -> pd.DataFrame | None:
    txt = cached_text(FRED.format(sid=sid), key=f"fred_{sid}", ttl=12 * 3600)
    if not txt:
        return None
    try:
        df = pd.read_csv(io.StringIO(txt))
        df.columns = ["date", name]
        df["date"] = pd.to_datetime(df["date"], errors="coerce")
        df[name] = pd.to_numeric(df[name], errors="coerce")
        return df.dropna()
    except Exception:
        return None


def fetch_macro_conditions(days: int = 540) -> pd.DataFrame:
    """Daily macro frame: date, brent_usd, usd_inr, cpi_index, inflation_yoy."""
    frames = []
    for name, sid in _SERIES.items():
        f = _fred(sid, name)
        if f is not None and not f.empty:
            frames.append(f.set_index("date"))
    from src.utils import provenance
    if frames:
        macro = pd.concat(frames, axis=1).sort_index().ffill()
        macro = macro.tail(days).reset_index()
        provenance.record("Macro: oil / FX / inflation (FRED)", provenance.LIVE,
                          "Brent, USD/INR and CPI series from the public CSV endpoints",
                          provider="FRED (Federal Reserve Bank of St. Louis)")
    else:
        log.warning("Macro: FRED unavailable; using synthetic conditions.")
        macro = _synthetic(days)
        provenance.record("Macro: oil / FX / inflation (FRED)",
                          provenance.SYNTHETIC, "FRED unreachable",
                          provider="FRED (Federal Reserve Bank of St. Louis)", fallback="synthetic conditions")

    # ensure all columns exist
    for c in ["brent_usd", "usd_inr", "cpi_index"]:
        if c not in macro.columns:
            macro[c] = np.nan
    macro = macro.sort_values("date")
    macro[["brent_usd", "usd_inr", "cpi_index"]] = \
        macro[["brent_usd", "usd_inr", "cpi_index"]].ffill().bfill()
    # YoY inflation from the CPI index (~252 trading days back ~ 1y; use 250)
    macro["inflation_yoy"] = (macro["cpi_index"] /
                              macro["cpi_index"].shift(250) - 1) * 100
    macro["inflation_yoy"] = macro["inflation_yoy"].bfill().fillna(5.0)
    return macro.reset_index(drop=True)


def _synthetic(days: int) -> pd.DataFrame:
    rng = np.random.default_rng(11)
    end = pd.Timestamp.today().normalize()
    dates = pd.date_range(end - pd.Timedelta(days=days - 1), end, freq="D")
    brent = np.clip(80 + np.cumsum(rng.normal(0, 0.6, len(dates))) * 0.3, 55, 130)
    inr = np.clip(82 + np.cumsum(rng.normal(0, 0.05, len(dates))) * 0.3, 78, 90)
    cpi = 170 + np.linspace(0, 9, len(dates)) + np.cumsum(rng.normal(0, 0.05, len(dates)))
    return pd.DataFrame({"date": dates, "brent_usd": brent.round(2),
                         "usd_inr": inr.round(2), "cpi_index": cpi.round(2)})
