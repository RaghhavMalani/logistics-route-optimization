"""The robust decision policy: an intervention is recommended only when it
survives not knowing how long the disruption will last.

The expected-value ranking answers "which option scores best if the claim is
exactly right?". That is the wrong question for a closure claim, because the
one thing a claim never carries is its duration, and the benchmark said what
that costs: the slow-steam hedge lost to doing nothing on nine cases of twelve
when the closure ended before the claim did. The hedge paid certain hours to
remove an exposure that mostly did not materialise.

This module asks a different question. Every option's consequence is
evaluated under the one closure outcome model the product scores itself with
(:mod:`src.portwatch_os.decision.outcome`), at several stated durations:

    FIZZLE   the claim does not materialise; the water is open on arrival
    SHORT    the closure ends halfway to the claim horizon
    BASE     the closure ends at the claim horizon, as claimed
    LONG     the closure persists to twice the claim horizon

These are labelled stress horizons, not a distribution. No calibrated
duration distribution exists for a chokepoint claim, so none is invented and
none is weighted: the policy reports the regret of every option under every
horizon and decides by **minimax regret** -- the option whose worst regret
across the horizons is smallest -- with the current plan as a first-class
candidate. An intervention displaces the current plan only when

    its worst-case regret is lower than the plan's by more than the noise
    tolerance, it wins at least as many horizons as the plan, and it still
    does so when the queue model is switched off (model disagreement).

An irreversible intervention must additionally be justified by the claim as
stated (the BASE horizon), not by the long tail alone. Where the plan is kept
because the evidence is too weak, the answer is ``KEEP_CURRENT_PLAN`` with the
break-even closure length the intervention would need. Where the window
permits waiting for the next register refresh without foreclosing the
intervention, and the answer depends on the duration, the answer is
``WAIT_FOR_MORE_INFORMATION``: do nothing yet, re-evaluate when the next
observation lands, before the branch point closes.

The break-even is computed on a one-hour grid of closure lengths, so the
panel can say "the Cape wins only if the closure persists beyond 31 h" rather
than a confidence number nobody can act on.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Sequence, Tuple

from src.portwatch_os.decision.model import (
    ACT,
    DecisionOption,
    DecisionProblem,
    KEEP_CURRENT_PLAN,
    RECOMMENDATION_KINDS,
    VESSEL_ROUTING,
    WAIT_FOR_MORE_INFORMATION,
)
from src.portwatch_os.decision.outcome import (
    ClosureWindow,
    DEFAULT_QUEUE_MODEL,
    QUEUE_MODELS,
    closure_delay_hours,
    parse_instant,
)

#: The policies the engine can run. ``BALANCED`` is the incumbent expected-value
#: ranking; ``ROBUST`` is this module.
BALANCED_POLICY = "balanced-v1"
ROBUST_POLICY = "robust-v1"

#: Half an hour. The route geometry is non-navigational and hull timings are
#: declared to a tenth of an hour; a difference inside this is not a measured
#: advantage. Used as the minimax margin, the win tolerance and the break-even
#: tolerance alike so there is one figure to disagree with.
NOISE_TOLERANCE_HOURS = 0.5

#: The stress horizons, as multipliers of the remaining claim horizon. FIZZLE
#: is the claim not materialising and has no multiplier.
STRESS_HORIZONS: Tuple[Tuple[str, Optional[float], str], ...] = (
    ("FIZZLE", None, "the claim does not materialise: the water is open on arrival and no backlog forms"),
    ("SHORT", 0.5, "the closure ends halfway to the claim horizon"),
    ("BASE", 1.0, "the closure ends at the claim horizon, as claimed"),
    ("LONG", 2.0, "the closure persists to twice the claim horizon"),
)

#: How far the break-even grid runs, as a multiple of the remaining claim
#: horizon, and its step. Covers every stress horizon with room past LONG.
BREAK_EVEN_SPAN = 3.0
BREAK_EVEN_STEP_HOURS = 1.0
BREAK_EVEN_MIN_SPAN_HOURS = 24.0

#: Reversibility classes an option can carry.
REVERSIBLE_OPEN = "OPEN"              # the current plan: every other option stays available
REVERSIBLE_HIGH = "HIGH"              # a speed change: restored at any time
REVERSIBLE_UNTIL_BRANCH = "UNTIL_BRANCH"  # a diversion: reversible until the branch point
REVERSIBLE_PARTIAL = "PARTIAL"        # a destination change: rebound at sea, consequences unmodelled
IRREVERSIBLE = "IRREVERSIBLE"

#: Below this window the option is treated as closing before a refresh lands.
MINIMUM_WINDOW_HOURS = 0.5


# --------------------------------------------------------------------------
# results
# --------------------------------------------------------------------------


@dataclass
class GateCheck:
    name: str
    passed: bool
    blocking: bool
    detail: str
    basis: str

    def to_dict(self) -> Dict[str, Any]:
        return {"name": self.name, "passed": self.passed, "blocking": self.blocking,
                "detail": self.detail, "basis": self.basis}


@dataclass
class StressScenario:
    label: str
    multiplier: Optional[float]
    window: ClosureWindow
    description: str
    queue_model: str

    @property
    def closure_from_now_hours(self) -> Optional[float]:
        return None if self.multiplier is None else round(self._remaining * self.multiplier, 1)

    _remaining: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {"label": self.label, "multiplier": self.multiplier, "description": self.description,
                "queueModel": self.queue_model, "closureFromNowHours": self.closure_from_now_hours,
                "window": self.window.to_dict()}


@dataclass
class RobustAssessment:
    """Everything the robust policy computed, and what it concluded."""

    applicable: bool
    policy: str = ROBUST_POLICY
    kind: str = KEEP_CURRENT_PLAN
    option_id: Optional[str] = None
    #: An intervention that would win under longer closures but was not
    #: recommended; what the operator is told to watch.
    contender_id: Optional[str] = None
    #: For WAIT: the option to take if the claim still stands at re-evaluation.
    provisional_option_id: Optional[str] = None
    scenarios: List[StressScenario] = field(default_factory=list)
    #: option id -> scenario label -> {delay, regret, how}
    table: Dict[str, Dict[str, Dict[str, Any]]] = field(default_factory=dict)
    #: option id -> summary figures
    summary: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    picks: Dict[str, Optional[str]] = field(default_factory=dict)
    checks: List[GateCheck] = field(default_factory=list)
    duration_confidence: Dict[str, Any] = field(default_factory=dict)
    information: Dict[str, Any] = field(default_factory=dict)
    queue_model: Dict[str, Any] = field(default_factory=dict)
    not_modelled: Dict[str, str] = field(default_factory=dict)
    why: str = ""
    statement: str = ""
    notes: List[str] = field(default_factory=list)

    @property
    def failed_blocking(self) -> List[GateCheck]:
        return [c for c in self.checks if c.blocking and not c.passed]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "applicable": self.applicable,
            "policy": self.policy,
            "kind": self.kind,
            "optionId": self.option_id,
            "contenderId": self.contender_id,
            "provisionalOptionId": self.provisional_option_id,
            "scenarios": [s.to_dict() for s in self.scenarios],
            "table": self.table,
            "summary": self.summary,
            "picks": self.picks,
            "checks": [c.to_dict() for c in self.checks],
            "failedBlocking": [c.name for c in self.failed_blocking],
            "durationConfidence": self.duration_confidence,
            "information": self.information,
            "queueModel": self.queue_model,
            "notModelled": self.not_modelled,
            "why": self.why,
            "statement": self.statement,
            "notes": self.notes,
            "tolerance": {"hours": NOISE_TOLERANCE_HOURS,
                          "basis": "half an hour: non-navigational route geometry and timings declared to 0.1 h"},
        }


# --------------------------------------------------------------------------
# reading the problem
# --------------------------------------------------------------------------


def _clock(problem: DecisionProblem) -> Optional[datetime]:
    return parse_instant(problem.at) if problem.at else None


def _claim_window(problem: DecisionProblem) -> Tuple[Optional[datetime], Optional[datetime]]:
    event = problem.evidence.get("event") or {}
    start = event.get("claimFrom")
    end = event.get("claimLapsesAt")
    return (parse_instant(start) if start else None, parse_instant(end) if end else None)


def _risk_kind(problem: DecisionProblem) -> str:
    return str((problem.evidence.get("closureModel") or {}).get("riskKind") or "chokepoint")


def _hours_to_risk(problem: DecisionProblem) -> Optional[float]:
    attrs = (problem.evidence.get("exposure") or {}).get("attrs") or {}
    value = attrs.get("hours_to_risk_area")
    return None if value is None else float(value)


def _closes_in(option: DecisionOption) -> Optional[float]:
    value = option.provenance.get("closesInHours")
    return None if value is None else float(value)


def reversibility_of(option: DecisionOption, problem: DecisionProblem) -> Dict[str, Any]:
    """How far the option can be undone once taken, and until when."""
    closes = _closes_in(option)
    if option.is_baseline:
        window = _hours_to_risk(problem)
        return {"class": REVERSIBLE_OPEN, "closesInHours": None if window is None else round(window, 1),
                "detail": "every other option stays available until its own branch point; the plan itself "
                          "commits when the hull enters the exposed water"}
    if option.action == "SLOW_STEAM":
        return {"class": REVERSIBLE_HIGH, "closesInHours": None if closes is None else round(closes, 1),
                "detail": "speed can be restored at any time; only the hours already lost are sunk"}
    if option.action in ("REROUTE", "SPEED_UP"):
        if closes is not None and closes <= 0:
            return {"class": IRREVERSIBLE, "closesInHours": round(closes, 1),
                    "detail": "the branch point has passed; the detour is committed"}
        return {"class": REVERSIBLE_UNTIL_BRANCH, "closesInHours": None if closes is None else round(closes, 1),
                "detail": (f"reversible until the branch point in {closes:.0f} h; past it the detour is committed"
                           if closes is not None else "reversible until the branch point")}
    if option.action == "CHANGE_DESTINATION_PORT":
        return {"class": REVERSIBLE_PARTIAL, "closesInHours": None if closes is None else round(closes, 1),
                "detail": "the destination can be rebound at sea; the consignments' onward carriage is not modelled"}
    return {"class": REVERSIBLE_PARTIAL, "closesInHours": None if closes is None else round(closes, 1),
            "detail": "reversibility not classified for this action"}


# --------------------------------------------------------------------------
# scenarios and the regret table
# --------------------------------------------------------------------------


def stress_scenarios(problem: DecisionProblem, *, queue_model: str = DEFAULT_QUEUE_MODEL) -> List[StressScenario]:
    """The labelled horizons for this problem, or an empty list where the claim
    carries no horizon to stress."""
    clock = _clock(problem)
    claim_from, claim_end = _claim_window(problem)
    if clock is None or claim_end is None:
        return []
    remaining = max(0.0, (claim_end - clock).total_seconds() / 3600.0)
    blocked_from = claim_from if claim_from is not None and claim_from <= clock else clock
    drain = float(QUEUE_MODELS[queue_model]["drainFraction"])
    out: List[StressScenario] = []
    for label, multiplier, description in STRESS_HORIZONS:
        if multiplier is None:
            window = ClosureWindow(blocked_from, blocked_from, blocked_from)
        else:
            window = ClosureWindow.with_drain(blocked_from, clock + timedelta(hours=remaining * multiplier),
                                              drain_fraction=drain)
        scenario = StressScenario(label, multiplier, window, description, queue_model)
        scenario._remaining = remaining
        out.append(scenario)
    return out


def _candidates(problem: DecisionProblem) -> Tuple[List[DecisionOption], Dict[str, str]]:
    """Feasible options the closure model covers, and why the rest are left out.

    The current plan is always a candidate. Any other option must be feasible,
    not rejected by the Critic, and measurable on the frontier's objectives
    (an option whose delay is unknown is not recommended on a figure that
    ignores what is unknown); a change of destination under a chokepoint
    closure still transits the closed water and the model does not cover it.
    """
    frontier = problem.frontier
    kind = _risk_kind(problem)
    out: List[DecisionOption] = []
    left: Dict[str, str] = {}
    for option in problem.options:
        if option.is_baseline:
            if option.feasible and option.evaluation is not None:
                out.append(option)
            else:
                left[option.option_id] = "the current plan is not feasible"
            continue
        if not option.feasible or option.evaluation is None:
            left[option.option_id] = "rejected by a hard constraint"
            continue
        if option.critic and option.critic.get("verdict") == "REJECT":
            left[option.option_id] = "rejected by the Critic"
            continue
        if frontier is not None and option.option_id in frontier.incomparable:
            left[option.option_id] = "not measurable on " + ", ".join(frontier.incomparable[option.option_id])
            continue
        # An option dominated on the expected objectives stays a candidate here:
        # the dominance rests on the expected figures, and the whole point of
        # this lens is that those figures assume the claim's duration. The
        # Critic says so when such an option is recommended.
        if option.action == "CHANGE_DESTINATION_PORT" and kind != "port_closure":
            left[option.option_id] = ("still transits the closed chokepoint and lands the cargo elsewhere; "
                                      "the closure model does not cover it")
            continue
        out.append(option)
    return out, left


def regret_table(
    candidates: Sequence[DecisionOption],
    scenarios: Sequence[StressScenario],
    *,
    clock: datetime,
) -> Tuple[Dict[str, Dict[str, Dict[str, Any]]], Dict[str, str]]:
    """Every candidate under every scenario: delay, regret against the
    scenario's best candidate, and the arithmetic."""
    table: Dict[str, Dict[str, Dict[str, Any]]] = {}
    unmodelled: Dict[str, str] = {}
    for scenario in scenarios:
        rows: Dict[str, Dict[str, Any]] = {}
        for option in candidates:
            row = closure_delay_hours(option, scenario.window, clock=clock)
            if row is None:
                unmodelled[option.option_id] = "the closure model returns no figure for this option"
                continue
            rows[option.option_id] = row
        if not rows:
            continue
        best = min(r["hours"] for r in rows.values())
        for option_id, row in rows.items():
            table.setdefault(option_id, {})[scenario.label] = {
                "delay": row["hours"], "regret": round(row["hours"] - best, 1), "how": row["how"],
            }
    return table, unmodelled


