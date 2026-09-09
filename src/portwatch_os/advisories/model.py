"""Port-to-vessel advisories: the human-in-the-loop boundary.

This is where the product stops recommending and starts *communicating*, and it
is the single most safety-relevant module in the repository. Two rules are
enforced by the state machine below rather than by convention:

**Nothing reaches a vessel without a named human approving it.** The decision
engine produces a DRAFT. A port controller reviews it and either approves,
modifies or rejects it. Only an ISSUED advisory is visible to the company or the
vessel, and only a controller can issue one. There is no transition from DRAFT
to ISSUED that does not pass through a person.

**An advisory is a recommendation, never a command.** The recipient can accept,
query or decline, and declining is a normal terminal state that costs nothing.
PortWatch does not control vessel navigation, and the vocabulary here is chosen
so that it cannot drift into pretending otherwise: an advisory *recommends* an
arrival time, a speed or a berth. Master's authority is not in this state
machine because it is not this system's to model.

Every transition is recorded with who did it, when, and why. That audit trail is
what makes the workflow auditable after the fact, which for a port authority is
the difference between usable and not.
"""

from __future__ import annotations

import hashlib
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Sequence, Tuple

# --------------------------------------------------------------------------
# states
# --------------------------------------------------------------------------

DRAFT = "draft"
UNDER_REVIEW = "under_review"
ISSUED = "issued"
ACKNOWLEDGED = "acknowledged"
ACCEPTED = "accepted"
QUERIED = "queried"
DECLINED = "declined"
REJECTED = "rejected"
WITHDRAWN = "withdrawn"
EXPIRED = "expired"
COMPLETED = "completed"

ADVISORY_STATES: Tuple[str, ...] = (
    DRAFT, UNDER_REVIEW, ISSUED, ACKNOWLEDGED, ACCEPTED,
    QUERIED, DECLINED, REJECTED, WITHDRAWN, EXPIRED, COMPLETED,
)

#: Terminal states. Nothing leaves these.
TERMINAL_STATES: Tuple[str, ...] = (DECLINED, REJECTED, WITHDRAWN, EXPIRED, COMPLETED)

#: Who is allowed to make each transition. This is the authorisation model, and
#: it is checked on every call -- a vessel cannot issue an advisory to itself,
#: and a port controller cannot accept one on the recipient's behalf.
ISSUER = "issuer"           # the port authority controller
RECIPIENT = "recipient"     # the company or vessel the advisory is addressed to
SYSTEM = "system"           # the clock, for expiry only

ROLES: Tuple[str, ...] = (ISSUER, RECIPIENT, SYSTEM)


@dataclass(frozen=True)
class Transition:
    source: str
    target: str
    actor_role: str
    label: str
    #: Whether the transition needs a reason recorded. Rejecting or declining
    #: without one is how an audit trail becomes useless.
    requires_reason: bool = False


TRANSITIONS: Tuple[Transition, ...] = (
    Transition(DRAFT, UNDER_REVIEW, ISSUER, "Open for review"),
    Transition(DRAFT, WITHDRAWN, ISSUER, "Withdraw draft"),
    Transition(UNDER_REVIEW, ISSUED, ISSUER, "Approve and issue"),
    Transition(UNDER_REVIEW, REJECTED, ISSUER, "Reject", requires_reason=True),
    Transition(UNDER_REVIEW, DRAFT, ISSUER, "Return to draft with changes"),
    Transition(ISSUED, ACKNOWLEDGED, RECIPIENT, "Acknowledge receipt"),
    Transition(ISSUED, ACCEPTED, RECIPIENT, "Accept"),
    Transition(ISSUED, QUERIED, RECIPIENT, "Request review", requires_reason=True),
    Transition(ISSUED, DECLINED, RECIPIENT, "Decline", requires_reason=True),
    Transition(ISSUED, WITHDRAWN, ISSUER, "Withdraw", requires_reason=True),
    Transition(ISSUED, EXPIRED, SYSTEM, "Expire unanswered"),
    Transition(ACKNOWLEDGED, ACCEPTED, RECIPIENT, "Accept"),
    Transition(ACKNOWLEDGED, QUERIED, RECIPIENT, "Request review", requires_reason=True),
    Transition(ACKNOWLEDGED, DECLINED, RECIPIENT, "Decline", requires_reason=True),
    Transition(ACKNOWLEDGED, EXPIRED, SYSTEM, "Expire unanswered"),
    Transition(QUERIED, ISSUED, ISSUER, "Reissue after review"),
    Transition(QUERIED, WITHDRAWN, ISSUER, "Withdraw after review", requires_reason=True),
    Transition(ACCEPTED, COMPLETED, ISSUER, "Close as complete"),
    Transition(ACCEPTED, WITHDRAWN, ISSUER, "Withdraw", requires_reason=True),
)

