"""Scenario propagation against the live forecast.

The Decision Room used to be the least defensible screen in the system: its API
returned a hardcoded ``baseCongestionDelta`` per scenario, multiplied by the
intensity slider. Every number a judge could see was a constant.

This module replaces that with an actual propagation. It takes the live
quantile forecast the pipeline produced, applies a typed shock through the
calibrated impact model and the measured lane-exposure graph, and reports the
*difference* between the two forecasts. Nothing is asserted:

    baseline        the live forecast for each port and horizon
    shock           the same forecast transformed by the impact model
    delta           shock minus baseline, per port and network-wide
    exposure        the port's measured lane exposure to the shocked chokepoint
    confidence      the forecast's own confidence, discounted by model
                    disagreement and by how much of the port's exposure the
                    scenario actually explains
    recommendation  re-run of the decision engine on the shocked forecast, so
                    the recommended action is derived, not written by hand

The propagation is a first-order elasticity model with coefficients documented
against real analogues in :mod:`src.decision.impact_model`. It is a decision-
support estimate, and the payload labels it as one.
"""

from __future__ import annotations

from typing import Dict, List, Optional

import numpy as np
import pandas as pd

from src.decision.decision_layer import build_decisions, prob_exceed
from src.decision.impact_model import market_impact, port_impact
from src.decision.scenario_catalog import ScenarioSpec, resolve
from src.ingestion.connectors.portwatch import CHOKEPOINTS, port_exposure
from src.utils import port_registry
from src.utils.config import PORT_ID
from src.utils.logging_utils import get_logger

log = get_logger(__name__)

CONGESTION_THRESHOLD = 50.0

#: Ports outside a local shock's scope still feel a small network effect --
#: diverted calls and shared inland capacity -- but far less than those in it.
OUT_OF_SCOPE_WEIGHT = 0.15

#: The exposure the impact model assumes when no chokepoint is named. Local
#: shocks rescale their severity against this so the scope weight governs.
GENERIC_EXPOSURE = 0.3


def _scope_weight(spec: ScenarioSpec, model_id: str) -> float:
    """How strongly this scenario reaches a given port, 0..1."""
    port = port_registry.resolve(model_id)
    if spec.scope == "chokepoint" and spec.chokepoint:
        return float(port_exposure(model_id).get(spec.chokepoint, 0.05))
    if spec.scope == "coast":
        if port is not None and port.coast in spec.coasts:
            return 1.0
        return OUT_OF_SCOPE_WEIGHT
    return 1.0


def _risk_level(value: float, upper: float) -> str:
    if value >= 70 or upper >= 80:
        return "severe"
    if value >= 55 or upper >= 65:
        return "high"
    if value >= 40:
        return "medium"
    return "normal"


def _apply_shock(forecast: pd.DataFrame, spec: ScenarioSpec,
                 intensity: float) -> tuple[pd.DataFrame, Dict[str, dict]]:
    """Return the shocked forecast plus the per-port impact record."""
    severity = float(np.clip(spec.default_severity * intensity, 0.0, 1.0))
    shocked = forecast.copy()
    impacts: Dict[str, dict] = {}

    for model_id in forecast[PORT_ID].unique():
        weight = _scope_weight(spec, str(model_id))
        if spec.scope == "chokepoint":
            # port_impact resolves lane exposure itself for chokepoint shocks.
            impact = port_impact(spec.shock_type, spec.chokepoint, severity,
                                 str(model_id))
        else:
            # For a local shock the scope weight *is* the exposure, so the
            # severity is rescaled to cancel the generic 0.3 the impact model
            # assumes when no chokepoint is named.
            effective = float(np.clip(severity * weight / GENERIC_EXPOSURE, 0.0, 1.0))
            impact = port_impact(spec.shock_type, None, effective, str(model_id))
        impacts[str(model_id)] = {
            "exposure": round(weight, 3),
            "congestion_uplift": impact.congestion_uplift,
            "delay_factor": impact.delay_factor,
            "throughput_factor": impact.throughput_factor,
            "extra_steaming_days": impact.extra_steaming_days,
        }

    def transform(row):
        impact = impacts.get(str(row[PORT_ID]))
        if impact is None:
            return row
        uplift = impact["congestion_uplift"]
        for column in ("predicted_congestion", "q10", "q50", "q90"):
            if column in row and pd.notna(row[column]):
                row[column] = float(np.clip(row[column] + uplift, 0, 100))
        if "predicted_delay" in row and pd.notna(row["predicted_delay"]):
            row["predicted_delay"] = float(row["predicted_delay"] * impact["delay_factor"])
        if "predicted_throughput" in row and pd.notna(row["predicted_throughput"]):
            row["predicted_throughput"] = float(
                row["predicted_throughput"] * impact["throughput_factor"])
        return row

    shocked = shocked.apply(transform, axis=1)
    return shocked, impacts


