"""Dated approach-window comparison from public forecasts and stated limits.

This bounded demo tests an assumed arrival gate, not a validated port closure
model. No hazard location is turned into a delay. The normal decision object,
Critic, ledger, human review and advisory boundary carry the result.
"""
from datetime import timedelta
import hashlib
import json
from src.portwatch_os.intelligence.current_environment import bundle, instant, finite
from src.portwatch_os.intelligence.operational_quality import freeze_activity_context
from src.portwatch_os.decision.model import (
    DecisionProblem, DecisionOption, DecisionEvaluation, DecisionObjective,
    ConstraintResult, OBJECTIVES, VESSEL_ROUTING, FEASIBLE, known, unknown,
)
from src.portwatch_os.decision.actions import KEEP_PLAN, DELAY_ARRIVAL, CATALOGUE
from src.utils import port_registry


def build_arrival_problem(vessel, request, actor, state, at):
    port = port_registry.resolve(vessel.destination_port)
    data = bundle(port)
    source = data["sources"]["surface"]
    if source["status"] != "CURRENT":
        raise ValueError("Current surface forecast required; a stale receipt cannot drive this comparison")
    earliest = instant(vessel.eta)
    planned = instant(request.get("plannedArrival") or vessel.eta)
    if earliest <= at or planned < earliest or planned > earliest+timedelta(hours=72):
        raise ValueError("Demo arrival must be future, no earlier than the voyage ETA, and within 72h of it")
    gust_limit = request.get("maxGustKn", 15)
    visibility_limit = request.get("minVisibilityM", 5000)
    if not finite(gust_limit) or not 3 <= gust_limit <= 60 or not finite(visibility_limit) or not 0 <= visibility_limit <= 10000:
        raise ValueError("Assumed gust and visibility limits are outside the comparison envelope")
    rows = [r for r in data["hourly"] if instant(r["validAt"]) >= planned][:48]
    if len(rows) < 2 or instant(rows[0]["validAt"]) - planned > timedelta(hours=1):
        raise ValueError("The planned arrival is outside the current forecast's valid horizon")
    def clear(row):
        return finite(row["wind_gusts_10m"]) and finite(row["visibility"]) and row["wind_gusts_10m"] <= gust_limit and row["visibility"] >= visibility_limit
    index = next((i for i in range(len(rows)-1) if clear(rows[i]) and clear(rows[i+1])
                  and instant(rows[i+1]["validAt"])-instant(rows[i]["validAt"]) == timedelta(hours=1)), None)
    if index is None:
        raise ValueError("No two consecutive clear forecast hours in the next 48h; no bounded arrival alternative")
    safe_at = max(planned, instant(rows[index]["validAt"]))
    wait = (safe_at-planned).total_seconds()/3600
    frozen = {"evidenceVersion": "current-weather-approach-v2", "portCode": port.locode,
        "voyageId": vessel.vessel_id, "source": source["source"],
        "snapshotId": source["snapshotId"], "responseSha256": source["responseSha256"],
        "issuedAt": source["issuedAt"], "observedAt": None, "availableAt": source["availableAt"],
        "earliestVoyageArrival": earliest.isoformat(), "plannedArrival": planned.isoformat(),
        "firstClearApproach": safe_at.isoformat(), "noWeatherGateWaitHours": 0,
        "forecastGateWaitHours": round(wait,4), "consumedForecasts": rows[:index+2],
        "assumptions": {"kind":"assumed_approach_limits","source": "OPERATOR_DEMO_ASSUMPTION", "maxGustKn": gust_limit,
            "minVisibilityM": visibility_limit, "consecutiveClearHours": 2,
            "scope": "Port approach only; not an official JNPA limit, berth guarantee or bridge navigation instruction."},
        "hazardSnapshotId": data["sources"]["hazards"].get("snapshotId"),
        "hazardRelationship": "Regional context only; no hazard-to-delay formula used.",
        # Context is frozen for inspection only, after all hourly gate calculations.
        # It is not a continuation dependency, a delay input or a daily correction.
        "activityContext": freeze_activity_context(port.locode, now=at),
        "meaning": "Current public forecast applied to a fictional voyage under explicit operating assumptions. Forecast-driven simulated wait, not observed delay."}
    from src.portwatch_os.sandbox import current_sandbox
    scoped = current_sandbox.get()
    if scoped is not None:
        from src.portwatch_os.decision.episodes import ensure_episode
        owned = next(v for v in scoped.world["fleet"] if v["id"] == vessel.vessel_id)
        frozen["operationalEpisode"] = ensure_episode(scoped, owned)
    frozen["evidenceId"] = hashlib.sha256(json.dumps(frozen,sort_keys=True).encode()).hexdigest()
    decision_id = "dec-arrival-" + hashlib.sha256((frozen["evidenceId"]+actor.role+at.isoformat()).encode()).hexdigest()[:20]
    options = []
    for name, action, arrival, anchorage_wait, baseline in (
        ("Continue planned arrival; wait for the assumed gate", KEEP_PLAN, planned, wait, True),
        ("Propose the first forecast-clear arrival window", DELAY_ARRIVAL, safe_at, 0., False)):
        shift = (safe_at-earliest).total_seconds()/3600
        option = DecisionOption(option_id=decision_id+("-continue" if baseline else "-window"), action=action,
            label=name, actor=actor.role, is_baseline=baseline, status=FEASIBLE,
            params={"arrivalAt": arrival.isoformat(), "holdHours": (arrival-planned).total_seconds()/3600},
            constraints=[ConstraintResult("future_arrival", "Voyage timing is feasible", True, True,
                "No arrival is earlier than the declared fictional voyage ETA", basis="evidence.currentEnvironment.earliestVoyageArrival")],
            assumptions=[frozen["assumptions"]], provenance={"source": "CURRENT_FORECAST_DEMO", "evidenceId": frozen["evidenceId"]},
            evaluation=DecisionEvaluation(objectives={
                "eta": known(shift,"hours",basis="First forecast-clear approach minus declared voyage ETA; both options reach the same approach gate",confidence=None),
                "port_wait": known(anchorage_wait,"hours",basis="Hourly forecast under the assumed gust/visibility gate; baseline waits at anchor, later arrival avoids this assumed wait",confidence=None),
                "weather": known(rows[index].get("wave_height"),"m",basis="Marine forecast at the clear approach hour",confidence=None) if finite(rows[index].get("wave_height")) else unknown("m","Marine valid hour unavailable; waves are not part of this assumed approach gate"),
                "risk": unknown("risk","No calibrated closure probability or operational risk model for this weather gate"),
                "fuel": unknown("index","Fuel consequences of holding versus delayed approach are not modelled"),
                "cost": unknown("money","No validated rate or cost model for this approach assumption")},
                derived={"destinationPort": port.locode, "arrivalAt": arrival.isoformat(), "approachClearAt": safe_at.isoformat(),
                    "arrivalShiftHours": (arrival-earliest).total_seconds()/3600, "holdHours": (arrival-planned).total_seconds()/3600,
                    "weatherGustKn": rows[0]["wind_gusts_10m"] if baseline else rows[index]["wind_gusts_10m"]},
                notes=[frozen["meaning"]], computed_at=at.isoformat()),
            timeline=[{"at": arrival.isoformat(), "kind": "arrival", "label": "Requested demo arrival"},
                      {"at": safe_at.isoformat(), "kind": "weather", "label": "First forecast-clear approach under assumed limits"}])
        options.append(option)
    problem = DecisionProblem(decision_id=decision_id,created_at=at.isoformat(),domain=VESSEL_ROUTING,
        world_revision=state.summary()["revision"],world_state_id=state.state_id+":"+frozen["evidenceId"],
        subject_type="vessel",subject_id=vessel.vessel_id,subject_label=vessel.name,actor=actor,at=at.isoformat(),
        objectives=[DecisionObjective("eta","Clear approach shift","hours","min","Time to a clear approach under the assumed forecast gate"), OBJECTIVES["port_wait"]],
        available_actions=[{**CATALOGUE[a].to_dict(),"availability":{"status":"AVAILABLE","reason":"Bounded current forecast approach-window comparison"}} for a in (KEEP_PLAN,DELAY_ARRIVAL)],
        options=options,baseline_option_id=options[0].option_id,
        evidence={"currentEnvironment":frozen,"frontierObjectives":["eta","port_wait"],
                  "subject":{"source":"FICTIONAL_DEMO"}},
        headline=f"{vessel.name}: current forecast versus an assumed approach gate at {port.locode}",
        do_nothing_statement=f"Without this weather gate: 0h assumed weather wait. With the consumed forecast: {wait:.1f}h at anchor, clear at {safe_at.isoformat()}.",
        notes=[frozen["meaning"],"No berth assignment or whole-voyage weather safety claim is made."])
    if request.get("passagePlan") is not None:
        from .passage import extend_arrival_problem
        return extend_arrival_problem(problem, request["passagePlan"], data, at=at)
    return problem