_BY_SOURCE: Dict[str, List[Transition]] = {}
for _t in TRANSITIONS:
    _BY_SOURCE.setdefault(_t.source, []).append(_t)


class AdvisoryError(RuntimeError):
    """An illegal or unauthorised transition. Never swallowed."""


def allowed_transitions(state: str, actor_role: Optional[str] = None) -> List[Transition]:
    options = _BY_SOURCE.get(state, [])
    if actor_role is None:
        return list(options)
    return [t for t in options if t.actor_role == actor_role]


def find_transition(state: str, target: str, actor_role: str) -> Transition:
    """The transition, or an error naming exactly why it is not available."""
    for transition in _BY_SOURCE.get(state, []):
        if transition.target != target:
            continue
        if transition.actor_role != actor_role:
            raise AdvisoryError(
                f"{state} -> {target} is reserved for the {transition.actor_role}; "
                f"a {actor_role} may not make it"
            )
        return transition
    available = ", ".join(
        f"{t.target} ({t.actor_role})" for t in _BY_SOURCE.get(state, [])
    ) or "none"
    raise AdvisoryError(
        f"{state} -> {target} is not a legal advisory transition. From {state} the "
        f"available transitions are: {available}"
    )


# --------------------------------------------------------------------------
# advisory kinds
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class AdvisoryKind:
    key: str
    label: str
    #: The field the recommendation must carry to be well formed.
    required_field: str
    unit: Optional[str]
    description: str


ADVISORY_KINDS: Dict[str, AdvisoryKind] = {
    k.key: k
    for k in [
        AdvisoryKind("arrival_window", "Recommended arrival", "recommendedArrival", "UTC",
                     "A revised arrival time that reduces expected waiting."),
        AdvisoryKind("speed", "Recommended speed", "recommendedSpeedKn", "kn",
                     "A passage speed that meets the recommended arrival window."),
        AdvisoryKind("berth", "Berth reassignment", "recommendedBerth", None,
                     "A different berth, for capacity, draught or crane reasons."),
        AdvisoryKind("holding", "Holding instruction", "holdingArea", None,
                     "A recommended anchorage or holding sector while waiting."),
        AdvisoryKind("approach", "Approach routing", "approach", None,
                     "A recommended approach where conditions favour one."),
        AdvisoryKind("departure_priority", "Departure priority", "departureWindow", "UTC",
                     "A recommended departure slot."),
        AdvisoryKind("weather_precaution", "Weather precaution", "precaution", None,
                     "A recommended precaution for forecast conditions."),
        AdvisoryKind("cargo_transfer", "Cargo transfer", "transferPlan", None,
                     "A recommended transshipment connection and yard routing."),
    ]
}