def _column(frame: pd.DataFrame, name: str, default: float) -> pd.Series:
    """Numeric column, or a constant Series when the forecast lacks it.

    ``DataFrame.get`` returns a scalar for a missing column, so calling a Series
    method on the result raises. A forecast produced by the GBM-only path has no
    ``model_disagreement``, and that must degrade rather than 500.
    """
    if name not in frame.columns:
        return pd.Series(default, index=frame.index, dtype=float)
    return pd.to_numeric(frame[name], errors="coerce").fillna(default)


def _port_summary(baseline: pd.DataFrame, shocked: pd.DataFrame,
                  impacts: Dict[str, dict]) -> List[dict]:
    """Per-port baseline vs shock, with every delta computed from the tables."""
    rows: List[dict] = []
    for model_id, base_group in baseline.groupby(PORT_ID):
        port = port_registry.resolve(str(model_id))
        shock_group = shocked[shocked[PORT_ID] == model_id]
        if shock_group.empty:
            continue

        base_congestion = float(base_group["predicted_congestion"].mean())
        shock_congestion = float(shock_group["predicted_congestion"].mean())
        base_delay = float(_column(base_group, "predicted_delay", np.nan).mean())
        shock_delay = float(_column(shock_group, "predicted_delay", np.nan).mean())
        base_throughput = float(
            _column(base_group, "predicted_throughput", np.nan).mean())
        shock_throughput = float(
            _column(shock_group, "predicted_throughput", np.nan).mean())

        base_prob = float(np.mean([prob_exceed(r.q10, r.q50, r.q90,
                                               CONGESTION_THRESHOLD)
                                   for r in base_group.itertuples()]))
        shock_prob = float(np.mean([prob_exceed(r.q10, r.q50, r.q90,
                                                CONGESTION_THRESHOLD)
                                    for r in shock_group.itertuples()]))

        disagreement = float(_column(base_group, "model_disagreement", 0.0).mean())
        forecast_confidence = float(
            _column(base_group, "confidence_score", 0.6).mean())
        impact = impacts.get(str(model_id), {})
        exposure = float(impact.get("exposure", 0.0))

        # Propagation confidence: how much we trust this port's shocked number.
        # It cannot exceed the forecast's own confidence, and it falls when the
        # models disagree or when little of the port's activity is explained by
        # the shocked lane.
        confidence = float(np.clip(
            forecast_confidence * (1.0 - 0.3 * disagreement)
            * (0.55 + 0.45 * min(exposure / 0.5, 1.0)), 0.05, 0.95))

        throughput_delta_pct = (
            100.0 * (shock_throughput - base_throughput) / base_throughput
            if base_throughput and not np.isnan(base_throughput) else None)

        rows.append({
            "portCode": port.locode if port else str(model_id),
            "modelId": str(model_id),
            "name": port.name if port else str(model_id),
            "coast": port.coast if port else None,
            "exposure": round(exposure, 3),
            "baselineCongestion": round(base_congestion, 1),
            "shockCongestion": round(shock_congestion, 1),
            "congestionDelta": round(shock_congestion - base_congestion, 1),
            "baselineDelayHours": round(base_delay, 1) if not np.isnan(base_delay) else None,
            "shockDelayHours": round(shock_delay, 1) if not np.isnan(shock_delay) else None,
            "delayDeltaHours": (round(shock_delay - base_delay, 1)
                                if not np.isnan(base_delay) and not np.isnan(shock_delay)
                                else None),
            "throughputDeltaPct": (round(throughput_delta_pct, 1)
                                   if throughput_delta_pct is not None else None),
            "baselineCongestionProbability": round(base_prob, 3),
            "shockCongestionProbability": round(shock_prob, 3),
            "probabilityDelta": round(shock_prob - base_prob, 3),
            "extraSteamingDays": impact.get("extra_steaming_days", 0.0),
            "riskLevel": _risk_level(shock_congestion,
                                     float(shock_group["q90"].mean())),
            "impactScore": int(round(min(99.0, max(0.0,
                                                   (shock_congestion - base_congestion) * 2.5
                                                   + shock_prob * 40)))),
            "confidence": round(confidence, 3),
            "modelDisagreement": round(disagreement, 3),
        })

    rows.sort(key=lambda row: row["impactScore"], reverse=True)
    return rows


