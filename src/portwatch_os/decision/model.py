"""The decision object model: one shape for every "what should I do?".

A vessel routing choice, a berth allocation and a transshipment connection are
three different physics and one identical question. Each has a subject, an
actor who is entitled to act, a window before the choice closes, a set of
options of which exactly one is "change nothing", hard constraints that make
some options impossible, objectives on which the rest are compared, and a
recommendation somebody has to approve before it becomes an action. Modelling
them as one object is what lets a single Critic, a single ledger and a single
learning pass cover all three -- and what stops the product growing three
optimisers whose answers cannot be laid side by side.

Four rules the dataclasses below enforce rather than describe:

*   **Every problem is pinned to an immutable world revision.** A decision is a
    claim about the world as it was when the options were computed. If the
    world moves on, the problem says so; it is never silently recomputed.
*   **A baseline is a real option.** "Continue the current plan" is evaluated
    through the same simulator as every alternative, so "what happens if we
    do nothing" is a computed answer and never a hand-written number.
*   **Infeasible is not a score.** An option that fails a hard constraint is
    ``REJECTED`` and carries the constraint that rejected it. It is still shown
    -- an operator has to be able to see that the obvious move is impossible,
    and why -- but it takes no part in ranking.
*   **Unknown is not zero.** Every objective is a :class:`Measure` that either
    holds a value with its unit, confidence and basis, or holds the reason it
    could not be computed. Nothing downstream may treat an absent measure as
    a favourable one.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional, Sequence, Tuple

# --------------------------------------------------------------------------
# vocabulary
# --------------------------------------------------------------------------

#: Domains. The physics differs; the object does not.
VESSEL_ROUTING = "VESSEL_ROUTING"
PORT_BERTHING = "PORT_BERTHING"
CARGO_CONNECTION = "CARGO_CONNECTION"
DOMAINS: Tuple[str, ...] = (VESSEL_ROUTING, PORT_BERTHING, CARGO_CONNECTION)

#: Who can act. Matches the workspace roles, plus the terminal operator that
#: the port twin's crane and yard decisions actually belong to.
SHIPPING_COMPANY = "SHIPPING_COMPANY"
PORT_AUTHORITY = "PORT_AUTHORITY"
VESSEL_OPERATOR = "VESSEL_OPERATOR"
TERMINAL_OPERATOR = "TERMINAL_OPERATOR"
NATIONAL_ADMIN = "NATIONAL_ADMIN"
ACTORS: Tuple[str, ...] = (
    SHIPPING_COMPANY, PORT_AUTHORITY, VESSEL_OPERATOR, TERMINAL_OPERATOR, NATIONAL_ADMIN,
)

#: Whether an action can even be considered here. Decided before any
#: constraint runs: an action the simulator cannot evaluate is not an option
#: that failed, it is an option that was never on the table.
AVAILABLE = "AVAILABLE"
UNAVAILABLE = "UNAVAILABLE"
UNSUPPORTED = "UNSUPPORTED"
INSUFFICIENT_DATA = "INSUFFICIENT_DATA"
AVAILABILITY: Tuple[str, ...] = (AVAILABLE, UNAVAILABLE, UNSUPPORTED, INSUFFICIENT_DATA)

#: What became of an option once it was evaluated.
FEASIBLE = "FEASIBLE"
REJECTED = "REJECTED"
NOT_EVALUATED = "NOT_EVALUATED"
OPTION_STATUSES: Tuple[str, ...] = (FEASIBLE, REJECTED, NOT_EVALUATED)

#: Objective direction.
MINIMISE = "min"
MAXIMISE = "max"

#: The lifecycle a decision moves through. Computing is not deciding, and
#: approving is not acting; every step here is a distinct recorded state so
#: the ledger can say which of them actually happened.
COMPUTED = "COMPUTED"
REVIEWED = "REVIEWED"
APPROVED = "APPROVED"
PROPOSED = "PROPOSED"
ISSUED = "ISSUED"
ACCEPTED = "ACCEPTED"
DECLINED = "DECLINED"
OBSERVED = "OBSERVED"
WORKFLOW_STATES: Tuple[str, ...] = (
    COMPUTED, REVIEWED, APPROVED, PROPOSED, ISSUED, ACCEPTED, DECLINED, OBSERVED,
)


class DecisionError(ValueError):
    """A problem, option or transition that the model cannot hold, and why."""


# --------------------------------------------------------------------------
# measures
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class Measure:
    """One objective's value for one option -- or the reason there is none.

    ``basis`` names the computation: a transfer rule, a branch id, a
    simulator, a route sample. It is what the Critic and the evidence panel
    read, and it is required whenever a value is present: a number with no
    basis is an assertion, and this product does not ship assertions.
    """

    value: Optional[float]
    unit: str
    confidence: Optional[float] = None
    basis: str = ""
    unknown_because: Optional[str] = None
    #: Detail a computation wants to carry to the reader; never used in
    #: arithmetic.
    attrs: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.value is not None and not self.basis:
            raise DecisionError(f"a measure of {self.unit} with a value needs a basis")
        if self.value is None and not self.unknown_because:
            raise DecisionError(
                f"a measure of {self.unit} without a value must say why it is unknown"
            )

    @property
    def available(self) -> bool:
        return self.value is not None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "value": None if self.value is None else round(self.value, 4),
            "unit": self.unit,
            "confidence": None if self.confidence is None else round(self.confidence, 3),
            "basis": self.basis,
            "available": self.available,
            "unknownBecause": self.unknown_because,
            "attrs": self.attrs,
        }


def known(value: float, unit: str, *, basis: str, confidence: Optional[float] = None,
          **attrs: Any) -> Measure:
    return Measure(float(value), unit, confidence, basis, None, dict(attrs))


def unknown(unit: str, because: str, **attrs: Any) -> Measure:
    return Measure(None, unit, None, "", because, dict(attrs))


# --------------------------------------------------------------------------
# objectives
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class DecisionObjective:
    """One dimension options are compared on. Never collapsed prematurely."""

    key: str
    label: str
    unit: str
    direction: str = MINIMISE
    description: str = ""

    def better(self, a: float, b: float) -> bool:
        """Whether ``a`` is strictly better than ``b`` on this objective."""
        return a < b if self.direction == MINIMISE else a > b

    def to_dict(self) -> Dict[str, Any]:
        return {"key": self.key, "label": self.label, "unit": self.unit,
                "direction": self.direction, "description": self.description}


#: The catalogue of objectives the engine knows how to compute. A domain
#: selects the subset it can actually measure; an objective it cannot
#: measure is absent from the problem rather than present and zero.
OBJECTIVES: Dict[str, DecisionObjective] = {
    o.key: o for o in [
        DecisionObjective("eta", "ETA shift", "hours", MINIMISE,
                          "Expected arrival shift against the current plan."),
        DecisionObjective("delay", "Delay", "hours", MINIMISE,
                          "Hours added to the subject's own schedule."),
        DecisionObjective("distance", "Route distance", "nm", MINIMISE,
                          "Distance still to run on the option's routing."),
        DecisionObjective("fuel", "Fuel", "index", MINIMISE,
                          "Fuel burn relative to the current plan (1.0 = baseline)."),
        DecisionObjective("weather", "Weather exposure", "m", MINIMISE,
                          "Worst significant wave height sampled along the passage."),
        DecisionObjective("wave_hours", "Rough-sea hours", "hours", MINIMISE,
                          "Hours the passage spends in seas above the rough threshold."),
        DecisionObjective("storm", "Storm exposure", "risk", MINIMISE,
                          "Probability-like exposure to a modelled storm cell."),
        DecisionObjective("risk", "Chokepoint risk", "risk", MINIMISE,
                          "Residual exposure at the threatened water under this option."),
        DecisionObjective("port_wait", "Port wait", "hours", MINIMISE,
                          "Mean waiting time at anchor across the affected calls."),
        DecisionObjective("berth_utilisation", "Berth utilisation", "ratio", MAXIMISE,
                          "Share of berths working over the horizon."),
        DecisionObjective("yard_pressure", "Yard pressure", "ratio", MINIMISE,
                          "Projected yard pressure at the destination."),
        DecisionObjective("dwell", "Cargo dwell", "hours", MINIMISE,
                          "Hours the consignment sits in the yard before it sails."),
        DecisionObjective("missed_connection", "Missed-connection risk", "teu", MINIMISE,
                          "TEU whose onward connection is at risk."),
        DecisionObjective("emissions", "Emissions", "index", MINIMISE,
                          "CO2 relative to the current plan; proportional to fuel burn."),
        DecisionObjective("cost", "Financial cost", "money", MINIMISE,
                          "Total expected cost where a defensible cost basis exists."),
        DecisionObjective("uncertainty", "Uncertainty", "ratio", MINIMISE,
                          "One minus the weakest confidence in the option's evaluation."),
        DecisionObjective("turnaround", "Turnaround", "hours", MINIMISE,
                          "Mean time from arrival to departure."),
        DecisionObjective("crane_utilisation", "Crane utilisation", "ratio", MAXIMISE,
                          "Share of crane capacity working over the horizon."),
        DecisionObjective("missed_departures", "Missed departures", "count", MINIMISE,
                          "Calls that sail after their latest departure."),
        DecisionObjective("slack", "Connection slack", "hours", MAXIMISE,
                          "Hours between the cargo being ready and loading closing."),
        DecisionObjective("handling", "Handling", "hours", MINIMISE,
                          "Crane and yard hours the transfer consumes."),
        DecisionObjective("sailing", "Sailing", "hours", MINIMISE,
                          "Hour the consignment actually leaves on its connection."),
    ]
}


# --------------------------------------------------------------------------
# constraints
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class ConstraintResult:
    """One constraint checked against one option."""

    key: str
    label: str
    passed: bool
    hard: bool
    detail: str
    #: The computation or datum the check read.
    basis: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {"key": self.key, "label": self.label, "passed": self.passed,
                "hard": self.hard, "detail": self.detail, "basis": self.basis}


@dataclass(frozen=True)
class Availability:
    status: str
    reason: str = ""

    def __post_init__(self) -> None:
        if self.status not in AVAILABILITY:
            raise DecisionError(f"{self.status!r} is not an availability")
        if self.status != AVAILABLE and not self.reason:
            raise DecisionError(f"an action marked {self.status} must say why")

    @property
    def available(self) -> bool:
        return self.status == AVAILABLE

    def to_dict(self) -> Dict[str, Any]:
        return {"status": self.status, "reason": self.reason}


# --------------------------------------------------------------------------
# actor
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class DecisionActor:
    """Who this problem is framed for, and therefore which actions it may hold."""

    role: str
    organisation: Optional[str] = None
    port_code: Optional[str] = None
    vessel_ids: Tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if self.role not in ACTORS:
            raise DecisionError(f"{self.role!r} is not an actor that can hold a decision")

    def to_dict(self) -> Dict[str, Any]:
        return {"role": self.role, "organisation": self.organisation,
                "portCode": self.port_code, "vesselIds": list(self.vessel_ids)}


# --------------------------------------------------------------------------
# evaluation
# --------------------------------------------------------------------------


@dataclass
class DecisionEvaluation:
    """What one option does, on every dimension the domain can measure."""

    objectives: Dict[str, Measure] = field(default_factory=dict)
    #: The cascade this option's consequences were read from: reached
    #: subjects with their quantities, keyed by node key.
    consequences: List[Dict[str, Any]] = field(default_factory=list)
    #: Domain-specific derived state: the new ETA, the new berth plan, the
    #: connection plan. Shown, never ranked on directly.
    derived: Dict[str, Any] = field(default_factory=dict)
    financial: Optional[Dict[str, Any]] = None
    branch_id: Optional[str] = None
    notes: List[str] = field(default_factory=list)
    computed_at: Optional[str] = None

    def measure(self, key: str) -> Optional[Measure]:
        return self.objectives.get(key)

    @property
    def weakest_confidence(self) -> Optional[float]:
        found = [m.confidence for m in self.objectives.values()
                 if m.available and m.confidence is not None]
        return min(found) if found else None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "objectives": {k: m.to_dict() for k, m in self.objectives.items()},
            "consequences": self.consequences,
            "derived": self.derived,
            "financial": self.financial,
            "branchId": self.branch_id,
            "notes": self.notes,
            "computedAt": self.computed_at,
            "weakestConfidence": (
                None if self.weakest_confidence is None else round(self.weakest_confidence, 3)
            ),
        }


# --------------------------------------------------------------------------
# option
# --------------------------------------------------------------------------


@dataclass
class DecisionOption:
    """One thing the actor could do, and everything computed about it."""

    option_id: str
    action: str
    label: str
    actor: str
    params: Dict[str, Any] = field(default_factory=dict)
    availability: Availability = field(default_factory=lambda: Availability(AVAILABLE))
    constraints: List[ConstraintResult] = field(default_factory=list)
    status: str = NOT_EVALUATED
    evaluation: Optional[DecisionEvaluation] = None
    is_baseline: bool = False
    #: The assumptions the option's branch applied, in the branch's words.
    assumptions: List[Dict[str, Any]] = field(default_factory=list)
    provenance: Dict[str, Any] = field(default_factory=dict)
    critic: Optional[Dict[str, Any]] = None
    #: Route geometry the map draws, as [lat, lon] pairs, where the option
    #: has one. Non-navigational; the payload says so.
    geometry: Optional[List[List[float]]] = None
    #: Timeline marks the option produces: arrival, deadline, weather crossings.
    timeline: List[Dict[str, Any]] = field(default_factory=list)

    @property
    def feasible(self) -> bool:
        return self.status == FEASIBLE

    @property
    def rejected_by(self) -> List[ConstraintResult]:
        return [c for c in self.constraints if c.hard and not c.passed]

    def measure(self, key: str) -> Optional[Measure]:
        return None if self.evaluation is None else self.evaluation.measure(key)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "optionId": self.option_id,
            "action": self.action,
            "label": self.label,
            "actor": self.actor,
            "params": self.params,
            "availability": self.availability.to_dict(),
            "constraints": [c.to_dict() for c in self.constraints],
            "rejectedBy": [c.to_dict() for c in self.rejected_by],
            "status": self.status,
            "feasible": self.feasible,
            "isBaseline": self.is_baseline,
            "evaluation": None if self.evaluation is None else self.evaluation.to_dict(),
            "assumptions": self.assumptions,
            "provenance": self.provenance,
            "critic": self.critic,
            "geometry": self.geometry,
            "timeline": self.timeline,
        }


# --------------------------------------------------------------------------
# frontier and recommendation
# --------------------------------------------------------------------------


@dataclass
class DecisionFrontier:
    """The nondominated options over a chosen set of objectives."""

    objectives: List[str]
    nondominated: List[str]
    #: option id -> the option that dominates it.
    dominated: Dict[str, str] = field(default_factory=dict)
    #: option id -> the objectives it could not be compared on.
    incomparable: Dict[str, List[str]] = field(default_factory=dict)
    #: Labelled picks: FASTEST, LOWEST_RISK, ... -> option id, where the
    #: objective behind the label is actually measured.
    picks: Dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "objectives": self.objectives,
            "nondominated": self.nondominated,
            "dominated": self.dominated,
            "incomparable": self.incomparable,
            "picks": self.picks,
        }


@dataclass
class DecisionRecommendation:
    option_id: str
    actor: str
    #: How the ranking was reached, in numbers: weights and normalised scores.
    ranking_basis: Dict[str, Any] = field(default_factory=dict)
    #: Objective-by-objective comparison against the baseline.
    against_baseline: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    critic: Optional[Dict[str, Any]] = None
    expected_avoidable_cost: Optional[Dict[str, Any]] = None
    statement: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "optionId": self.option_id,
            "actor": self.actor,
            "rankingBasis": self.ranking_basis,
            "againstBaseline": self.against_baseline,
            "critic": self.critic,
            "expectedAvoidableCost": self.expected_avoidable_cost,
            "statement": self.statement,
        }


# --------------------------------------------------------------------------
# the problem
# --------------------------------------------------------------------------


@dataclass
class DecisionProblem:
    """One "what should I do?", pinned to one world revision."""

    decision_id: str
    created_at: str
    domain: str
    world_revision: Dict[str, Any]
    world_state_id: str
    subject_type: str
    subject_id: str
    subject_label: str
    actor: DecisionActor
    attention_item_id: Optional[str] = None
    cascade_id: Optional[str] = None
    #: ISO instant after which no option remains. ``None`` when no option closes.
    decision_deadline: Optional[str] = None
    decision_window_hours: Optional[float] = None
    #: The instant the world was queried at.
    at: Optional[str] = None
    objectives: List[DecisionObjective] = field(default_factory=list)
    hard_constraints: List[str] = field(default_factory=list)
    soft_constraints: List[str] = field(default_factory=list)
    #: Every action in the catalogue for this domain and actor, with whether it
    #: could be considered. Includes the ones that could not.
    available_actions: List[Dict[str, Any]] = field(default_factory=list)
    baseline_option_id: Optional[str] = None
    options: List[DecisionOption] = field(default_factory=list)
    frontier: Optional[DecisionFrontier] = None
    recommendation: Optional[DecisionRecommendation] = None
    #: Where every input came from: the cascade, the marine product, the
    #: cost basis, the branch registry.
    evidence: Dict[str, Any] = field(default_factory=dict)
    headline: str = ""
    do_nothing_statement: str = ""
    workflow: str = COMPUTED
    workflow_history: List[Dict[str, Any]] = field(default_factory=list)
    #: Set when a human chose; may differ from the recommendation.
    human_choice: Optional[str] = None
    notes: List[str] = field(default_factory=list)

    # -- lookups -----------------------------------------------------------
    def option(self, option_id: str) -> Optional[DecisionOption]:
        return next((o for o in self.options if o.option_id == option_id), None)

    @property
    def baseline(self) -> Optional[DecisionOption]:
        return None if self.baseline_option_id is None else self.option(self.baseline_option_id)

    @property
    def feasible_options(self) -> List[DecisionOption]:
        return [o for o in self.options if o.feasible]

    @property
    def rejected_options(self) -> List[DecisionOption]:
        return [o for o in self.options if o.status == REJECTED]

    def validate(self) -> List[str]:
        """Structural problems. Empty means the problem is well formed."""
        problems: List[str] = []
        if self.domain not in DOMAINS:
            problems.append(f"unknown domain {self.domain}")
        if self.baseline_option_id is None:
            problems.append("a decision problem must carry a baseline option")
        elif self.baseline is None:
            problems.append(f"baseline {self.baseline_option_id} is not among the options")
        elif not self.baseline.is_baseline:
            problems.append("the baseline option is not marked as such")
        if sum(1 for o in self.options if o.is_baseline) > 1:
            problems.append("more than one option claims to be the baseline")
        if not self.world_state_id:
            problems.append("a decision problem must be pinned to a world state")
        ids = [o.option_id for o in self.options]
        if len(ids) != len(set(ids)):
            problems.append("option ids are not unique")
        return problems

    def to_dict(self, *, include_options: bool = True) -> Dict[str, Any]:
        payload: Dict[str, Any] = {
            "decisionId": self.decision_id,
            "createdAt": self.created_at,
            "domain": self.domain,
            "worldRevision": self.world_revision,
            "worldStateId": self.world_state_id,
            "subject": {"type": self.subject_type, "id": self.subject_id,
                        "label": self.subject_label},
            "actor": self.actor.to_dict(),
            "attentionItemId": self.attention_item_id,
            "cascadeId": self.cascade_id,
            "decisionDeadline": self.decision_deadline,
            "decisionWindowHours": (
                None if self.decision_window_hours is None
                else round(self.decision_window_hours, 2)
            ),
            "at": self.at,
            "objectives": [o.to_dict() for o in self.objectives],
            "hardConstraints": self.hard_constraints,
            "softConstraints": self.soft_constraints,
            "availableActions": self.available_actions,
            "baselineOptionId": self.baseline_option_id,
            "frontier": None if self.frontier is None else self.frontier.to_dict(),
            "recommendation": (
                None if self.recommendation is None else self.recommendation.to_dict()
            ),
            "evidence": self.evidence,
            "headline": self.headline,
            "doNothingStatement": self.do_nothing_statement,
            "workflow": self.workflow,
            "workflowHistory": self.workflow_history,
            "humanChoice": self.human_choice,
            "notes": self.notes,
            "counts": {
                "options": len(self.options),
                "feasible": len(self.feasible_options),
                "rejected": len(self.rejected_options),
            },
        }
        if include_options:
            payload["options"] = [o.to_dict() for o in self.options]
        return payload


__all__ = [
    "ACCEPTED",
    "ACTORS",
    "APPROVED",
    "AVAILABILITY",
    "AVAILABLE",
    "Availability",
    "CARGO_CONNECTION",
    "COMPUTED",
    "ConstraintResult",
    "DECLINED",
    "DOMAINS",
    "DecisionActor",
    "DecisionError",
    "DecisionEvaluation",
    "DecisionFrontier",
    "DecisionObjective",
    "DecisionOption",
    "DecisionProblem",
    "DecisionRecommendation",
    "FEASIBLE",
    "INSUFFICIENT_DATA",
    "ISSUED",
    "MAXIMISE",
    "MINIMISE",
    "Measure",
    "NATIONAL_ADMIN",
    "NOT_EVALUATED",
    "OBJECTIVES",
    "OBSERVED",
    "OPTION_STATUSES",
    "PORT_AUTHORITY",
    "PORT_BERTHING",
    "PROPOSED",
    "REJECTED",
    "REVIEWED",
    "SHIPPING_COMPANY",
    "TERMINAL_OPERATOR",
    "UNAVAILABLE",
    "UNSUPPORTED",
    "VESSEL_OPERATOR",
    "VESSEL_ROUTING",
    "WORKFLOW_STATES",
    "known",
    "unknown",
]