@dataclass
class AuditEntry:
    """One recorded step in an advisory's life."""

    at: str
    actor: str
    actor_role: str
    action: str
    from_state: str
    to_state: str
    reason: Optional[str] = None
    changes: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class Advisory:
    """One recommendation from a port authority to a vessel or its operator."""

    advisory_id: str
    kind: str
    port_code: str
    #: Who issued it. A named controller, not "the system".
    issuer: str
    issuer_organisation: str
    #: Who it is addressed to.
    recipient_vessel_id: str
    recipient_vessel_name: str
    recipient_organisation: str
    created_at: str
    #: The recommendation itself. Shape depends on the kind.
    recommendation: Dict[str, Any]
    #: Plain-language justification. Required: an advisory a master cannot
    #: evaluate is an advisory a master will ignore.
    reason: str
    state: str = DRAFT

    #: What the decision engine's confidence was. Never the LLM's.
    model_confidence: Optional[float] = None
    #: Ledger prediction ids this rests on, for the evidence drawer.
    prediction_ids: List[str] = field(default_factory=list)
    #: The measured evidence, e.g. {"expectedWaitReductionHours": 3.8}.
    evidence: Dict[str, Any] = field(default_factory=dict)
    #: What the Critic said before this was shown to a controller.
    critic_verdict: Optional[str] = None
    critic_reasons: List[str] = field(default_factory=list)
    #: The decision ledger row this advisory settles, if any.
    decision_id: Optional[str] = None

    #: When it stops being actionable.
    valid_until: Optional[str] = None
    issued_at: Optional[str] = None
    responded_at: Optional[str] = None
    response_reason: Optional[str] = None
    #: Set when a controller changed the recommendation before issuing.
    modified_from: Optional[Dict[str, Any]] = None
    audit: List[AuditEntry] = field(default_factory=list)

    @staticmethod
    def make_id(port_code: str, vessel_id: str, kind: str, created_at: str) -> str:
        digest = hashlib.sha1(
            f"{port_code}|{vessel_id}|{kind}|{created_at}".encode("utf-8")
        ).hexdigest()
        return f"ADV-{port_code}-{digest[:10].upper()}"

    @property
    def kind_spec(self) -> Optional[AdvisoryKind]:
        return ADVISORY_KINDS.get(self.kind)

    @property
    def is_terminal(self) -> bool:
        return self.state in TERMINAL_STATES

    @property
    def visible_to_recipient(self) -> bool:
        """The rule that keeps unapproved drafts off a vessel's screen.

        A draft is a working document inside the port authority. Until a
        controller issues it, the recipient must not see it at all -- otherwise
        the human approval step is theatre.
        """
        return self.state not in (DRAFT, UNDER_REVIEW)

    def validate(self) -> List[str]:
        """Structural problems with this advisory. Empty means well formed."""
        problems: List[str] = []
        spec = self.kind_spec
        if spec is None:
            problems.append(f"unknown advisory kind {self.kind}")
        elif spec.required_field not in self.recommendation:
            problems.append(
                f"a {spec.label} advisory must carry {spec.required_field}"
            )
        if not self.reason or len(self.reason.strip()) < 12:
            problems.append(
                "an advisory must carry a reason a master can evaluate"
            )
        if not self.recipient_vessel_id:
            problems.append("an advisory must name its recipient vessel")
        return problems

    def to_dict(self, *, for_recipient: bool = False) -> Dict[str, Any]:
        payload = {
            "advisoryId": self.advisory_id,
            "kind": self.kind,
            "kindLabel": self.kind_spec.label if self.kind_spec else self.kind,
            "portCode": self.port_code,
            "issuer": self.issuer,
            "issuerOrganisation": self.issuer_organisation,
            "recipientVesselId": self.recipient_vessel_id,
            "recipientVesselName": self.recipient_vessel_name,
            "recipientOrganisation": self.recipient_organisation,
            "createdAt": self.created_at,
            "recommendation": self.recommendation,
            "reason": self.reason,
            "state": self.state,
            "isTerminal": self.is_terminal,
            "modelConfidence": self.model_confidence,
            "predictionIds": self.prediction_ids,
            "evidence": self.evidence,
            "criticVerdict": self.critic_verdict,
            "criticReasons": self.critic_reasons,
            "decisionId": self.decision_id,
            "validUntil": self.valid_until,
            "issuedAt": self.issued_at,
            "respondedAt": self.responded_at,
            "responseReason": self.response_reason,
            "modifiedFrom": self.modified_from,
            "audit": [entry.to_dict() for entry in self.audit],
            "availableTransitions": [
                {"target": t.target, "label": t.label, "actorRole": t.actor_role,
                 "requiresReason": t.requires_reason}
                for t in allowed_transitions(self.state)
            ],
        }
        if for_recipient:
            # A recipient sees the recommendation and the reasoning, not the
            # port's internal review trail.
            payload["audit"] = [
                entry.to_dict() for entry in self.audit
                if entry.to_state not in (DRAFT, UNDER_REVIEW)
            ]
        return payload


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def transition(
    advisory: Advisory,
    target: str,
    *,
    actor: str,
    actor_role: str,
    reason: Optional[str] = None,
    changes: Optional[Dict[str, Any]] = None,
    at: Optional[str] = None,
) -> Advisory:
    """Move an advisory to a new state, or refuse and say why.

    Mutates and returns the advisory. Every call appends an audit entry,
    including the refused ones -- no, especially not the refused ones: a refusal
    raises, and the caller decides whether that is worth recording. What is
    always recorded is what actually happened.
    """
    if actor_role not in ROLES:
        raise AdvisoryError(f"unknown actor role {actor_role}")
    if not actor:
        raise AdvisoryError("every advisory transition must name its actor")

    step = find_transition(advisory.state, target, actor_role)
    if step.requires_reason and not (reason and reason.strip()):
        raise AdvisoryError(
            f"'{step.label}' must record a reason; an audit trail without one "
            "cannot be reviewed afterwards"
        )

    now = at or utc_now()
    previous = advisory.state
    advisory.state = target

    if target == ISSUED and advisory.issued_at is None:
        advisory.issued_at = now
    if target in (ACCEPTED, DECLINED, QUERIED, ACKNOWLEDGED):
        advisory.responded_at = now
        advisory.response_reason = reason

    advisory.audit.append(
        AuditEntry(
            at=now, actor=actor, actor_role=actor_role, action=step.label,
            from_state=previous, to_state=target, reason=reason,
            changes=dict(changes or {}),
        )
    )
    return advisory


