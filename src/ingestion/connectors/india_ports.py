"""India major-port traffic connector (the India-centric data backbone).

Produces monthly, port-level data for India's major ports:
  * traffic   : cargo tonnes, container TEU, dwell hours, turnaround days,
                capacity utilisation, output per ship-berth-day.
  * commodity : cargo split by commodity group (POL/crude, containers, coal,
                iron ore, fertiliser, other).
  * trade     : import/export tonnes + trade value (INR crore).

Live sources (set keys/ids to enable; offline fallback otherwise):
  * data.gov.in OGD API "Traffic Handled at Major Ports"  (DATA_GOV_IN_API_KEY)
  * Sagar Unnati performance dashboard (turnaround / output per ship-berthday)
  * DGCIS foreign-trade portal (commodity x port import/export)

If live data is unavailable we synthesise a realistic dataset (seeded, with
magnitudes scaled by each port's relative capacity) so all analytics run offline.

Sources:
  https://www.data.gov.in/catalog/traffic-handled-major-ports-india
  https://shipmin.dashboard.nic.in/   (Sagar Unnati)
  https://www.dgciskol.gov.in/        (DGCIS foreign trade)
"""

from __future__ import annotations

from src.utils.settings import get_settings

from typing import Dict

import numpy as np
import pandas as pd

from src.ingestion.connectors.base import cached_json
from src.utils.config import PORTS, PORT_ID, RANDOM_SEED
from src.utils.logging_utils import get_logger

log = get_logger(__name__)

DATA_GOV_IN_API_KEY = get_settings().DATA_GOV_IN_API_KEY
DATA_GOV_IN_RESOURCE = get_settings().DATA_GOV_IN_PORT_RESOURCE_ID  # optional

COMMODITIES = ["pol_crude", "containers", "coal", "iron_ore", "fertiliser", "other"]

# Rough commodity-mix archetypes by port character (shares sum ~1).
_CONTAINER_PORTS = {"JNPT", "MUNDRA", "CHENNAI", "COCHIN", "TUTICORIN"}
_BULK_PORTS = {"PARADIP", "DEENDAYAL", "VIZAG", "MORMUGAO", "NEW_MANGALORE"}


def fetch_india_port_traffic(months: int = 36,
                             seed: int = RANDOM_SEED) -> Dict[str, pd.DataFrame]:
    """Return {'traffic','commodity','trade'} monthly per-port DataFrames."""
    from src.utils import provenance
    live = _try_data_gov_in(months)
    if live is not None:
        provenance.record("India port traffic (data.gov.in)", provenance.LIVE)
        return live
    provenance.record("India port traffic (data.gov.in)", provenance.SYNTHETIC,
                      "set DATA_GOV_IN_API_KEY + resource id to go live")
    return _synthetic(months, seed)


# ---------------------------------------------------------------------------
def _try_data_gov_in(months: int):
    if not (DATA_GOV_IN_API_KEY and DATA_GOV_IN_RESOURCE):
        return None
    url = f"https://api.data.gov.in/resource/{DATA_GOV_IN_RESOURCE}"
    data = cached_json(url, key="datagovin_port_traffic", ttl=24 * 3600,
                       params={"api-key": DATA_GOV_IN_API_KEY, "format": "json",
                               "limit": 5000})
    recs = (data or {}).get("records")
    if not recs:
        return None
    try:
        df = pd.DataFrame(recs)
        log.info("India ports: loaded %d records from data.gov.in.", len(df))
        # Shape varies by resource; downstream analytics tolerate extra columns.
        return {"traffic": df, "commodity": pd.DataFrame(), "trade": pd.DataFrame()}
    except Exception as exc:  # pragma: no cover
        log.warning("data.gov.in parse failed (%s); using synthetic.", exc)
        return None