def summarise(
    table: Dict[str, Dict[str, Dict[str, Any]]],
    baseline_id: Optional[str],
    scenario_labels: Sequence[str],
) -> Dict[str, Dict[str, Any]]:
    """Per option: worst-case regret, unweighted mean regret, horizons won,
    advantage over the current plan, and the robustness margin."""
    out: Dict[str, Dict[str, Any]] = {}
    baseline_rows = table.get(baseline_id or "", {})
    baseline_worst = max((r["regret"] for r in baseline_rows.values()), default=None)
    for option_id, rows in table.items():
        regrets = [rows[label]["regret"] for label in scenario_labels if label in rows]
        if not regrets:
            continue
        worst = max(regrets)
        wins = [label for label in scenario_labels if label in rows and rows[label]["regret"] <= NOISE_TOLERANCE_HOURS]
        advantage = [baseline_rows[label]["delay"] - rows[label]["delay"]
                     for label in scenario_labels if label in rows and label in baseline_rows]
        out[option_id] = {
            "worstCaseRegret": round(worst, 1),
            "worstCaseScenario": max((label for label in scenario_labels if label in rows),
                                     key=lambda label: rows[label]["regret"]),
            "meanRegret": round(sum(regrets) / len(regrets), 1),
            "meanRegretBasis": "unweighted mean over labelled stress horizons; no calibrated duration distribution",
            "wins": len(wins),
            "winningScenarios": wins,
            "scenarios": len(regrets),
            "baselineAdvantageHours": {
                label: round(baseline_rows[label]["delay"] - rows[label]["delay"], 1)
                for label in scenario_labels if label in rows and label in baseline_rows
            },
            "meanBaselineAdvantageHours": round(sum(advantage) / len(advantage), 1) if advantage else None,
            "robustnessMargin": None if baseline_worst is None else round(baseline_worst - worst, 1),
        }
    return out