def modify(
    advisory: Advisory,
    changes: Dict[str, Any],
    *,
    actor: str,
    reason: str,
    at: Optional[str] = None,
) -> Advisory:
    """A controller edits the recommendation before issuing it.

    Only from DRAFT or UNDER_REVIEW, and only by the issuer. The original is kept
    in ``modified_from``, because "the model said 18:30 and the controller made it
    19:15" is exactly the signal the learning layer needs about whether the model
    is trusted.
    """
    if advisory.state not in (DRAFT, UNDER_REVIEW):
        raise AdvisoryError(
            f"an advisory in {advisory.state} cannot be edited; withdraw it and "
            "raise a new one"
        )
    if not reason or len(reason.strip()) < 4:
        raise AdvisoryError("a modification must record why it was made")

    if advisory.modified_from is None:
        advisory.modified_from = dict(advisory.recommendation)
    advisory.recommendation = {**advisory.recommendation, **changes}
    advisory.audit.append(
        AuditEntry(
            at=at or utc_now(), actor=actor, actor_role=ISSUER, action="Modify recommendation",
            from_state=advisory.state, to_state=advisory.state, reason=reason,
            changes=dict(changes),
        )
    )
    return advisory


def expire_due(
    advisories: Sequence[Advisory],
    *,
    now: Optional[str] = None,
) -> List[Advisory]:
    """Expire issued advisories past their validity. The only SYSTEM transition.

    An advisory that nobody answered and that is now about a time in the past is
    noise on an operator's screen. Expiring it is a measurement -- the ledger
    records that it went unanswered, which is itself a signal about whether the
    advisories are useful.
    """
    now = now or utc_now()
    expired: List[Advisory] = []
    for advisory in advisories:
        if advisory.state not in (ISSUED, ACKNOWLEDGED):
            continue
        if not advisory.valid_until or advisory.valid_until > now:
            continue
        transition(
            advisory, EXPIRED, actor="portwatch-clock", actor_role=SYSTEM,
            reason=f"validity elapsed at {advisory.valid_until} with no response",
            at=now,
        )
        expired.append(advisory)
    return expired


__all__ = [
    "ACCEPTED",
    "ACKNOWLEDGED",
    "ADVISORY_KINDS",
    "ADVISORY_STATES",
    "COMPLETED",
    "DECLINED",
    "DRAFT",
    "EXPIRED",
    "ISSUED",
    "ISSUER",
    "QUERIED",
    "RECIPIENT",
    "REJECTED",
    "ROLES",
    "SYSTEM",
    "TERMINAL_STATES",
    "TRANSITIONS",
    "UNDER_REVIEW",
    "WITHDRAWN",
    "Advisory",
    "AdvisoryError",
    "AdvisoryKind",
    "AuditEntry",
    "Transition",
    "allowed_transitions",
    "expire_due",
    "find_transition",
    "modify",
    "transition",
    "utc_now",
]