def _chokepoint_impacts(spec: ScenarioSpec, intensity: float) -> List[dict]:
    """Chokepoint status under the scenario, keyed to the exposure graph."""
    severity = float(np.clip(spec.default_severity * intensity, 0.0, 1.0))
    rows = []
    for cid, meta in CHOKEPOINTS.items():
        if cid == "GOOD_HOPE":
            continue
        is_target = spec.chokepoint == cid
        level = ("severe" if is_target and severity >= 0.75 else
                 "high" if is_target else
                 "elevated" if spec.scope == "chokepoint" else "normal")
        rows.append({
            "code": cid,
            "name": meta["name"],
            "location": {"lat": meta["lat"], "lon": meta["lon"]},
            "riskLevel": level,
            "isShocked": is_target,
            "rerouteDays": meta.get("reroute_days", 0),
            "hasAlternative": not meta.get("no_alt", False),
        })
    return rows


def _route_impacts(port_rows: List[dict], spec: ScenarioSpec) -> List[dict]:
    """Coast-level exposure, aggregated from the per-port propagation."""
    routes = []
    for coast, label in (("west", "West coast corridor"),
                         ("east", "East coast corridor"),
                         ("south", "Southern gateway")):
        block = [row for row in port_rows if row.get("coast") == coast]
        if not block:
            continue
        delays = [row["delayDeltaHours"] for row in block
                  if row["delayDeltaHours"] is not None]
        routes.append({
            "name": label,
            "coast": coast,
            "ports": [row["portCode"] for row in block],
            "delayDeltaHours": round(float(np.mean(delays)), 1) if delays else None,
            "congestionDelta": round(float(np.mean(
                [row["congestionDelta"] for row in block])), 1),
            "riskLevel": max((row["riskLevel"] for row in block),
                             key=lambda level: ["normal", "medium", "high",
                                                "severe"].index(level)),
            "inScope": coast in spec.coasts,
        })
    return routes