# --------------------------------------------------------------------------
# break-even
# --------------------------------------------------------------------------


def break_even(
    option: DecisionOption,
    baseline: DecisionOption,
    problem: DecisionProblem,
    *,
    queue_model: str = DEFAULT_QUEUE_MODEL,
) -> Dict[str, Any]:
    """Closure lengths from now at which the option beats the current plan.

    A one-hour grid from "reopens now" to three times the remaining claim
    horizon (at least a day). Reports the first hour the option wins, the
    last consecutive hour it keeps winning (``None`` when it still wins at
    the end of the grid), and the share of the grid it wins.
    """
    clock = _clock(problem)
    claim_from, claim_end = _claim_window(problem)
    if clock is None or claim_end is None:
        return {"available": False, "reason": "the claim carries no horizon to evaluate against"}
    remaining = max(0.0, (claim_end - clock).total_seconds() / 3600.0)
    span = max(BREAK_EVEN_MIN_SPAN_HOURS, remaining * BREAK_EVEN_SPAN)
    blocked_from = claim_from if claim_from is not None and claim_from <= clock else clock
    drain = float(QUEUE_MODELS[queue_model]["drainFraction"])
    grid: List[float] = []
    hours = 0.0
    while hours <= span + 1e-9:
        grid.append(round(hours, 1))
        hours += BREAK_EVEN_STEP_HOURS
    wins: List[float] = []
    points: List[Dict[str, Any]] = []
    for d in grid:
        window = ClosureWindow.with_drain(blocked_from, clock + timedelta(hours=d), drain_fraction=drain)
        mine = closure_delay_hours(option, window, clock=clock)
        theirs = closure_delay_hours(baseline, window, clock=clock)
        if mine is None or theirs is None:
            return {"available": False, "reason": "the closure model returns no figure for one of the options"}
        won = mine["hours"] < theirs["hours"] - NOISE_TOLERANCE_HOURS
        if won:
            wins.append(d)
        points.append({"closureFromNowHours": d, "option": mine["hours"], "baseline": theirs["hours"]})
    if not wins:
        return {"available": True, "winsFromHours": None, "winsUntilHours": None, "winningShare": 0.0,
                "gridSpanHours": round(span, 1), "gridStepHours": BREAK_EVEN_STEP_HOURS,
                "statement": f"does not beat the current plan at any closure length up to {span:.0f} h from now",
                "curve": _thin(points)}
    first = wins[0]
    last: Optional[float] = first
    for d in wins[1:]:
        if abs(d - (last + BREAK_EVEN_STEP_HOURS)) > 1e-9:
            break
        last = d
    open_ended = last is not None and abs(last - grid[-1]) < 1e-9
    statement = (
        f"beats the current plan only if the closure persists beyond {first:.0f} h from now"
        + ("" if open_ended else f" and ends before {last:.0f} h")
        if first > 0 else
        "beats the current plan at every closure length" if open_ended else
        f"beats the current plan only if the closure ends before {last:.0f} h from now"
    )
    return {"available": True, "winsFromHours": first, "winsUntilHours": None if open_ended else last,
            "winningShare": round(len(wins) / len(grid), 3), "gridSpanHours": round(span, 1),
            "gridStepHours": BREAK_EVEN_STEP_HOURS, "statement": statement, "curve": _thin(points)}


