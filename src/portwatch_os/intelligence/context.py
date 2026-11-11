"""Read global economic context without synthetic substitutions or date rewrites."""
from __future__ import annotations

import io
from pathlib import Path

import pandas as pd

from src.portwatch_os.clock import LIVE, get_clock, wall_now, world_now
from src.portwatch_os.fabric.products import ProductCatalogue
from src.portwatch_os.freshness.reviewed_sources import ECB_RATES, ecb_context, permits_publication

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
        if key == "usd_inr":
            _, product = ProductCatalogue().product(ECB_RATES)
            if permits_publication(product):
                now = wall_now()  # wall-clock: compare the live ECB reference date to real time.
                quote.update(
                    label="USD / INR · ECB cross rate", series="ECB-EUR-CROSS",
                    source="https://www.ecb.europa.eu/stats/policy_and_exchange_rates/euro_reference_exchange_rates/html/index.en.html",
                    shippingConnection="ECB reference rates via Frankfurter. INR per USD is derived from same-date EUR legs.",
                    **ecb_context(now),
                )
                result.append(quote)
                continue
        if key in ('usd_inr','brent'):
            from src.portwatch_os.intelligence.free_sources import public_product
            public=public_product('fred_fx' if key=='usd_inr' else 'fred_brent')
            if public.get('rows'):
                rows=public['rows'];last=rows[-1];previous=rows[-2]['value'] if len(rows)>1 else None
                quote.update(value=last['value'],observedAt=last['date'],status=public['freshness'],
                    changePct=100*(last['value']/previous-1) if previous else None,
                    firstAvailableAt=public['firstAvailableAt'],lastSuccessfulCheckAt=public['lastSuccessfulCheckAt'],
                    sha256=public['sha256'],timePrecision='DATE_ONLY',origin='OFFICIAL_REPORT')
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
                quote.update(value=float(last["value"]), observedAt=last["date"].date().isoformat(),
                             ageHours=round(age, 1), status="CACHED" if age <= budget else "STALE",
                             changePct=100*(float(last["value"])/float(previous)-1) if previous else None)
        except (OSError, ValueError, pd.errors.ParserError):
            pass
        result.append(quote)
    return result
