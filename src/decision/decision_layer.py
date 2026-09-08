"""Decision layer -- turning a probabilistic forecast into an operator's order.

"Congestion is high" is not an instruction. This layer converts the quantile
forecast, the regime state and the specialist signals into a specific, bounded,
measurable action for a named target, together with the evidence behind it:

    action                 a verb an operator can execute today
    target                 which port / arrival window it applies to
    horizon                when it applies
    reason + top drivers   why, with each factor's measured contribution
    expected impact        the delay hours the action is expected to avoid
    alternative action     the fallback if the primary cannot be executed
    uncertainty            how wide the forecast band and model disagreement are
    confidence             the model's confidence, discounted for both

The arithmetic is deterministic and inspectable. No language model participates
in choosing an action or computing a number; text is only ever a rendering of
values computed here.

Output columns
--------------
    port_id, forecast_origin_date, target_date, horizon_day,
    predicted_congestion, congestion_probability, eta_delay_risk,
    port_entry_risk, weather_impact, operational_adjustment, priority_score,
    action_code, action_title, action_target, severity, reason, top_drivers,
    expected_impact, expected_delay_saved_hours, alternative_action,
    uncertainty, decision_confidence
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List

import numpy as np
import pandas as pd

from src.utils.config import DATE, PORT_ID
from src.utils.logging_utils import get_logger

log = get_logger(__name__)

#: Congestion (0..100) above which a port is treated as congested.
CONGESTION_THRESHOLD = 50.0

#: Nominal inbound approach used to convert a delay into a speed instruction.
NOMINAL_APPROACH_HOURS = 48.0
NOMINAL_SERVICE_SPEED_KN = 13.0

#: Model disagreement above this means "observe, do not commit".
DISAGREEMENT_HOLD = 0.55

#: Slow steaming can only absorb so much. Beyond this the honest instruction is
#: to re-time the call, not to tell a master to crawl for days.
MAX_SLOW_STEAM_HOURS = 36.0
MAX_SLOW_STEAM_KNOTS = 3.5
MIN_SLOW_STEAM_KNOTS = 0.8

#: Data quality below this means the recommendation is advisory only.
QUALITY_FLOOR = 0.55


@dataclass(frozen=True)
class Action:
    code: str
    title: str
    template: str
    alternative: str


ACTIONS: Dict[str, Action] = {
    "HOLD_ARRIVAL": Action(
        "HOLD_ARRIVAL", "Re-time inbound arrivals",
        "Delay inbound arrival by {shift_hours:.0f}h to the day-{best_day} window",
        "Hold vessels at outer anchorage and re-berth on the next free window"),
    "SLOW_STEAM": Action(
        "SLOW_STEAM", "Slow steam to the berth window",
        "Reduce approach speed by {slow_knots:.1f} kn to absorb {shift_hours:.0f}h "
        "of waiting at sea instead of at anchorage",
        "Hold arrival at anchorage if the schedule cannot absorb slower steaming"),
    "STAGGER_ARRIVALS": Action(
        "STAGGER_ARRIVALS", "Stagger the arrival stream",
        "Spread the next {cluster_window}d of arrivals across the window; "
        "arrivals are clustering at {clustering:.0%} above an even spread",
        "Hold the lowest-priority call and re-sequence tomorrow"),
    "REASSIGN_BERTH": Action(
        "REASSIGN_BERTH", "Reassign the berth slot",
        "Reassign the day-{horizon} berth slot; capacity pressure is "
        "{capacity:.0%} with queue momentum still rising",
        "Add a handling shift on the existing berth allocation"),
    "ADD_SHIFT": Action(
        "ADD_SHIFT", "Add a handling shift",
        "Add a handling shift and pre-clear yard space for day {horizon}",
        "Extend gate hours and defer non-priority cargo moves"),
    "YARD_OVERFLOW": Action(
        "YARD_OVERFLOW", "Activate the yard overflow plan",
        "Activate yard overflow: utilization {utilization:.0%} with "
        "{throughput_stress:.0%} throughput degradation",
        "Divert non-priority boxes to the secondary stack area"),
    "PREPOSITION_MARINE": Action(
        "PREPOSITION_MARINE", "Pre-position pilots and tugs",
        "Pre-position pilots and tugs for the day-{horizon} window; "
        "weather load is {weather:.0%} and {weather_regime}",
        "Confirm safe-berthing windows with the harbour master before committing"),
    "ETA_BUFFER": Action(
        "ETA_BUFFER", "Publish an ETA buffer",
        "Publish a {buffer_hours:.0f}h ETA buffer to lines for day {horizon}",
        "Advise a shorter buffer and review again at the next model run"),
    "DIVERT_PORT": Action(
        "DIVERT_PORT", "Evaluate an alternative port call",
        "Evaluate diverting to {alternative_port}: expected wait is "
        "{alt_saving:.0f}h lower on the same arrival window",
        "Keep the intended port and publish an extended ETA buffer"),
    "MONITOR_DISAGREEMENT": Action(
        "MONITOR_DISAGREEMENT", "Observe only -- models disagree",
        "Hold operational changes: model disagreement is {disagreement:.0%} "
        "and the 80% band spans {band:.0f} congestion points",
        "Re-evaluate at the next model run before committing resources"),
    "MONITOR_QUALITY": Action(
        "MONITOR_QUALITY", "Advisory only -- inputs degraded",
        "Treat as advisory: input data quality is {quality:.0%}; verify berth "
        "and arrival data before acting",
        "Fall back to the port's standing operating plan"),
    "NORMAL": Action(
        "NORMAL", "Maintain normal operations",
        "No intervention required; congestion probability is {prob:.0%}",
        "Continue standard monitoring"),
}


# ---------------------------------------------------------------------------
# Probability from quantiles
# ---------------------------------------------------------------------------
def prob_exceed(q10: float, q50: float, q90: float, threshold: float) -> float:
    """Estimate P(value > threshold) from three quantile points.

    Treats (q10, q50, q90) as points on the CDF at (0.1, 0.5, 0.9) and
    linearly interpolates or extrapolates, clamped to [0, 1].
    """
    pts = sorted([(q10, 0.1), (q50, 0.5), (q90, 0.9)])
    xs = [p[0] for p in pts]
    ps = [p[1] for p in pts]
    if threshold <= xs[0]:
        cdf = (ps[0] + (threshold - xs[0]) * (ps[1] - ps[0]) / (xs[1] - xs[0])
               if xs[1] > xs[0] else ps[0])
    elif threshold >= xs[2]:
        cdf = (ps[1] + (threshold - xs[1]) * (ps[2] - ps[1]) / (xs[2] - xs[1])
               if xs[2] > xs[1] else ps[2])
    elif threshold <= xs[1]:
        cdf = ps[0] + (threshold - xs[0]) * (ps[1] - ps[0]) / max(xs[1] - xs[0], 1e-9)
    else:
        cdf = ps[1] + (threshold - xs[1]) * (ps[2] - ps[1]) / max(xs[2] - xs[1], 1e-9)
    return round(1.0 - float(np.clip(cdf, 0.0, 1.0)), 4)


def _delay_risk(delay_hours: float) -> str:
    if np.isnan(delay_hours):
        return "Unknown"
    if delay_hours >= 24:
        return "High"
    if delay_hours >= 12:
        return "Medium"
    return "Low"


def slow_steam_knots(shift_hours: float,
                     approach_hours: float = NOMINAL_APPROACH_HOURS,
                     service_speed: float = NOMINAL_SERVICE_SPEED_KN) -> float:
    """Speed reduction that absorbs ``shift_hours`` of delay at sea.

    A vessel ``approach_hours`` from the pilot station covers the same distance
    in ``approach_hours + shift_hours`` at ``v * H / (H + d)``. The difference is
    the instruction an operator can hand to the master.
    """
    if shift_hours <= 0:
        return 0.0
    slower = service_speed * approach_hours / (approach_hours + shift_hours)
    return round(max(0.0, service_speed - slower), 2)


# ---------------------------------------------------------------------------
# Driver attribution
# ---------------------------------------------------------------------------
_DRIVER_WEIGHTS = {
    "congestion probability": 0.30,
    "capacity pressure": 0.16,
    "berth pressure": 0.12,
    "weather load": 0.12,
    "regime severity": 0.12,
    "anomaly": 0.10,
    "disruption exposure": 0.08,
}


def _drivers(signals: Dict[str, float]) -> List[tuple[str, float]]:
    """Rank the factors by their weighted contribution to the priority score."""
    contributions = [
        (name, round(weight * float(signals.get(name, 0.0)), 4))
        for name, weight in _DRIVER_WEIGHTS.items()
    ]
    contributions.sort(key=lambda item: item[1], reverse=True)
    return [c for c in contributions if c[1] > 0.005][:4]


def _format_drivers(drivers: List[tuple[str, float]]) -> str:
    return " | ".join(f"{name}={value}" for name, value in drivers)


# ---------------------------------------------------------------------------
# Action selection
# ---------------------------------------------------------------------------
def _select_action(context: Dict[str, float]) -> Action:
    """Deterministic rule cascade, ordered from 'do not act' to 'act hardest'."""
    if context["quality"] < QUALITY_FLOOR:
        return ACTIONS["MONITOR_QUALITY"]
    if context["disagreement"] >= DISAGREEMENT_HOLD and context["prob"] < 0.75:
        return ACTIONS["MONITOR_DISAGREEMENT"]

    if context["alt_saving"] >= 6.0 and context["prob"] >= 0.55:
        return ACTIONS["DIVERT_PORT"]
    if context["shift_hours"] >= 12.0 and context["prob"] >= 0.5:
        # Absorbing the wait at sea beats waiting at anchorage, but only when
        # the speed reduction is something a master can actually execute.
        executable = (context["shift_hours"] <= MAX_SLOW_STEAM_HOURS
                      and MIN_SLOW_STEAM_KNOTS <= context["slow_knots"]
                      <= MAX_SLOW_STEAM_KNOTS)
        return ACTIONS["SLOW_STEAM"] if executable else ACTIONS["HOLD_ARRIVAL"]
    if context["throughput_stress"] >= 0.35 and context["utilization"] >= 0.75:
        return ACTIONS["YARD_OVERFLOW"]
    if context["capacity"] >= 0.7 and context["queue_momentum"] >= 0.55:
        return ACTIONS["REASSIGN_BERTH"]
    if context["clustering"] >= 0.35 and context["prob"] >= 0.4:
        return ACTIONS["STAGGER_ARRIVALS"]
    if context["weather"] >= 0.55 or context["weather_persistent"]:
        return ACTIONS["PREPOSITION_MARINE"]
    if context["prob"] >= 0.6:
        return ACTIONS["ADD_SHIFT"]
    if context["prob"] >= 0.35:
        return ACTIONS["ETA_BUFFER"]
    return ACTIONS["NORMAL"]


def _severity(priority: float, action_code: str) -> str:
    if action_code in ("MONITOR_QUALITY", "MONITOR_DISAGREEMENT"):
        return "watch"
    if priority >= 0.72:
        return "severe"
    if priority >= 0.52:
        return "high"
    if priority >= 0.32:
        return "medium"
    return "normal"


# ---------------------------------------------------------------------------
def build_decisions(forecast: pd.DataFrame,
                    weather_now: pd.DataFrame | None = None,
                    threshold: float = CONGESTION_THRESHOLD,
                    panel: pd.DataFrame | None = None) -> pd.DataFrame:
    """Build the operational decision table from the forecast and panel state."""
    if forecast is None or forecast.empty:
        return pd.DataFrame()

    df = forecast.copy()
    context_by_port = _port_context(panel)
    wx = _weather_lookup(weather_now)
    best_windows = _best_windows(df, threshold)
    alternatives = _alternative_ports(df, threshold)

    rows = []
    for _, r in df.iterrows():
        port_id = r[PORT_ID]
        horizon = int(r["horizon_day"])
        state = context_by_port.get(str(port_id), {})

        cong_prob = prob_exceed(r["q10"], r["q50"], r["q90"], threshold)
        delay = float(r.get("predicted_delay", np.nan))
        eta_risk = _delay_risk(delay if pd.notna(delay) else np.nan)
        wx_val = wx.get(port_id, np.nan)
        weather_load = 0.0 if np.isnan(wx_val) else float(wx_val)

        band = float(r["q90"]) - float(r["q10"])
        disagreement = float(r.get("model_disagreement", 0.0) or 0.0)
        uncertainty = float(np.clip(band / 60.0 + 0.4 * disagreement, 0, 1))

        risk_num = 0.6 * cong_prob + 0.4 * {"Low": 0.2, "Medium": 0.6,
                                            "High": 1.0, "Unknown": 0.4}[eta_risk]
        entry_risk = ("High" if risk_num >= 0.6 else
                      "Medium" if risk_num >= 0.35 else "Low")

        window = best_windows.get(str(port_id), {})
        best_day = int(window.get("best_day", horizon))
        shift_hours = max(0.0, (best_day - horizon) * 24.0)
        # The saving is measured against *this* arrival day, not against the
        # worst day in the horizon, so the number is the one an operator gets.
        current_delay = float(delay) if pd.notna(delay) else float(
            window.get("delay_at_best", 0.0))
        delay_saved = max(0.0, current_delay - float(window.get("delay_at_best", 0.0)))
        alt = alternatives.get(str(port_id), {})

        signals = {
            "congestion probability": cong_prob,
            "capacity pressure": state.get("capacity_pressure", 0.0),
            "berth pressure": state.get("berth_pressure", 0.0),
            "weather load": weather_load,
            "regime severity": state.get("regime_severity", 0.0),
            "anomaly": state.get("anomaly_score", 0.0),
            "disruption exposure": state.get("disruption_pressure", 0.0),
        }
        drivers = _drivers(signals)
        priority = float(np.clip(sum(value for _, value in
                                     [(n, w * signals.get(n, 0.0))
                                      for n, w in _DRIVER_WEIGHTS.items()]), 0, 1))

        context = {
            "prob": cong_prob,
            "quality": state.get("data_quality_score", 1.0),
            "disagreement": disagreement,
            "band": band,
            "shift_hours": shift_hours,
            "slow_knots": slow_steam_knots(shift_hours),
            "alt_saving": float(alt.get("saving_hours", 0.0)),
            "alternative_port": alt.get("port_name", ""),
            "capacity": state.get("capacity_pressure", 0.0),
            "queue_momentum": state.get("queue_momentum", 0.0),
            "clustering": state.get("arrival_clustering", 0.0),
            "utilization": state.get("utilization", 0.0),
            "throughput_stress": state.get("throughput_stress", 0.0),
            "weather": weather_load,
            "weather_persistent": bool(state.get("weather_persistence", 0.0) >= 0.5),
            "weather_regime": state.get("weather_regime", "unsettled"),
            "best_day": best_day,
            "horizon": horizon,
            "cluster_window": 3,
            "buffer_hours": float(np.clip(delay * 0.6 if pd.notna(delay) else 6.0,
                                          4, 48)),
        }
        action = _select_action(context)
        instruction = action.template.format(**context)

        expected_impact = _expected_impact(action.code, context, delay_saved)
        decision_confidence = float(np.clip(
            float(r.get("confidence_score", 0.6)) * (1.0 - 0.35 * disagreement)
            * (0.7 + 0.3 * context["quality"]), 0.05, 0.97))

        rows.append({
            PORT_ID: port_id,
            "forecast_origin_date": r["forecast_origin_date"],
            "target_date": r["target_date"],
            "horizon_day": horizon,
            "predicted_congestion": round(float(r["predicted_congestion"]), 2),
            "congestion_probability": cong_prob,
            "eta_delay_risk": eta_risk,
            "port_entry_risk": entry_risk,
            "weather_impact": round(weather_load, 3) if not np.isnan(wx_val) else np.nan,
            "operational_adjustment": instruction,
            "priority_score": round(priority, 4),
            "action_code": action.code,
            "action_title": action.title,
            "action_target": _action_target(action.code, context, port_id),
            "severity": _severity(priority, action.code),
            "reason": _reason(action.code, context, drivers),
            "top_drivers": _format_drivers(drivers),
            "expected_impact": expected_impact["text"],
            "expected_delay_saved_hours": expected_impact["hours"],
            "alternative_action": action.alternative,
            "uncertainty": round(uncertainty, 3),
            "decision_confidence": round(decision_confidence, 3),
        })

    out = pd.DataFrame(rows)
    log.info("Decision layer produced %d rows (%d ports, %d distinct actions).",
             len(out), out[PORT_ID].nunique(), out["action_code"].nunique())
    return out


def _action_target(code: str, context: Dict, port_id) -> str:
    if code == "DIVERT_PORT" and context.get("alternative_port"):
        return f"{port_id} -> {context['alternative_port']}"
    if code in ("HOLD_ARRIVAL", "SLOW_STEAM"):
        return f"{port_id} inbound, day {context['horizon']} -> day {context['best_day']}"
    return f"{port_id} day {context['horizon']}"


def _reason(code: str, context: Dict, drivers: List[tuple[str, float]]) -> str:
    lead = ", ".join(f"{name} {value:.2f}" for name, value in drivers[:3])
    base = (f"P(congestion>{CONGESTION_THRESHOLD:.0f}) = {context['prob']:.0%} "
            f"at day {context['horizon']}")
    if code == "MONITOR_DISAGREEMENT":
        return (f"{base}; models disagree by {context['disagreement']:.0%} of the "
                f"forecast band, so the evidence does not yet support committing "
                f"resources. Leading factors: {lead}.")
    if code == "MONITOR_QUALITY":
        return (f"{base}; input data quality is {context['quality']:.0%}, below the "
                f"threshold for an operational instruction. Leading factors: {lead}.")
    return f"{base}. Leading factors: {lead}."


def _expected_impact(code: str, context: Dict, delay_saved: float) -> Dict:
    """The measurable consequence of taking the action, or an explicit none."""
    if code in ("HOLD_ARRIVAL", "SLOW_STEAM"):
        hours = round(float(delay_saved), 1)
        return {
            "hours": hours,
            "text": (f"Moving the call from day {context['horizon']} to day "
                     f"{context['best_day']} avoids about {hours:.1f}h of "
                     f"expected berth wait."),
        }
    if code == "DIVERT_PORT":
        hours = round(float(context["alt_saving"]), 1)
        return {"hours": hours,
                "text": (f"Calling {context['alternative_port']} instead is "
                         f"expected to cut waiting time by about {hours:.1f}h "
                         f"before steaming cost.")}
    if code == "ETA_BUFFER":
        return {"hours": round(float(context["buffer_hours"]), 1),
                "text": (f"A {context['buffer_hours']:.0f}h published buffer covers "
                         f"the 80% forecast band for day {context['horizon']}.")}
    if code in ("MONITOR_DISAGREEMENT", "MONITOR_QUALITY", "NORMAL"):
        return {"hours": 0.0, "text": "No operational change; no delay saving claimed."}
    return {"hours": round(float(delay_saved), 1),
            "text": (f"Relieves the day-{context['horizon']} pressure point; "
                     f"about {delay_saved:.1f}h of expected wait is addressable "
                     f"within the forecast window.")}


# ---------------------------------------------------------------------------
# Context builders
# ---------------------------------------------------------------------------
def _port_context(panel: pd.DataFrame | None) -> Dict[str, Dict[str, float]]:
    """Latest specialist state per port, used to choose and justify actions."""
    if panel is None or panel.empty:
        return {}
    frame = panel.copy()
    frame[DATE] = pd.to_datetime(frame[DATE], errors="coerce")
    latest = frame.sort_values(DATE).groupby(PORT_ID, as_index=False).tail(1)

    context: Dict[str, Dict[str, float]] = {}
    for _, row in latest.iterrows():
        def value(column: str, default: float = 0.0) -> float:
            raw = row.get(column, default)
            try:
                out = float(raw)
            except (TypeError, ValueError):
                return default
            return default if pd.isna(out) else out

        severity = max(value("p_severe"), 0.6 * value("p_congested"))
        context[str(row[PORT_ID])] = {
            "capacity_pressure": value("capacity_pressure"),
            "queue_momentum": value("queue_momentum"),
            "berth_pressure": value("berth_pressure"),
            "arrival_clustering": value("arrival_clustering"),
            "anomaly_score": value("anomaly_score"),
            "disruption_pressure": value("disruption_pressure"),
            "weather_persistence": value("weather_persistence"),
            "weather_regime": str(row.get("weather_regime", "unsettled")),
            "utilization": value("utilization", 0.5),
            "throughput_stress": value("throughput_stress"),
            "data_quality_score": value("data_quality_score", 1.0),
            "regime_severity": severity,
        }
    return context


def _weather_lookup(weather_now: pd.DataFrame | None) -> Dict[str, float]:
    if weather_now is None or weather_now.empty or "WxImpactIndex" not in weather_now:
        return {}
    w = weather_now.copy()
    if "horizon_day" in w.columns:
        w = w[w["horizon_day"] == 0]
    w = w.sort_values(DATE)
    return w.groupby(PORT_ID)["WxImpactIndex"].last().to_dict()


def _best_windows(forecast: pd.DataFrame, threshold: float) -> Dict[str, Dict]:
    """Cheapest and most expensive arrival day inside the forecast horizon."""
    windows: Dict[str, Dict] = {}
    for port_id, group in forecast.groupby(PORT_ID):
        g = group.sort_values("horizon_day").copy()
        probs = [prob_exceed(r.q10, r.q50, r.q90, threshold) for r in g.itertuples()]
        delay = pd.to_numeric(g.get("predicted_delay"), errors="coerce")
        delay = delay.fillna(pd.to_numeric(g["q50"], errors="coerce") * 0.2)
        cost = delay.to_numpy(dtype=float) + 40.0 * np.asarray(probs)
        best = int(np.argmin(cost))
        worst = int(np.argmax(cost))
        windows[str(port_id)] = {
            "best_day": int(g.iloc[best]["horizon_day"]),
            "worst_day": int(g.iloc[worst]["horizon_day"]),
            "delay_at_best": float(delay.iloc[best]),
            "delay_at_worst": float(delay.iloc[worst]),
        }
    return windows


def _alternative_ports(forecast: pd.DataFrame, threshold: float) -> Dict[str, Dict]:
    """For each port, the nearest lower-wait alternative on the same coast."""
    from src.utils import port_registry

    summaries = {}
    for port_id, group in forecast.groupby(PORT_ID):
        delay = pd.to_numeric(group.get("predicted_delay"), errors="coerce")
        delay = delay.fillna(pd.to_numeric(group["q50"], errors="coerce") * 0.2)
        summaries[str(port_id)] = float(delay.mean())

    out: Dict[str, Dict] = {}
    for port_id, own_delay in summaries.items():
        port = port_registry.resolve(port_id)
        if port is None:
            continue
        candidates = []
        for other_id, other_delay in summaries.items():
            if other_id == port_id:
                continue
            other = port_registry.resolve(other_id)
            if other is None or other.coast != port.coast:
                continue
            saving = own_delay - other_delay
            if saving > 0:
                candidates.append((saving, other))
        if not candidates:
            out[port_id] = {"saving_hours": 0.0, "port_name": ""}
            continue
        candidates.sort(key=lambda item: item[0], reverse=True)
        saving, best = candidates[0]
        out[port_id] = {"saving_hours": round(float(saving), 2),
                        "port_name": best.short, "port_id": best.model_id}
    return out


def high_risk_calendar(decisions: pd.DataFrame, prob_cut: float = 0.5
                       ) -> pd.DataFrame:
    """Per-port list of high-risk target dates (congestion probability >= cut)."""
    if decisions.empty:
        return decisions
    hi = decisions[decisions["congestion_probability"] >= prob_cut]
    columns = [PORT_ID, "target_date", "horizon_day", "congestion_probability",
               "port_entry_risk", "action_code", "expected_delay_saved_hours"]
    return (hi.sort_values([PORT_ID, "horizon_day"])
            [[c for c in columns if c in hi.columns]].reset_index(drop=True))