# ---------------------------------------------------------------------------
def _synthetic(months: int, seed: int) -> Dict[str, pd.DataFrame]:
    rng = np.random.default_rng(seed)
    end = pd.Timestamp.today().normalize().replace(day=1)
    month_index = pd.date_range(end - pd.DateOffset(months=months - 1), end, freq="MS")

    traffic_rows, commodity_rows, trade_rows = [], [], []
    for p in PORTS:
        cap = p.port_capacity
        annual_mt = 130 * cap                      # ~MT/yr scaled by capacity
        container_share = 0.55 if p.port_id in _CONTAINER_PORTS else (
            0.12 if p.port_id in _BULK_PORTS else 0.30)
        base_turnaround = 1.4 + (1 - cap) * 2.2    # efficient ports turn faster
        trend = np.linspace(0, 0.12, len(month_index))  # gentle growth

        for i, m in enumerate(month_index):
            seasonal = 1 + 0.08 * np.sin((m.month - 3) / 12 * 2 * np.pi)
            cargo_mt = annual_mt / 12 * seasonal * (1 + trend[i]) * (1 + rng.normal(0, 0.04))
            cargo_mt = max(cargo_mt, 0.1)
            teu = cargo_mt * container_share * 70 * (1 + rng.normal(0, 0.05))  # ~TEU/'000t
            util = float(np.clip(0.55 + 0.3 * cap + rng.normal(0, 0.04), 0.3, 0.98))
            turnaround = float(max(0.8, base_turnaround * (0.9 + 0.4 * util)
                                   + rng.normal(0, 0.2)))
            dwell = float(max(6, turnaround * 24 * 0.6 + rng.normal(0, 6)))
            output_psbd = float(15000 * cap * (0.8 + 0.4 * util) + rng.normal(0, 800))

            traffic_rows.append({
                PORT_ID: p.port_id, "date": m, "year": m.year, "month": m.month,
                "cargo_mt": round(cargo_mt, 3),
                "containers_teu": round(teu, 0),
                "capacity_utilization": round(util, 3),
                "turnaround_days": round(turnaround, 2),
                "dwell_hours": round(dwell, 1),
                "output_per_ship_berth_day": round(output_psbd, 0),
            })

            # commodity split
            shares = _commodity_shares(p.port_id, container_share, rng)
            for c, s in shares.items():
                commodity_rows.append({PORT_ID: p.port_id, "date": m,
                                       "commodity": c,
                                       "cargo_mt": round(cargo_mt * s, 3)})

            # import / export + value
            imp_share = float(np.clip(0.55 + rng.normal(0, 0.05), 0.3, 0.8))
            imp = cargo_mt * imp_share
            exp = cargo_mt - imp
            # crude rupee value proxy: ~INR 4.5 cr per MT of cargo handled.
            value_cr = round(cargo_mt * 4.5, 1)
            trade_rows.append({PORT_ID: p.port_id, "date": m,
                               "import_mt": round(imp, 3), "export_mt": round(exp, 3),
                               "trade_value_inr_cr": value_cr})

    log.info("India ports: synthesised %d months x %d ports.",
             len(month_index), len(PORTS))
    return {"traffic": pd.DataFrame(traffic_rows),
            "commodity": pd.DataFrame(commodity_rows),
            "trade": pd.DataFrame(trade_rows)}


def _commodity_shares(port_id, container_share, rng) -> Dict[str, float]:
    if port_id in _BULK_PORTS:
        base = {"pol_crude": 0.25, "containers": 0.12, "coal": 0.28,
                "iron_ore": 0.20, "fertiliser": 0.08, "other": 0.07}
    elif port_id in _CONTAINER_PORTS:
        base = {"pol_crude": 0.18, "containers": container_share, "coal": 0.08,
                "iron_ore": 0.05, "fertiliser": 0.05, "other": 0.09}
    else:
        base = {"pol_crude": 0.22, "containers": 0.30, "coal": 0.18,
                "iron_ore": 0.10, "fertiliser": 0.08, "other": 0.12}
    # jitter + renormalise
    vals = {k: max(0.01, v * (1 + rng.normal(0, 0.08))) for k, v in base.items()}
    tot = sum(vals.values())
    return {k: v / tot for k, v in vals.items()}
