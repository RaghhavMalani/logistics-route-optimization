"""Market data connector: oil + freight (the 'terminal' tickers).

Brent crude is pulled from FRED's public CSV endpoint (no API key required); if
offline we fall back to a synthetic series. A freight-rate index (Baltic-style)
is synthesised here (no free real-time API), with a clear hook to swap in a real
feed later.

  * fetch_brent()        -> DataFrame[date, brent_usd]
  * fetch_freight_index()-> DataFrame[date, freight_index]
  * latest_quote()       -> dict with latest value + day change for tickers

Sources:
  FRED Brent  : https://fred.stlouisfed.org/series/DCOILBRENTEU
  EIA API     : https://www.eia.gov/opendata/  (optional, set EIA_API_KEY)
"""

from __future__ import annotations

from src.utils.settings import get_settings

import io
from typing import Optional

import numpy as np
import pandas as pd

from src.ingestion.connectors.base import cached_text
from src.utils.logging_utils import get_logger

log = get_logger(__name__)

FRED_BRENT_CSV = "https://fred.stlouisfed.org/graph/fredgraph.csv?id=DCOILBRENTEU"
EIA_API_KEY = get_settings().EIA_API_KEY


def fetch_brent(days: int = 365) -> pd.DataFrame:
    from src.utils import provenance
    txt = cached_text(FRED_BRENT_CSV, key="fred_brent", ttl=12 * 3600)
    if txt:
        try:
            df = pd.read_csv(io.StringIO(txt))
            df.columns = ["date", "brent_usd"]
            df["date"] = pd.to_datetime(df["date"], errors="coerce")
            df["brent_usd"] = pd.to_numeric(df["brent_usd"], errors="coerce")
            df = df.dropna().tail(days).reset_index(drop=True)
            if not df.empty:
                provenance.record("Brent crude (FRED)", provenance.LIVE)
                return df
        except Exception as exc:
            log.warning("Brent parse failed (%s); using synthetic.", exc)
    provenance.record("Brent crude (FRED)", provenance.SYNTHETIC,
                      "FRED unreachable")
    return _synth_series("brent_usd", base=82.0, vol=1.5, days=days)


def fetch_freight_index(days: int = 365) -> pd.DataFrame:
    # Placeholder for a real feed (Baltic Dry Index / Freightos FBX / Drewry WCI).
    return _synth_series("freight_index", base=1500.0, vol=35.0, days=days)


def latest_quote(df: pd.DataFrame, value_col: str) -> dict:
    if df is None or df.empty:
        return {"value": float("nan"), "change_pct": float("nan")}
    s = df[value_col].to_numpy(dtype=float)
    last = float(s[-1])
    prev = float(s[-2]) if len(s) > 1 else last
    chg = (last - prev) / prev * 100 if prev else 0.0
    return {"value": round(last, 2), "change_pct": round(chg, 2),
            "as_of": str(df["date"].iloc[-1].date())}


def _synth_series(col: str, base: float, vol: float, days: int) -> pd.DataFrame:
    rng = np.random.default_rng(abs(hash(col)) % (2**32))
    end = pd.Timestamp.today().normalize()
    dates = pd.date_range(end - pd.Timedelta(days=days - 1), end, freq="D")
    walk = base + np.cumsum(rng.normal(0, vol, len(dates))) * 0.3
    walk = np.clip(walk, base * 0.5, base * 1.8)
    return pd.DataFrame({"date": dates, col: np.round(walk, 2)})