def simulate_scenario(scenario_key: str,
                      intensity: float,
                      forecast: pd.DataFrame,
                      panel: Optional[pd.DataFrame] = None,
                      weather_now: Optional[pd.DataFrame] = None,
                      run_id: int = 0) -> dict:
    """Run one scenario against the live forecast and return the full payload."""
    spec = resolve(scenario_key)
    intensity = float(np.clip(intensity, 0.1, 3.0))

    if forecast is None or forecast.empty:
        raise ValueError("simulate_scenario requires a non-empty live forecast")

    baseline = forecast.copy()
    shocked, impacts = _apply_shock(baseline, spec, intensity)

    port_rows = _port_summary(baseline, shocked, impacts)
    severity = float(np.clip(spec.default_severity * intensity, 0.0, 1.0))
    market = market_impact(spec.shock_type, spec.chokepoint, severity)

    # Re-run the decision engine on the shocked forecast: the recommendation is
    # derived from the shocked distributions, not written for the scenario.
    shocked_decisions = build_decisions(shocked, weather_now, panel=panel)
    baseline_decisions = build_decisions(baseline, weather_now, panel=panel)

    recommendation = _recommendation(shocked_decisions, baseline_decisions,
                                     port_rows, spec, intensity)

    network_congestion_delta = round(float(np.mean(
        [row["congestionDelta"] for row in port_rows])), 2) if port_rows else 0.0
    delays = [row["delayDeltaHours"] for row in port_rows
              if row["delayDeltaHours"] is not None]
    network_delay_delta = round(float(np.mean(delays)), 2) if delays else 0.0
    throughputs = [row["throughputDeltaPct"] for row in port_rows
                   if row["throughputDeltaPct"] is not None]
    network_throughput_delta = round(float(np.mean(throughputs)), 2) if throughputs else 0.0

    in_scope = [row for row in port_rows if row["exposure"] >= 0.3]
    overall_confidence = (round(float(np.mean([row["confidence"] for row in in_scope])), 3)
                          if in_scope else
                          round(float(np.mean([row["confidence"] for row in port_rows])), 3)
                          if port_rows else 0.0)

    origin = pd.to_datetime(baseline["forecast_origin_date"], errors="coerce").max()
    baseline_model = (str(baseline["model"].iloc[0]) if "model" in baseline.columns
                      and not baseline.empty else "unknown")
    return {
        "scenarioKey": spec.key,
        "scenarioName": spec.name,
        "description": spec.description,
        "question": spec.question,
        "analogue": spec.analogue,
        "shockType": spec.shock_type,
        "scope": spec.scope,
        "chokepoint": spec.chokepoint,
        "intensity": round(intensity, 2),
        "severity": round(severity, 3),
        "durationDays": spec.duration_days,
        "runId": run_id,

        "forecastOrigin": None if pd.isna(origin) else origin.isoformat(),
        "baselineModel": baseline_model,
        "horizonDays": int(pd.to_numeric(baseline["horizon_day"],
                                         errors="coerce").max()),

        "congestionDelta": network_congestion_delta,
        "delayDeltaHours": network_delay_delta,
        "throughputDelta": network_throughput_delta,
        "freightDelta": market["freight_pct"],
        "oilDelta": market["oil_pct"],
        "riskLevel": _risk_level(
            float(np.mean([row["shockCongestion"] for row in port_rows]))
            if port_rows else 0.0, 0.0),
        "confidence": overall_confidence,

        "affectedPorts": port_rows,
        "routeImpacts": _route_impacts(port_rows, spec),
        "chokepointImpacts": _chokepoint_impacts(spec, intensity),
        "recommendation": recommendation,
        "propagation": _propagation_chain(spec, port_rows, market, recommendation),
        "method": ("Live quantile forecast transformed by a first-order impact "
                   "model over the measured lane-exposure graph. Deltas are the "
                   "difference between the two forecasts; no scenario outcome is "
                   "stored. This is a decision-support estimate, not a "
                   "prediction that the event will occur."),
    }