def _thin(points: List[Dict[str, Any]], keep: int = 25) -> List[Dict[str, Any]]:
    if len(points) <= keep:
        return points
    step = max(1, len(points) // keep)
    thinned = points[::step]
    if thinned[-1] is not points[-1]:
        thinned.append(points[-1])
    return thinned


# --------------------------------------------------------------------------
# the gate
# --------------------------------------------------------------------------


def _pick_minimax(summary: Dict[str, Dict[str, Any]], baseline_id: Optional[str]) -> Optional[str]:
    if not summary:
        return None
    return min(summary, key=lambda oid: (summary[oid]["worstCaseRegret"], 0 if oid == baseline_id else 1,
                                         summary[oid]["meanRegret"], oid))


def _pick_robust(summary: Dict[str, Dict[str, Any]], baseline_id: Optional[str]) -> Optional[str]:
    if not summary:
        return None
    return min(summary, key=lambda oid: (-summary[oid]["wins"], summary[oid]["worstCaseRegret"],
                                         summary[oid]["meanRegret"], 0 if oid == baseline_id else 1, oid))


def _next_observation_hours() -> Tuple[float, str]:
    """When the next event-register refresh is due, from the freshness policy."""
    try:
        from src.portwatch_os.freshness.jobs import EVENTS_POLICY

        hours = EVENTS_POLICY.fresh_for.total_seconds() / 3600.0
        return hours, f"event register refresh SLA ({EVENTS_POLICY.provider}); fresh_for {hours:.0f} h"
    except Exception:  # noqa: BLE001 - the policy module is optional here
        return 6.0, "event register refresh SLA (default 6 h)"


def _scenario_sensitive(table: Dict[str, Dict[str, Dict[str, Any]]], labels: Sequence[str]) -> Tuple[bool, Dict[str, str]]:
    """Whether which option is best depends on the horizon."""
    best_by_label: Dict[str, str] = {}
    for label in labels:
        rows = {oid: rows[label] for oid, rows in table.items() if label in rows}
        if rows:
            best_by_label[label] = min(rows, key=lambda oid: (rows[oid]["delay"], oid))
    return len(set(best_by_label.values())) > 1, best_by_label


def assess(problem: DecisionProblem, *, expected_best: Optional[str]) -> RobustAssessment:
    """Run the robust policy on an evaluated, criticised, ranked problem."""
    baseline = problem.baseline
    if problem.domain != VESSEL_ROUTING:
        return _not_applicable(problem, expected_best,
                               "no duration-uncertainty model for this domain; the expected-value ranking decides "
                               "and the current plan wins ties")
    clock = _clock(problem)
    scenarios = stress_scenarios(problem)
    if baseline is None or not baseline.feasible or clock is None or not scenarios:
        return _not_applicable(problem, expected_best,
                               "the claim carries no horizon, or the current plan could not be evaluated")

    candidates, left_out = _candidates(problem)
    labels = [s.label for s in scenarios]
    table, unmodelled = regret_table(candidates, scenarios, clock=clock)
    left_out.update(unmodelled)
    summary = summarise(table, baseline.option_id, labels)
    for option_id in summary:
        option = problem.option(option_id)
        if option is None:
            continue
        summary[option_id]["reversibility"] = reversibility_of(option, problem)
        if option.is_baseline:
            summary[option_id]["breakEven"] = None
        else:
            summary[option_id]["breakEven"] = break_even(option, baseline, problem)

    if baseline.option_id not in summary:
        return _not_applicable(problem, expected_best, "the closure model returns no figure for the current plan")

    minimax = _pick_minimax(summary, baseline.option_id)
    robust_best = _pick_robust(summary, baseline.option_id)
    sensitive, best_by_label = _scenario_sensitive(table, labels)
    next_obs, next_obs_basis = _next_observation_hours()

    assessment = RobustAssessment(
        applicable=True, scenarios=scenarios, table=table, summary=summary,
        picks={"EXPECTED_BEST": expected_best, "ROBUST_BEST": robust_best, "LOWEST_WORST_CASE_REGRET": minimax},
        duration_confidence=_duration_confidence(problem),
        queue_model={"name": DEFAULT_QUEUE_MODEL, **QUEUE_MODELS[DEFAULT_QUEUE_MODEL],
                     "alternative": {"name": "NONE", **QUEUE_MODELS["NONE"]}},
        not_modelled=left_out,
    )
    assessment.information = {
        "scenarioSensitive": sensitive,
        "bestByScenario": best_by_label,
        "nextObservationHours": round(next_obs, 1),
        "nextObservationBasis": next_obs_basis,
        "informationValueHoursUpperBound": summary[baseline.option_id]["worstCaseRegret"],
        "informationValueBasis": "the current plan's worst-case regret across the horizons: the most that knowing "
                                 "the duration could save; an upper bound, unweighted",
    }

    # -- the contender: the intervention that wins the longest horizons -------
    contender = None
    for label in reversed(labels):
        best = best_by_label.get(label)
        if best is not None and best != baseline.option_id:
            contender = best
            break

    if minimax == baseline.option_id or minimax is None:
        assessment.contender_id = contender
        assessment.checks = _checks_for(problem, contender, baseline, summary, table, labels, assessment) if contender else []
        _conclude_keep_or_wait(problem, assessment, baseline, contender, sensitive, next_obs)
        return assessment

    candidate = problem.option(minimax)
    assessment.checks = _checks_for(problem, minimax, baseline, summary, table, labels, assessment)
    if assessment.failed_blocking:
        assessment.contender_id = minimax
        _conclude_keep_or_wait(problem, assessment, baseline, minimax, sensitive, next_obs)
        return assessment

    # -- the intervention clears the gate --------------------------------------
    reversibility = summary[minimax]["reversibility"]
    wait_hours = _wait_feasible(candidate, next_obs)
    if reversibility["class"] in (REVERSIBLE_UNTIL_BRANCH, IRREVERSIBLE, REVERSIBLE_PARTIAL) and sensitive and wait_hours is not None:
        # The intervention is justified, but committing it now buys nothing
        # the branch point does not still allow later, and the next refresh
        # may withdraw the claim. Preserve the option; name it as provisional.
        assessment.kind = WAIT_FOR_MORE_INFORMATION
        assessment.option_id = baseline.option_id
        assessment.provisional_option_id = minimax
        assessment.contender_id = minimax
        assessment.information.update({"reevaluateInHours": wait_hours,
                                       "branchPointInHours": reversibility.get("closesInHours")})
        closes = reversibility.get("closesInHours")
        available = f"for {closes:.0f} h" if closes is not None else "with no stated branch point"
        assessment.why = (
            f"{candidate.label} clears the robust gate but is {reversibility['class'].lower().replace('_', ' ')}: "
            f"it stays available {available} and the register refreshes in "
            f"{next_obs:.0f} h, so nothing is lost by re-evaluating first."
        )
        assessment.statement = (
            f"Do nothing yet. Re-evaluate in {wait_hours:.0f} h when the event register refreshes; "
            f"{candidate.label.lower()} remains available {available}. "
            f"If the claim still stands, take it."
        )
        return assessment

    assessment.kind = ACT
    assessment.option_id = minimax
    assessment.why = _why_act(candidate, baseline, summary, labels)
    assessment.statement = f"{candidate.label} for {problem.subject_label}. {assessment.why}"
    return assessment


def _wait_feasible(option: DecisionOption, next_obs: float) -> Optional[float]:
    """Hours to wait before re-evaluating, or None when waiting forecloses the option."""
    closes = _closes_in(option)
    if closes is None:
        return round(next_obs, 1)
    if closes - MINIMUM_WINDOW_HOURS < next_obs:
        return None
    return round(next_obs, 1)


def _conclude_keep_or_wait(
    problem: DecisionProblem,
    assessment: RobustAssessment,
    baseline: DecisionOption,
    contender_id: Optional[str],
    sensitive: bool,
    next_obs: float,
) -> None:
    assessment.option_id = baseline.option_id
    contender = problem.option(contender_id) if contender_id else None
    summary = assessment.summary
    base_summary = summary[baseline.option_id]
    horizons = base_summary["scenarios"]
    if contender is None or not sensitive:
        assessment.kind = KEEP_CURRENT_PLAN
        assessment.why = (f"The current plan wins {base_summary['wins']}/{horizons} stress horizons; no intervention "
                          "beats it under any of them.")
        assessment.statement = f"Keep the current plan for {problem.subject_label}. {assessment.why}"
        return
    be = summary.get(contender.option_id, {}).get("breakEven") or {}
    failed = ", ".join(c.name for c in assessment.failed_blocking) or "none"
    reason = (be.get("statement") or "does not beat the current plan under the stress horizons")
    value = assessment.information.get("informationValueHoursUpperBound") or 0.0
    wait_hours = _wait_feasible(contender, next_obs)
    if wait_hours is not None and value > NOISE_TOLERANCE_HOURS:
        assessment.kind = WAIT_FOR_MORE_INFORMATION
        assessment.information.update({"reevaluateInHours": wait_hours,
                                       "branchPointInHours": (summary[contender.option_id]["reversibility"]
                                                              .get("closesInHours"))})
        assessment.why = (
            f"{contender.label} {reason} (duration confidence {assessment.duration_confidence.get('label')}); "
            f"the current plan wins {base_summary['wins']}/{horizons} stress horizons and knowing the duration is "
            f"worth up to {value:.0f} h. Failed gate checks: {failed}."
        )
        closes = summary[contender.option_id]["reversibility"].get("closesInHours")
        assessment.statement = (
            f"Do nothing yet. Re-evaluate in {wait_hours:.0f} h when the event register refreshes"
            + (f"; {contender.label.lower()} remains available for {closes:.0f} h" if closes is not None else "")
            + f". {contender.label} {reason}."
        )
        return
    assessment.kind = KEEP_CURRENT_PLAN
    assessment.why = (
        f"{contender.label} {reason} (duration confidence {assessment.duration_confidence.get('label')}); "
        f"the current plan wins {base_summary['wins']}/{horizons} stress horizons. Failed gate checks: {failed}."
    )
    assessment.statement = f"Keep the current plan for {problem.subject_label}. {assessment.why}"


def _why_act(candidate: DecisionOption, baseline: DecisionOption, summary: Dict[str, Dict[str, Any]], labels: Sequence[str]) -> str:
    mine, theirs = summary[candidate.option_id], summary[baseline.option_id]
    be = mine.get("breakEven") or {}
    return (
        f"Worst-case regret {mine['worstCaseRegret']:.0f} h against the current plan's {theirs['worstCaseRegret']:.0f} h; "
        f"wins {mine['wins']}/{mine['scenarios']} stress horizons against the plan's {theirs['wins']}/{theirs['scenarios']}"
        + (f"; {be['statement']}" if be.get("statement") else "") + "."
    )


def _duration_confidence(problem: DecisionProblem) -> Dict[str, Any]:
    seed = ((problem.evidence.get("event") or {}).get("seed") or {})
    attrs = seed.get("attrs") or {}
    if attrs.get("assumed"):
        return {"label": "ASSUMED", "basis": "an operator-assumed closure with a 72 h window; its duration is the assumption"}
    calibrated = bool(attrs.get("calibrated"))
    return {
        "label": "LOW / UNCALIBRATED",
        "basis": ("the claim's probability is calibrated against resolved outcomes but its duration is not; "
                  if calibrated else
                  "neither the claim's probability nor its duration is calibrated; ")
                 + "the stress horizons are labelled multiples of the claim horizon, not a distribution",
        "claimProbabilityCalibrated": calibrated,
        "claimConfidence": seed.get("confidence"),
    }


def _checks_for(
    problem: DecisionProblem,
    candidate_id: str,
    baseline: DecisionOption,
    summary: Dict[str, Dict[str, Any]],
    table: Dict[str, Dict[str, Dict[str, Any]]],
    labels: Sequence[str],
    assessment: RobustAssessment,
) -> List[GateCheck]:
    candidate = problem.option(candidate_id)
    mine, theirs = summary[candidate_id], summary[baseline.option_id]
    checks: List[GateCheck] = []

    margin = theirs["worstCaseRegret"] - mine["worstCaseRegret"]
    checks.append(GateCheck(
        "worst_case_regret", margin > NOISE_TOLERANCE_HOURS, True,
        f"worst-case regret {mine['worstCaseRegret']:.1f} h ({mine['worstCaseScenario']}) against the current plan's "
        f"{theirs['worstCaseRegret']:.1f} h ({theirs['worstCaseScenario']}); margin {margin:+.1f} h against a "
        f"{NOISE_TOLERANCE_HOURS:.1f} h tolerance",
        basis="minimax regret over FIZZLE/SHORT/BASE/LONG under the recorded queue model",
    ))
    checks.append(GateCheck(
        "scenario_wins", mine["wins"] >= theirs["wins"], True,
        f"wins {mine['wins']}/{mine['scenarios']} horizons ({', '.join(mine['winningScenarios']) or 'none'}) against "
        f"the current plan's {theirs['wins']}/{theirs['scenarios']}",
        basis="horizons where the option's regret is within tolerance of the best",
    ))

    # Model disagreement: the same comparison with no queue at all.
    clock = _clock(problem)
    alt_scenarios = stress_scenarios(problem, queue_model="NONE")
    candidates = [o for o in (baseline, candidate) if o is not None]
    alt_table, _ = regret_table(candidates, alt_scenarios, clock=clock) if clock else ({}, {})
    alt_summary = summarise(alt_table, baseline.option_id, [s.label for s in alt_scenarios])
    if candidate_id in alt_summary and baseline.option_id in alt_summary:
        alt_margin = alt_summary[baseline.option_id]["worstCaseRegret"] - alt_summary[candidate_id]["worstCaseRegret"]
        checks.append(GateCheck(
            "queue_model_agreement", alt_margin > NOISE_TOLERANCE_HOURS, True,
            f"with no queue the margin is {alt_margin:+.1f} h (recorded queue: {margin:+.1f} h); "
            + ("both models agree" if alt_margin > NOISE_TOLERANCE_HOURS else
               "the intervention rests on the queue assumption alone"),
            basis="QUEUE_MODELS.NONE against QUEUE_MODELS.RECORDED",
        ))
    else:
        checks.append(GateCheck("queue_model_agreement", False, True,
                                "the no-queue model returns no figure for one of the options",
                                basis="QUEUE_MODELS.NONE"))

    reversibility = mine.get("reversibility") or {}
    irreversible = reversibility.get("class") in (REVERSIBLE_UNTIL_BRANCH, IRREVERSIBLE)
    base_regret = (table.get(candidate_id, {}).get("BASE") or {}).get("regret")
    checks.append(GateCheck(
        "claim_as_stated", base_regret is not None and base_regret <= NOISE_TOLERANCE_HOURS, irreversible,
        (f"regret {base_regret:.1f} h if the closure ends exactly at the claim horizon; "
         f"{'blocking because the option is ' + reversibility.get('class', '').lower().replace('_', ' ') if irreversible else 'advisory: the option is ' + reversibility.get('class', '').lower().replace('_', ' ') + ' reversible'}")
        if base_regret is not None else "no BASE horizon figure",
        basis="table[BASE].regret; an irreversible move must be justified by the claim as stated, not the tail alone",
    ))

    weather = candidate.measure("weather") if candidate else None
    if candidate is not None and candidate.action in ("REROUTE", "SPEED_UP"):
        checks.append(GateCheck(
            "passage_weather", bool(weather is not None and weather.available), False,
            (f"worst sampled wave {weather.value:.1f} m on the alternative passage" if weather is not None and weather.available
             else "the alternative passage was not weather-checked: " + ((weather.unknown_because if weather else None) or "no weather measure")),
            basis="objectives.weather",
        ))
    eta = candidate.measure("eta") if candidate else None
    checks.append(GateCheck(
        "eta_certain", bool(eta is not None and eta.available and (eta.attrs.get("certain") or (eta.confidence or 0) >= 0.8)), False,
        (f"the option's delay is {'certain' if eta is not None and eta.available and eta.attrs.get('certain') else 'an expected value'} "
         f"(confidence {eta.confidence})" if eta is not None and eta.available else "no ETA figure"),
        basis="objectives.eta.attrs.certain",
    ))
    checks.append(GateCheck(
        "claim_calibrated", bool(assessment.duration_confidence.get("claimProbabilityCalibrated")), False,
        assessment.duration_confidence.get("basis", ""),
        basis="evidence.event.seed.attrs.calibrated",
    ))
    return checks


def _not_applicable(problem: DecisionProblem, expected_best: Optional[str], reason: str) -> RobustAssessment:
    baseline = problem.baseline
    chosen = expected_best
    kind = KEEP_CURRENT_PLAN if (chosen is None or (baseline is not None and chosen == baseline.option_id)) else ACT
    option = problem.option(chosen) if chosen else None
    assessment = RobustAssessment(applicable=False, kind=kind, option_id=chosen,
                                  picks={"EXPECTED_BEST": expected_best, "ROBUST_BEST": None,
                                         "LOWEST_WORST_CASE_REGRET": None},
                                  why=reason)
    if option is None:
        assessment.statement = f"No feasible option for {problem.subject_label}."
    elif kind == KEEP_CURRENT_PLAN:
        assessment.statement = f"Keep the current plan for {problem.subject_label}."
    else:
        assessment.statement = f"{option.label} for {problem.subject_label}."
    assessment.notes.append(reason)
    return assessment


__all__ = [
    "ACT",
    "BALANCED_POLICY",
    "BREAK_EVEN_SPAN",
    "GateCheck",
    "IRREVERSIBLE",
    "KEEP_CURRENT_PLAN",
    "MINIMUM_WINDOW_HOURS",
    "NOISE_TOLERANCE_HOURS",
    "RECOMMENDATION_KINDS",
    "REVERSIBLE_HIGH",
    "REVERSIBLE_OPEN",
    "REVERSIBLE_PARTIAL",
    "REVERSIBLE_UNTIL_BRANCH",
    "ROBUST_POLICY",
    "RobustAssessment",
    "STRESS_HORIZONS",
    "StressScenario",
    "WAIT_FOR_MORE_INFORMATION",
    "assess",
    "break_even",
    "regret_table",
    "reversibility_of",
    "stress_scenarios",
    "summarise",
]
