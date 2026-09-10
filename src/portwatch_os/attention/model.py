"""What requires action, why now, and what it costs to do nothing.

A risk score is not a product. "Bab-el-Mandeb: 0.72" tells an operator nothing
they can act on: not whether to act, not by when, not what happens if they
don't, and not what it is worth. Every field here exists to answer one of those
questions, and an item that cannot answer them is not worth an operator's
attention in the first place.

Two rules shape the whole module.

**Nothing here computes a number.** Every magnitude is lifted from a cascade the
World State Engine already produced, with its unit, confidence and provenance
intact. An attention item is a *framing* of computed consequence, so a port
authority and a carrier looking at one event cannot be shown two different
arithmetics of it.

**An option that has closed is not an option.** A vessel already inside the
water cannot divert, however severe its exposure, and presenting it among things
to act on wastes the one resource this module exists to protect. Those items
become ``MONITOR_ONLY`` and are ranked accordingly -- present, visible, and
never at the top of a queue titled "act now".
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Sequence, Tuple

# --------------------------------------------------------------------------
# status
# --------------------------------------------------------------------------

#: The option closes within the hour, or has already begun to.
ACT_NOW = "ACT_NOW"
#: An option exists and the window is measured in hours, not days.
ACT_SOON = "ACT_SOON"
#: Consequence is real but the decision can wait a shift.
WATCH = "WATCH"
#: Exposed, and nothing can be done about it. Reported so it is not mistaken
#: for safety, never ranked as an opportunity.
MONITOR_ONLY = "MONITOR_ONLY"
#: The consequence is known and no intervention exists in this deployment.
NO_ACTION_AVAILABLE = "NO_ACTION_AVAILABLE"

STATUSES: Tuple[str, ...] = (
    ACT_NOW,
    ACT_SOON,
    WATCH,
    MONITOR_ONLY,
    NO_ACTION_AVAILABLE,
)

#: Statuses that describe something a human could still change.
ACTIONABLE: Tuple[str, ...] = (ACT_NOW, ACT_SOON, WATCH)

# --------------------------------------------------------------------------
# scope
# --------------------------------------------------------------------------

NATIONAL = "NATIONAL_ADMIN"
PORT_AUTHORITY = "PORT_AUTHORITY"
SHIPPING_COMPANY = "SHIPPING_COMPANY"
VESSEL_OPERATOR = "VESSEL_OPERATOR"


@dataclass(frozen=True)
class Effect:
    """One consequence, in the unit it was computed in.

    Carries its own provenance because the operational and financial effects of
    the same item are usually derived at different points in a cascade and with
    different confidence; collapsing them into one number would hide which part
    of the claim is weak.
    """

    value: Optional[float]
    unit: Optional[str]
    confidence: Optional[float] = None
    #: Plain-language statement of what the number means.
    statement: str = ""
    #: Why there is no number, when there is none. Never left empty in that case.
    unavailable_because: Optional[str] = None
    #: The rule in the transfer catalogue that produced it.
    rule: Optional[str] = None

    @property
    def available(self) -> bool:
        return self.value is not None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "value": None if self.value is None else round(self.value, 3),
            "unit": self.unit,
            "confidence": None if self.confidence is None else round(self.confidence, 3),
            "statement": self.statement,
            "available": self.available,
            "unavailableBecause": self.unavailable_because,
            "rule": self.rule,
        }


UNAVAILABLE = Effect(value=None, unit=None)


@dataclass(frozen=True)
class Option:
    """Something a human could do, and what it would take."""

    action: str
    summary: str
    #: Hours from now until this specific option stops being available.
    closes_in_hours: Optional[float] = None
    effect: Effect = UNAVAILABLE
    #: Why this is not the recommendation, when it is an alternative.
    tradeoff: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "action": self.action,
            "summary": self.summary,
            "closesInHours": (
                None if self.closes_in_hours is None else round(self.closes_in_hours, 2)
            ),
            "effect": self.effect.to_dict(),
            "tradeoff": self.tradeoff,
        }


@dataclass
class AttentionItem:
    """One thing an operator should look at, and everything needed to decide."""

    attention_id: str
    subject_type: str
    subject_id: str
    subject_label: str
    #: The workspace role this item is framed for.
    scope: str

    headline: str
    reason: str

    #: 0..1, lifted from the cascade rather than assigned here.
    severity: float
    confidence: float
    #: 0..1, derived from how soon the option closes.
    urgency: float

    status: str

    #: When the option stops being available. ``None`` when there is no option.
    action_deadline: Optional[str] = None
    #: Hours from the query instant to that deadline.
    intervention_window_hours: Optional[float] = None

    baseline_outcome: str = ""
    do_nothing_outcome: str = ""

    recommended_action: Optional[Option] = None
    alternative_actions: List[Option] = field(default_factory=list)

    expected_operational_effect: Effect = UNAVAILABLE
    expected_financial_effect: Effect = UNAVAILABLE

    #: The cascade this was framed from, and the node within it. Both are
    #: required: an item that cannot point at the computation behind it is an
    #: assertion, and this product does not ship assertions.
    cascade_id: str = ""
    evidence_node_key: str = ""

    #: Computed by :func:`rank`. Not a severity; see the module docstring.
    priority: float = 0.0
    priority_basis: Dict[str, float] = field(default_factory=dict)

    @property
    def financial_effect_available(self) -> bool:
        return self.expected_financial_effect.available

    @property
    def actionable(self) -> bool:
        return self.status in ACTIONABLE

    def to_dict(self) -> Dict[str, Any]:
        return {
            "attentionId": self.attention_id,
            "subjectType": self.subject_type,
            "subjectId": self.subject_id,
            "subjectLabel": self.subject_label,
            "scope": self.scope,
            "headline": self.headline,
            "reason": self.reason,
            "severity": round(self.severity, 3),
            "confidence": round(self.confidence, 3),
            "urgency": round(self.urgency, 3),
            "status": self.status,
            "actionable": self.actionable,
            "actionDeadline": self.action_deadline,
            "interventionWindowHours": (
                None if self.intervention_window_hours is None
                else round(self.intervention_window_hours, 2)
            ),
            "baselineOutcome": self.baseline_outcome,
            "doNothingOutcome": self.do_nothing_outcome,
            "recommendedAction": (
                None if self.recommended_action is None
                else self.recommended_action.to_dict()
            ),
            "alternativeActions": [o.to_dict() for o in self.alternative_actions],
            "expectedOperationalEffect": self.expected_operational_effect.to_dict(),
            "expectedFinancialEffect": self.expected_financial_effect.to_dict(),
            "financialEffectAvailable": self.financial_effect_available,
            "cascadeId": self.cascade_id,
            "evidenceNodeKey": self.evidence_node_key,
            "priority": round(self.priority, 5),
            "priorityBasis": {k: round(v, 4) for k, v in self.priority_basis.items()},
        }


# --------------------------------------------------------------------------
# ranking
# --------------------------------------------------------------------------

#: How much a closing window multiplies an item's priority. A step function
#: rather than a curve, because an operator has to be able to predict the
#: ordering of their own queue, and "under three hours jumps the queue" is a
#: rule a person can hold in their head.
URGENCY_STEPS: Tuple[Tuple[float, float], ...] = (
    (1.0, 3.0),      # closes within the hour
    (3.0, 2.4),
    (6.0, 1.9),
    (12.0, 1.5),
    (24.0, 1.2),
)
URGENCY_BASELINE = 1.0

#: What an item is worth when nothing can be done about it. Not zero: an
#: operator still needs to know a committed vessel is exposed. Low enough that
#: it never displaces something actionable.
UNACTIONABLE_WEIGHT = 0.12


def urgency_multiplier(window_hours: Optional[float]) -> float:
    """How much a closing decision window amplifies priority."""
    if window_hours is None:
        return URGENCY_BASELINE
    if window_hours <= 0:
        # The window has shut. Urgency cannot rescue an item that has no option;
        # `actionability` is what demotes it, not this.
        return URGENCY_BASELINE
    for threshold, multiplier in URGENCY_STEPS:
        if window_hours <= threshold:
            return multiplier
    return URGENCY_BASELINE


def urgency_score(window_hours: Optional[float]) -> float:
    """The 0..1 urgency an operator sees, distinct from the multiplier."""
    if window_hours is None or window_hours <= 0:
        return 0.0
    if window_hours >= 72.0:
        return 0.05
    return max(0.0, min(1.0, 1.0 - (window_hours / 72.0)))


def rank(item: AttentionItem) -> float:
    """Priority, and the reason for it, recorded on the item.

    Deliberately not a severity sort. The quantity an operator is really
    choosing between is *how much loss their attention can still prevent*, which
    is the consequence at stake, discounted by how sure we are of it, amplified
    by how soon the chance to act disappears, and reduced almost to nothing when
    there is no chance to act at all.

    That last term is what lets a moderate event with a thirty-minute window
    outrank a severe one nobody can do anything about -- which is the ordering a
    duty controller would choose by hand, and the reason a severity sort feels
    wrong to them.
    """
    consequence = _normalised_consequence(item)
    confidence = max(0.0, min(1.0, item.confidence))
    urgency = urgency_multiplier(item.intervention_window_hours)
    actionability = 1.0 if item.actionable else UNACTIONABLE_WEIGHT

    priority = consequence * confidence * urgency * actionability
    item.priority = priority
    item.priority_basis = {
        "consequence": consequence,
        "confidence": confidence,
        "urgencyMultiplier": urgency,
        "actionability": actionability,
    }
    return priority


#: Consequence magnitudes are normalised so units can be compared at all. These
#: are the scales at which an operator would call something a full-weight
#: problem: a day of aggregate delay, ten exposed hulls, a fifth of the yard.
_CONSEQUENCE_SCALE: Dict[str, float] = {
    "hours": 24.0,
    "vessels": 10.0,
    "ratio": 0.2,
    "teu": 500.0,
    "berth_hours": 24.0,
    "inr": 5_000_000.0,
    "risk": 1.0,
}


def _normalised_consequence(item: AttentionItem) -> float:
    effect = item.expected_operational_effect
    if effect.available and effect.unit in _CONSEQUENCE_SCALE:
        scale = _CONSEQUENCE_SCALE[effect.unit]
        return min(1.0, abs(effect.value or 0.0) / scale)
    # No operational magnitude computed. Severity is the only thing left, and it
    # is used here rather than as the primary sort precisely because it is the
    # weakest of the available signals.
    return max(0.0, min(1.0, item.severity))


def order(items: Sequence[AttentionItem]) -> List[AttentionItem]:
    """Rank every item and return them worst-first, deterministically."""
    for item in items:
        rank(item)
    return sorted(
        items,
        key=lambda i: (-i.priority, i.status, i.attention_id),
    )


__all__ = [
    "ACTIONABLE",
    "ACT_NOW",
    "ACT_SOON",
    "AttentionItem",
    "Effect",
    "MONITOR_ONLY",
    "NATIONAL",
    "NO_ACTION_AVAILABLE",
    "Option",
    "PORT_AUTHORITY",
    "SHIPPING_COMPANY",
    "STATUSES",
    "UNACTIONABLE_WEIGHT",
    "UNAVAILABLE",
    "URGENCY_BASELINE",
    "URGENCY_STEPS",
    "VESSEL_OPERATOR",
    "WATCH",
    "order",
    "rank",
    "urgency_multiplier",
    "urgency_score",
]
