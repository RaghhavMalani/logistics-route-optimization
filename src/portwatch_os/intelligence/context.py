"""Read global economic context without synthetic substitutions or date rewrites."""
from __future__ import annotations

import io
from pathlib import Path

import pandas as pd

from src.portwatch_os.clock import LIVE, get_clock, world_now

SERIES = (
    ("brent", "Brent crude", "DCOILBRENTEU", "USD/bbl", "Fuel and energy cost exposure"),
    ("usd_inr", "USD / INR", "DEXINUS", "INR/USD", "Import cost and settlement exposure"),
    ("india_cpi", "India CPI", "INDCPIALLMINMEI", "index", "Inflation context for operating costs"),
)


def economic_context(cache_dir: Path) -> list[dict]:
    result = []
    for key, label, sid, unit, connection in SERIES:
        quote = {"id": key, "label": label, "series": sid, "unit": unit,
                 "source": f"https://fred.stlouisfed.org/series/{sid}",
                 "shippingConnection": connection, "status": "UNAVAILABLE",
                 "value": None, "changePct": None, "observedAt": None, "ageHours": None}
        path = cache_dir / f"fred_{sid}.txt"
        if get_clock().state.mode != LIVE:
            quote["shippingConnection"] += "; historical publication vintages unavailable"
            result.append(quote)
            continue
        try:
            frame = pd.read_csv(io.StringIO(path.read_text(encoding="utf-8")))
            frame.columns = ["date", "value"]
            frame["date"] = pd.to_datetime(frame["date"], utc=True, errors="coerce")
            frame["value"] = pd.to_numeric(frame["value"], errors="coerce")
            frame = frame.dropna().sort_values("date")
            frame = frame[frame["date"] <= pd.Timestamp(world_now())]
            if not frame.empty:
                last = frame.iloc[-1]
                previous = frame.iloc[-2]["value"] if len(frame) > 1 else None
                age = (world_now()-last["date"].to_pydatetime()).total_seconds()/3600
                budget = 24*60 if key == "india_cpi" else 24*7
                quote.update(value=float(last["value"]), observedAt=last["date"].isoformat(),
                             ageHours=round(age, 1), status="CACHED" if age <= budget else "STALE",
                             changePct=100*(float(last["value"])/float(previous)-1) if previous else None)
        except (OSError, ValueError, pd.errors.ParserError):
            pass
        result.append(quote)
    return result