def _recommendation(shocked: pd.DataFrame, baseline: pd.DataFrame,
                    port_rows: List[dict], spec: ScenarioSpec,
                    intensity: float) -> dict:
    """The action the decision engine picks once the shock is applied."""
    if shocked.empty:
        return {"available": False,
                "reason": "No decisions could be derived from the shocked forecast."}

    focus_code = port_rows[0]["portCode"] if port_rows else None
    focus_model_id = port_rows[0]["modelId"] if port_rows else None

    block = shocked[shocked[PORT_ID] == focus_model_id] if focus_model_id else shocked
    if block.empty:
        block = shocked
    peak = block.sort_values("priority_score", ascending=False).iloc[0]

    base_block = baseline[baseline[PORT_ID] == focus_model_id] if focus_model_id else baseline
    base_action = (base_block.sort_values("priority_score", ascending=False)
                   .iloc[0]["action_code"] if not base_block.empty else None)

    changed = bool(base_action and base_action != peak["action_code"])
    delay_saved = float(peak.get("expected_delay_saved_hours", 0.0) or 0.0)

    return {
        "available": True,
        "id": f"REC-{spec.key}-{focus_code or 'NETWORK'}",
        "portCode": focus_code,
        "severity": str(peak.get("severity", "medium")),
        "action": str(peak.get("action_code", "MONITOR")),
        "title": str(peak.get("action_title", "Review operations")),
        "target": str(peak.get("action_target", focus_code or "network")),
        "instruction": str(peak.get("operational_adjustment", "")),
        "rationale": str(peak.get("reason", "")),
        "topDrivers": str(peak.get("top_drivers", "")),
        "expectedImpact": str(peak.get("expected_impact", "")),
        "expectedDelaySavedHours": round(delay_saved, 1),
        "alternativeAction": str(peak.get("alternative_action", "")),
        "confidence": round(float(peak.get("decision_confidence", 0.6)), 3),
        "uncertainty": round(float(peak.get("uncertainty", 0.0)), 3),
        "changedFromBaseline": changed,
        "baselineAction": base_action,
        "actionMix": (shocked["action_code"].value_counts().to_dict()
                      if "action_code" in shocked else {}),
    }


def _propagation_chain(spec: ScenarioSpec, port_rows: List[dict],
                       market: dict, recommendation: dict) -> List[dict]:
    """The causal chain the Decision Room renders, each step carrying its number."""
    top = port_rows[:3]
    chain = [{
        "step": "SHOCK",
        "label": spec.name,
        "detail": spec.description,
        "value": f"severity {spec.default_severity:.0%}",
    }]
    if spec.chokepoint:
        meta = CHOKEPOINTS.get(spec.chokepoint, {})
        chain.append({
            "step": "LANE",
            "label": meta.get("name", spec.chokepoint),
            "detail": ("No maritime bypass exists" if meta.get("no_alt")
                       else f"Reroute adds about {meta.get('reroute_days', 0)} "
                            "steaming days"),
            "value": f"freight {market['freight_pct']:+.1f}%",
        })
    else:
        chain.append({
            "step": "SCOPE",
            "label": ("Coast: " + ", ".join(spec.coasts)) if spec.coasts else "National",
            "detail": "Ports in scope absorb the shock directly.",
            "value": f"{len([p for p in port_rows if p['exposure'] >= 0.5])} ports in scope",
        })

    if top:
        chain.append({
            "step": "PORT EXPOSURE",
            "label": ", ".join(row["name"] for row in top),
            "detail": "Most exposed ports by computed impact score.",
            "value": " · ".join(f"{row['portCode']} {row['congestionDelta']:+.1f}"
                                for row in top),
        })
        delays = [row["delayDeltaHours"] for row in top
                  if row["delayDeltaHours"] is not None]
        if delays:
            chain.append({
                "step": "ETA",
                "label": "Expected berth wait",
                "detail": "Mean change in predicted wait across the horizon.",
                "value": f"{float(np.mean(delays)):+.1f}h",
            })

    if recommendation.get("available"):
        chain.append({
            "step": "ACTION",
            "label": recommendation["title"],
            "detail": recommendation["instruction"],
            "value": recommendation["target"],
        })
        saved = recommendation.get("expectedDelaySavedHours") or 0.0
        chain.append({
            "step": "EXPECTED BENEFIT",
            "label": "Delay avoided by acting",
            "detail": recommendation.get("expectedImpact", ""),
            "value": (f"{saved:.1f}h" if saved > 0
                      else "no delay saving claimed"),
        })
    return chain
