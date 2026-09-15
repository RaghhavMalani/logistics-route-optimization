"""The mission scorecard: what PortWatch knew, predicted and recommended,
against what happened.

After the reveal the outcome is applied to *every* option the engine
evaluated, so the question "would another option have been better?" is
answered from the same facts as "was the one we recommended any good?".
The realised model is stated in full below and is used for scoring only --
never for the decision, which was made before the future was readable.

    knew          the claim as it stood at the clock: status, severity,
                  confidence, claim horizon
    predicted     the baseline's residual risk and expected shift; each
                  option's predicted ETA shift
    recommended   the engine's option and its Critic verdict
    selected      what the operator chose on the replay
    happened      reopening and backlog clearance, from the sources
    forecast error   claim horizon against the blocked duration; the baseline
                  risk against whether the strait was closed on arrival
    regret        realised delay of the option taken against the realised best
    learned       the statements the numbers support
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from src.portwatch_os.decision.model import DecisionOption, DecisionProblem
from src.portwatch_os.decision.outcome import ClosureWindow, closure_delay_hours, destination_of, parse_instant
from src.portwatch_os.missions.model import Mission, Outcome


def _parse(value: str) -> datetime:
    return parse_instant(value)


REALISED_MODEL = (
    "A hull that reaches the closed canal or port waits until it reopens, then takes its turn in a queue "
    "drained linearly in arrival order between the reopening and the stated backlog-clearance bound. "
    "A hull arriving after the reopening but before the backlog cleared waits the remaining share of "
    "the drain. A hull on the Cape routing takes its certain detour; the Cape was open. A hull that lands "
    "at another port takes the passage difference the routing geometry gives, floored at zero; onward "
    "carriage of its consignments to the booked port is not modelled and is said so. Weather and port "
    "congestion beyond the stated closure are not part of the realised model."
)


_destination_of = destination_of


def realised_delay_hours(
    option: DecisionOption,
    problem: DecisionProblem,
    outcome: Outcome,
    *,
    clock: datetime,
) -> Optional[Dict[str, Any]]:
    """Hours the option actually cost, under the stated realised model.

    The physics is :func:`closure_delay_hours`, the one closure outcome model
    the decision policy also evaluates under; what the reveal adds is the
    window itself -- the reopening and the backlog clearance the sources
    state -- and, for an event that acts on ports, which port's window the
    option lands in. A diversion to a port the outcome records as closed has
    no realised figure: the model does not cover a hull landing into a
    second closure.
    """
    subject = _destination_of(option, problem) if outcome.closures else None
    if option.action == "CHANGE_DESTINATION_PORT":
        if not outcome.closures or option.params.get("portCode") in outcome.closures:
            return None
    stated = outcome.closure_for(subject)
    window = ClosureWindow(
        blocked_from=_parse(stated["closedFrom"]), reopened_at=_parse(stated["reopenedAt"]),
        cleared_at=_parse(stated["backlogClearedBound"].split(" ")[0]),
    )
    row = closure_delay_hours(option, window, clock=clock)
    if row is not None and option.action in ("REROUTE", "SPEED_UP"):
        row = {**row, "how": "certain detour on the alternative routing; the Cape was open"}
    return row


def scorecard(mission: Mission, problem: DecisionProblem, *, chosen_option_id: Optional[str]) -> Dict[str, Any]:
    outcome = mission.outcome
    clock = _parse(problem.at) if problem.at else mission.start
    knew = mission.claim_at(clock)
    baseline = problem.baseline
    recommended = problem.recommendation.option_id if problem.recommendation else None

    realised: Dict[str, Dict[str, Any]] = {}
    for option in problem.options:
        row = realised_delay_hours(option, problem, outcome, clock=clock)
        if row is not None:
            eta = option.measure("eta")
            row["predicted"] = None if eta is None or not eta.available else round(eta.value, 1)
            row["status"] = option.status
            row["label"] = option.label
            realised[option.option_id] = row

    feasible_realised = {oid: r for oid, r in realised.items() if problem.option(oid) and problem.option(oid).feasible}
    best_id = min(feasible_realised, key=lambda oid: feasible_realised[oid]["hours"]) if feasible_realised else None
    chosen_row = realised.get(chosen_option_id or "")
    regret = None if chosen_row is None or best_id is None else round(chosen_row["hours"] - feasible_realised[best_id]["hours"], 1)

    # -- forecast error ---------------------------------------------------------------
    claim_end = clock + timedelta(hours=mission.claim_horizon_hours)
    subject_window = outcome.closure_for(problem.subject_id and _destination_of(baseline, problem) if baseline else None) \
        if outcome.closures else outcome.closure_for(None)
    reopened = _parse(subject_window["reopenedAt"])
    persistence_error = round((reopened - claim_end).total_seconds() / 3600.0, 1)
    baseline_risk = baseline.measure("risk") if baseline else None
    arrival_hours = (baseline.evaluation.derived.get("hoursToChokepoint") if baseline and baseline.evaluation else None)
    closed_on_arrival = None
    brier = None
    if arrival_hours is not None:
        arrival = clock + timedelta(hours=float(arrival_hours))
        closed_on_arrival = arrival < reopened
        if baseline_risk is not None and baseline_risk.available:
            brier = round((baseline_risk.value - (1.0 if closed_on_arrival else 0.0)) ** 2, 4)

    learned: List[str] = []
    place = "port" if mission.subject_kind == "port" else "strait"
    if persistence_error > 0:
        learned.append(f"The {mission.claim_horizon_hours:.0f} h claim horizon understated the closure by "
                       f"{persistence_error:.0f} h; persistence beyond a {mission.subject_kind} claim needs its own model.")
    elif persistence_error < 0:
        learned.append(f"The {mission.claim_horizon_hours:.0f} h claim horizon overstated the closure by "
                       f"{-persistence_error:.0f} h; the {place} reopened before the claim lapsed.")
    if closed_on_arrival is not None and baseline_risk is not None and baseline_risk.available:
        learned.append(
            f"The baseline exposure {baseline_risk.value:.2f} scored a Brier of {brier} against a {place} that was "
            f"{'closed' if closed_on_arrival else 'open'} on arrival."
        )
    if best_id is not None and recommended is not None:
        if best_id == recommended:
            learned.append(f"The recommendation ({recommended}) was the realised best; regret 0.")
        elif recommended in realised:
            learned.append(f"{best_id} would have cost {feasible_realised[best_id]['hours']:.0f} h against the "
                           f"recommended {recommended}'s {realised[recommended]['hours']:.0f} h.")
        else:
            learned.append(f"{best_id} was the realised best; the recommended {recommended} has no realised "
                           "figure under the stated model.")
    for oid, row in realised.items():
        if row.get("predicted") is not None:
            error = row["hours"] - row["predicted"]
            if abs(error) >= 6.0:
                learned.append(f"{oid}: predicted {row['predicted']:.0f} h, realised {row['hours']:.0f} h ({error:+.0f} h).")

    observed_for_learning: Dict[str, Any] = {
        "optionOutcomes": {oid: {"eta": row["hours"]} for oid, row in realised.items()},
        "incident": 1.0 if closed_on_arrival else 0.0,
    }
    if chosen_row is not None:
        observed_for_learning["eta"] = chosen_row["hours"]

    return {
        "missionId": mission.mission_id,
        "decisionId": problem.decision_id,
        "subject": problem.subject_label,
        "clock": clock.isoformat(),
        "knew": {**knew, "claimHorizonHours": mission.claim_horizon_hours,
                 "visibleObservations": len(mission.visible(clock))},
        "predicted": {
            "baselineRisk": None if baseline_risk is None or not baseline_risk.available else round(baseline_risk.value, 3),
            "baselineExpectedShiftHours": (
                None if baseline is None or baseline.measure("eta") is None or not baseline.measure("eta").available
                else round(baseline.measure("eta").value, 1)
            ),
            "options": {oid: row.get("predicted") for oid, row in realised.items()},
        },
        "recommended": {
            "optionId": recommended,
            "critic": None if problem.recommendation is None else (problem.recommendation.critic or {}).get("verdict"),
            "statement": None if problem.recommendation is None else problem.recommendation.statement,
        },
        "selected": chosen_option_id,
        "happened": outcome.to_dict(),
        "forecastError": {
            "claimHorizonHours": mission.claim_horizon_hours,
            "blockedHours": round((reopened - _parse(subject_window["closedFrom"])).total_seconds() / 3600.0, 1),
            "subject": None if not outcome.closures or baseline is None else _destination_of(baseline, problem),
            "persistenceErrorHours": persistence_error,
            "closedOnArrival": closed_on_arrival,
            "brier": brier,
        },
        "realised": realised,
        "realisedBest": best_id,
        "regretHours": regret,
        "rankingCorrect": None if best_id is None or recommended is None else best_id == recommended,
        "wouldAnotherOptionHaveBeenBetter": (
            None if best_id is None or chosen_option_id is None else best_id != chosen_option_id
        ),
        "learned": learned,
        "realisedModel": REALISED_MODEL,
        "observedForLearning": observed_for_learning,
    }


__all__ = ["REALISED_MODEL", "realised_delay_hours", "scorecard"]
