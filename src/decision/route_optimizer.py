"""Dynamic route / port-call optimization.

Given the 10-day forecast, recommend for a vessel:
  * the best arrival day at its intended port (lowest expected cost),
  * a recommended ETA buffer,
  * and ranked alternative ports if the intended port is too congested.

The "cost" of calling at a port on a given day blends the forecast delay, the
congestion probability, and a travel penalty (great-circle distance from the
vessel's current position). This is a transparent, explainable optimizer -- not
a black box -- which is what a port/ship manager needs.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional

import numpy as np
import pandas as pd

from src.decision.decision_layer import prob_exceed
from src.utils.config import PORT_BY_ID, PORT_ID, PORT_IDS
from src.utils.logging_utils import get_logger

log = get_logger(__name__)

# Approximate port coordinates (lat, lon) for great-circle travel penalties.
PORT_COORDS: Dict[str, tuple] = {
    "DEENDAYAL": (23.02, 70.22),
    "MUNDRA": (22.74, 69.70),
    "JNPT": (18.95, 72.95),
    "MUMBAI": (18.96, 72.84),
    "MORMUGAO": (15.40, 73.80),
    "NEW_MANGALORE": (12.92, 74.80),
    "COCHIN": (9.97, 76.27),
    "TUTICORIN": (8.75, 78.20),
    "CHENNAI": (13.10, 80.30),
    "KAMARAJAR": (13.25, 80.33),
    "VIZAG": (17.69, 83.22),
    "PARADIP": (20.26, 86.67),
    "KOLKATA": (22.55, 88.31),
}

# Cost weights.
W_DELAY = 1.0          # per hour of expected delay
W_CONGESTION = 40.0    # per unit congestion probability (>threshold)
W_TRAVEL = 0.02        # per km of diversion
AVG_SPEED_KMPH = 35.0  # ~19 knots, to convert distance -> extra steaming hours


def haversine_km(a: tuple, b: tuple) -> float:
    R = 6371.0
    lat1, lon1, lat2, lon2 = map(np.radians, [a[0], a[1], b[0], b[1]])
    dlat, dlon = lat2 - lat1, lon2 - lon1
    h = np.sin(dlat / 2) ** 2 + np.cos(lat1) * np.cos(lat2) * np.sin(dlon / 2) ** 2
    return float(2 * R * np.arcsin(np.sqrt(h)))


@dataclass
class Vessel:
    name: str
    target_port: str
    position: Optional[tuple] = None          # (lat, lon); default = target port
    earliest_day: int = 1                     # earliest arrival horizon day
    latest_day: int = 7                       # latest acceptable horizon day
    candidate_ports: List[str] = field(default_factory=list)


def _port_cost_by_day(forecast: pd.DataFrame, port: str) -> pd.DataFrame:
    g = forecast[forecast[PORT_ID] == port].sort_values("horizon_day").copy()
    if g.empty:
        return g
    g["congestion_probability"] = [
        prob_exceed(r.q10, r.q50, r.q90, 50.0) for r in g.itertuples()]
    delay = g["predicted_delay"].fillna(g["q50"])  # fall back to congestion proxy
    g["operational_cost"] = (W_DELAY * delay
                             + W_CONGESTION * g["congestion_probability"])
    return g


def best_arrival_window(forecast: pd.DataFrame, port: str,
                        earliest: int = 1, latest: int = 10) -> Dict:
    g = _port_cost_by_day(forecast, port)
    if g.empty:
        return {}
    win = g[(g["horizon_day"] >= earliest) & (g["horizon_day"] <= latest)]
    if win.empty:
        win = g
    best = win.loc[win["operational_cost"].idxmin()]
    worst = win.loc[win["operational_cost"].idxmax()]
    buffer_hours = int(np.clip(float(win["predicted_delay"].fillna(win["q50"]).max())
                               * 0.6, 4, 48))
    return {
        "port_id": port,
        "best_arrival_day": int(best["horizon_day"]),
        "best_target_date": best["target_date"],
        "worst_arrival_day": int(worst["horizon_day"]),
        "recommended_buffer_hours": buffer_hours,
        "best_day_cost": round(float(best["operational_cost"]), 2),
        "best_day_congestion_prob": round(float(best["congestion_probability"]), 3),
    }


def recommend_route(forecast: pd.DataFrame, vessel: Vessel) -> Dict:
    """Score the target port and candidates; recommend the best port + day."""
    pos = vessel.position or PORT_COORDS.get(vessel.target_port)
    candidates = list(dict.fromkeys([vessel.target_port] + (
        vessel.candidate_ports or [])))

    scored = []
    for port in candidates:
        if port not in PORT_IDS:
            continue
        win = best_arrival_window(forecast, port, vessel.earliest_day,
                                  vessel.latest_day)
        if not win:
            continue
        dist = haversine_km(pos, PORT_COORDS[port]) if pos else 0.0
        travel_hours = dist / AVG_SPEED_KMPH
        total = win["best_day_cost"] + W_TRAVEL * dist
        scored.append({
            "port_id": port,
            "port_name": PORT_BY_ID[port].name if port in PORT_BY_ID else port,
            "best_arrival_day": win["best_arrival_day"],
            "best_target_date": win["best_target_date"],
            "congestion_prob": win["best_day_congestion_prob"],
            "diversion_km": round(dist, 0),
            "extra_steaming_hours": round(travel_hours, 1),
            "recommended_buffer_hours": win["recommended_buffer_hours"],
            "total_cost": round(total, 2),
            "is_intended": port == vessel.target_port,
        })

    if not scored:
        return {"vessel": vessel.name, "recommendation": "No forecast available.",
                "options": pd.DataFrame()}

    table = pd.DataFrame(scored).sort_values("total_cost").reset_index(drop=True)
    best = table.iloc[0]
    intended = table[table["is_intended"]].iloc[0] if table["is_intended"].any() else best

    reroute = (not best["is_intended"]) and (
        intended["total_cost"] - best["total_cost"] > 0.15 * intended["total_cost"])

    if reroute:
        msg = (f"{vessel.name}: consider rerouting from {intended['port_name']} "
               f"to {best['port_name']} (Day +{best['best_arrival_day']}). "
               f"Expected cost {best['total_cost']} vs {intended['total_cost']} "
               f"(+{best['extra_steaming_hours']}h steaming, "
               f"{best['diversion_km']:.0f} km diversion).")
    else:
        msg = (f"{vessel.name}: keep {intended['port_name']}; best arrival "
               f"Day +{intended['best_arrival_day']} "
               f"({intended['best_target_date'].date() if hasattr(intended['best_target_date'], 'date') else intended['best_target_date']}), "
               f"buffer {intended['recommended_buffer_hours']}h, "
               f"congestion prob {intended['congestion_prob']}.")

    return {"vessel": vessel.name, "recommended_port": best["port_id"],
            "reroute": bool(reroute), "recommendation": msg, "options": table}


def demo_vessels() -> List[Vessel]:
    """A few illustrative vessels for the demo / dashboard."""
    return [
        Vessel("MV Konkan", target_port="JNPT", earliest_day=1, latest_day=7,
               candidate_ports=["MUNDRA", "COCHIN"]),
        Vessel("MV Coromandel", target_port="CHENNAI", earliest_day=2, latest_day=8,
               candidate_ports=["VIZAG", "KOLKATA"]),
        Vessel("MV Malabar", target_port="COCHIN", earliest_day=1, latest_day=6,
               candidate_ports=["JNPT"]),
    ]


def optimize_fleet(forecast: pd.DataFrame,
                   vessels: List[Vessel] | None = None,
                   panel: pd.DataFrame | None = None) -> pd.DataFrame:
    """Score every vessel against the live forecast and report the trade-off.

    The output is deliberately comparative: for each vessel it reports the
    intended call and the best alternative side by side, with the ETA, risk and
    port-wait differences between them, so an operator can see *why* a reroute
    is or is not worth it rather than being handed a bare instruction.
    """
    vessels = vessels or demo_vessels()
    wait_by_port = _expected_wait(forecast)
    risk_by_port = _entry_risk(forecast)

    rows = []
    for v in vessels:
        rec = recommend_route(forecast, v)
        options = rec["options"]
        if options.empty:
            rows.append({"vessel": v.name, "intended_port": v.target_port,
                         "recommended_port": None, "reroute": False,
                         "recommendation": rec["recommendation"]})
            continue

        best = options.iloc[0]
        intended = (options[options["is_intended"]].iloc[0]
                    if options["is_intended"].any() else best)

        intended_wait = wait_by_port.get(str(intended["port_id"]), float("nan"))
        best_wait = wait_by_port.get(str(best["port_id"]), float("nan"))
        wait_delta = (round(float(best_wait - intended_wait), 2)
                      if pd.notna(intended_wait) and pd.notna(best_wait) else None)

        # ETA difference = extra steaming to the alternative, minus the waiting
        # time it saves. Negative means the vessel is alongside sooner.
        extra_steaming = float(best["extra_steaming_hours"]) - float(
            intended["extra_steaming_hours"])
        eta_delta = (round(extra_steaming + wait_delta, 2)
                     if wait_delta is not None else round(extra_steaming, 2))

        risk_delta = None
        intended_risk = risk_by_port.get(str(intended["port_id"]))
        best_risk = risk_by_port.get(str(best["port_id"]))
        if intended_risk is not None and best_risk is not None:
            risk_delta = round(float(best_risk - intended_risk), 4)

        rows.append({
            "vessel": v.name,
            "intended_port": v.target_port,
            "recommended_port": rec.get("recommended_port"),
            "reroute": bool(rec.get("reroute")),
            "best_arrival_day": int(best["best_arrival_day"]),
            "intended_arrival_day": int(intended["best_arrival_day"]),
            "eta_delta_hours": eta_delta,
            "risk_delta": risk_delta,
            "port_wait_delta_hours": wait_delta,
            "recommended_buffer_hours": int(intended["recommended_buffer_hours"]),
            "diversion_km": float(best["diversion_km"]),
            "extra_steaming_hours": float(best["extra_steaming_hours"]),
            "intended_congestion_prob": float(intended["congestion_prob"]),
            "alternative_congestion_prob": float(best["congestion_prob"]),
            "recommendation": rec["recommendation"],
        })
    return pd.DataFrame(rows)


def _expected_wait(forecast: pd.DataFrame) -> Dict[str, float]:
    """Mean predicted berth wait per port across the forecast horizon."""
    if forecast is None or forecast.empty:
        return {}
    frame = forecast.copy()
    delay = pd.to_numeric(frame.get("predicted_delay"), errors="coerce")
    if delay is None or delay.isna().all():
        delay = pd.to_numeric(frame["q50"], errors="coerce") * 0.2
    frame["_wait"] = delay
    return {str(k): float(v) for k, v in
            frame.groupby(PORT_ID)["_wait"].mean().items()}


def _entry_risk(forecast: pd.DataFrame) -> Dict[str, float]:
    """Mean P(congestion > threshold) per port -- the comparable risk number."""
    if forecast is None or forecast.empty:
        return {}
    out: Dict[str, float] = {}
    for port_id, group in forecast.groupby(PORT_ID):
        probs = [prob_exceed(r.q10, r.q50, r.q90, 50.0) for r in group.itertuples()]
        out[str(port_id)] = float(np.mean(probs)) if probs else 0.0
    return out
