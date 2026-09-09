"""The Critic.

Every high-impact recommendation passes through here before a human sees it. The
Critic's job is narrow and it matters that it stays narrow:

    It checks whether a recommendation is **supported, safe and consistent**
    with the evidence that produced it.

It does not re-derive the recommendation, it does not overrule a mathematical
constraint, and it cannot make a rejected proposal into an approved one. Where
the deterministic layer has already said something is infeasible, the Critic
records that and stops -- it has no authority to relax a berth's draught or a
vessel's position.

The checks are ordered by how badly they fail. A recommendation that would tell
a master to divert a ship already past the strait is not "low confidence", it is
wrong, and it is rejected outright. A recommendation resting on a stale artefact
is still actionable but should be shown with that attached, so it is modified
rather than rejected.

Verdicts:

    APPROVED   Every check passed. Show it to the controller as it stands.
    MODIFIED   Actionable, but something must be attached to it or changed.
    REJECTED   Do not put this in front of an operator.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Sequence, Tuple

from src.portwatch_os.agents.base import AgentResult, Finding

APPROVED = "APPROVED"
MODIFIED = "MODIFIED"
REJECTED = "REJECTED"

VERDICTS: Tuple[str, ...] = (APPROVED, MODIFIED, REJECTED)

#: Severity of a failed check, which decides the verdict. A single ``blocking``
#: failure rejects; ``qualifying`` failures modify.
BLOCKING = "blocking"
QUALIFYING = "qualifying"


@dataclass
class CriticCheck:
    """One check, its result, and what it means."""

    name: str
    passed: bool
    severity: str
    detail: str
    #: What must change if this failed and the verdict is MODIFIED.
    remedy: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name, "passed": self.passed, "severity": self.severity,
            "detail": self.detail, "remedy": self.remedy,
        }


@dataclass
class CriticVerdict:
    verdict: str
    checks: List[CriticCheck] = field(default_factory=list)
    reasons: List[str] = field(default_factory=list)
    #: Qualifications that must be shown alongside the recommendation.
    qualifications: List[str] = field(default_factory=list)
    #: Confidence after the Critic's own discount.
    adjusted_confidence: Optional[float] = None
    ran_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat(timespec="seconds")
    )

    @property
    def failed(self) -> List[CriticCheck]:
        return [c for c in self.checks if not c.passed]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "verdict": self.verdict,
            "checks": [c.to_dict() for c in self.checks],
            "reasons": self.reasons,
            "qualifications": self.qualifications,
            "adjustedConfidence": (
                None if self.adjusted_confidence is None
                else round(self.adjusted_confidence, 3)
            ),
            "failedChecks": [c.name for c in self.failed],
            "ranAt": self.ran_at,
        }


@dataclass
class Recommendation:
    """What the Critic is asked to judge.

    Deliberately a flat record rather than a reference to an agent: the Critic
    must be able to judge a recommendation from the decision engine, from an
    optimiser or from an agent chain, and treating all three identically is what
    stops a "trusted" path growing round the side.
    """

    kind: str
    subject: str
    action: str
    #: The numbers being recommended, e.g. {"recommendedArrivalHours": 5.0}.
    values: Dict[str, Any] = field(default_factory=dict)
    #: What the recommendation claims it achieves.
    expected_impact: Dict[str, float] = field(default_factory=dict)
    #: Confidence from the producing model, not from a language model.
    confidence: Optional[float] = None
    #: The tools whose output this rests on.
    evidence_tools: List[str] = field(default_factory=list)
    #: Free-form evidence the checks read.
    evidence: Dict[str, Any] = field(default_factory=dict)
    reason: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "kind": self.kind, "subject": self.subject, "action": self.action,
            "values": self.values, "expectedImpact": self.expected_impact,
            "confidence": self.confidence, "evidenceTools": self.evidence_tools,
            "reason": self.reason,
        }


# --------------------------------------------------------------------------
# thresholds
# --------------------------------------------------------------------------

#: Below this, a recommendation is not put in front of an operator as an action.
MIN_ACTIONABLE_CONFIDENCE = 0.35

#: An artefact older than this is flagged, not rejected: a twelve-hour-old port
#: state is still the best available picture, and hiding it would be worse.
STALE_HOURS = 18.0

#: A recommendation must be supported by at least this many successful tools.
MIN_EVIDENCE_TOOLS = 1

#: Speed advisories outside this envelope are refused: the product does not
#: recommend a speed a merchant vessel would not run.
SPEED_ENVELOPE_KN = (6.0, 24.0)

#: Arrival restaggering beyond this is not an advisory, it is a schedule change
#: and belongs in a commercial conversation rather than a port advisory.
MAX_ARRIVAL_SHIFT_HOURS = 48.0


class Critic:
    """Judges recommendations. Cannot create or relax one."""

    name = "critic"
    purpose = (
        "Check that a recommendation is supported by its evidence, physically "
        "possible, and safe to put in front of an operator."
    )

    def review(
        self,
        recommendation: Recommendation,
        *,
        agent_results: Sequence[AgentResult] = (),
    ) -> CriticVerdict:
        checks: List[CriticCheck] = []

        checks.append(self._check_evidence(recommendation, agent_results))
        checks.append(self._check_confidence(recommendation))
        checks.append(self._check_freshness(recommendation))
        checks.append(self._check_physical_envelope(recommendation))
        checks.append(self._check_timing(recommendation))
        checks.append(self._check_constraints(recommendation))
        checks.append(self._check_impact_claim(recommendation))
        checks.append(self._check_disagreement(recommendation, agent_results))

        blocking = [c for c in checks if not c.passed and c.severity == BLOCKING]
        qualifying = [c for c in checks if not c.passed and c.severity == QUALIFYING]

        if blocking:
            verdict = REJECTED
        elif qualifying:
            verdict = MODIFIED
        else:
            verdict = APPROVED

        # Each qualifying failure discounts confidence. The Critic never raises
        # it: a reviewer's job is to find reasons to trust something less.
        adjusted = recommendation.confidence
        if adjusted is not None:
            adjusted = adjusted * (0.85 ** len(qualifying))

        return CriticVerdict(
            verdict=verdict,
            checks=checks,
            reasons=[c.detail for c in blocking] or [c.detail for c in qualifying],
            qualifications=[c.remedy for c in qualifying if c.remedy],
            adjusted_confidence=adjusted,
        )

    # -- checks ------------------------------------------------------------
    def _check_evidence(
        self,
        recommendation: Recommendation,
        agent_results: Sequence[AgentResult],
    ) -> CriticCheck:
        successful = {
            call.tool for result in agent_results for call in result.calls if call.ok
        } | set(recommendation.evidence_tools)
        ok = len(successful) >= MIN_EVIDENCE_TOOLS
        return CriticCheck(
            "supported_by_evidence", ok, BLOCKING,
            (
                f"Rests on {len(successful)} successful tool call(s): "
                f"{', '.join(sorted(successful)) or 'none'}."
                if ok else
                "No tool produced the numbers in this recommendation. A recommendation "
                "with no computed evidence behind it is not shown to an operator."
            ),
        )

    def _check_confidence(self, recommendation: Recommendation) -> CriticCheck:
        confidence = recommendation.confidence
        if confidence is None:
            return CriticCheck(
                "confidence_stated", False, QUALIFYING,
                "The producing model stated no confidence.",
                remedy="Show this without a confidence figure rather than implying one.",
            )
        ok = confidence >= MIN_ACTIONABLE_CONFIDENCE
        return CriticCheck(
            "confidence_actionable", ok, QUALIFYING,
            f"Model confidence {confidence:.2f} against a floor of "
            f"{MIN_ACTIONABLE_CONFIDENCE:.2f}.",
            remedy=(
                None if ok else
                "Present as an observation to monitor rather than as a recommended action."
            ),
        )

    def _check_freshness(self, recommendation: Recommendation) -> CriticCheck:
        age = recommendation.evidence.get("sourceAgeHours")
        if age is None:
            return CriticCheck(
                "evidence_fresh", True, QUALIFYING,
                "No artefact age was supplied; freshness could not be checked.",
            )
        ok = float(age) <= STALE_HOURS
        return CriticCheck(
            "evidence_fresh", ok, QUALIFYING,
            f"The driving artefact is {float(age):.1f} h old against a "
            f"{STALE_HOURS:.0f} h budget.",
            remedy=(
                None if ok else
                f"Attach the artefact age ({float(age):.1f} h) to the recommendation so "
                "the controller can weigh it."
            ),
        )

    def _check_physical_envelope(self, recommendation: Recommendation) -> CriticCheck:
        """Physical plausibility. Blocking, because a bad number here is unsafe."""
        speed = recommendation.values.get("recommendedSpeedKn")
        if speed is not None:
            low, high = SPEED_ENVELOPE_KN
            if not (low <= float(speed) <= high):
                return CriticCheck(
                    "physical_envelope", False, BLOCKING,
                    f"A recommended speed of {float(speed):.1f} kn is outside the "
                    f"{low:.0f}-{high:.0f} kn envelope this product will advise.",
                )

        shift = recommendation.values.get("arrivalShiftHours")
        if shift is not None and abs(float(shift)) > MAX_ARRIVAL_SHIFT_HOURS:
            return CriticCheck(
                "physical_envelope", False, BLOCKING,
                f"An arrival shift of {float(shift):.1f} h exceeds the "
                f"{MAX_ARRIVAL_SHIFT_HOURS:.0f} h advisory envelope. A change this "
                "large is a schedule renegotiation, not a port advisory.",
            )

        return CriticCheck(
            "physical_envelope", True, BLOCKING,
            "Recommended values are inside the operating envelope.",
        )

    def _check_timing(self, recommendation: Recommendation) -> CriticCheck:
        """The check that stops the product advising the impossible.

        A vessel that has already entered a risk area cannot be diverted out of
        it. Recommending a diversion anyway would be worse than silence: it
        would look authoritative and be unactionable.
        """
        already = recommendation.evidence.get("alreadyEntered")
        action = recommendation.action.lower()
        if already and any(word in action for word in ("divert", "reroute", "avoid")):
            return CriticCheck(
                "action_still_available", False, BLOCKING,
                "The vessel has already entered the exposed area, so a diversion is "
                "no longer available. Recommending one would be unactionable.",
            )

        deadline = recommendation.evidence.get("hoursToDeadline")
        if deadline is not None and float(deadline) <= 0:
            return CriticCheck(
                "action_still_available", False, BLOCKING,
                f"The decision deadline passed {abs(float(deadline)):.1f} h ago.",
            )
        if deadline is not None and float(deadline) < 2:
            return CriticCheck(
                "action_still_available", False, QUALIFYING,
                f"Only {float(deadline):.1f} h remain before the option closes.",
                remedy="Mark this as urgent and show the deadline prominently.",
            )
        return CriticCheck(
            "action_still_available", True, BLOCKING,
            "The recommended action is still available at the time of review.",
        )

    def _check_constraints(self, recommendation: Recommendation) -> CriticCheck:
        """Hard constraints the deterministic layer already rejected.

        The Critic reports these; it never relaxes them. If the simulator said a
        berth cannot take a hull, no amount of reasoning here changes that.
        """
        violations = recommendation.evidence.get("violations") or []
        rejected = recommendation.evidence.get("rejectedActions") or []
        if violations:
            return CriticCheck(
                "no_constraint_violations", False, BLOCKING,
                f"The producing simulation reported {len(violations)} hard-constraint "
                f"violation(s): {violations[0].get('detail', violations[0])}. The Critic "
                "reports these and does not override them.",
            )
        if rejected:
            return CriticCheck(
                "no_constraint_violations", False, QUALIFYING,
                f"{len(rejected)} proposed action(s) were refused as infeasible by the "
                "simulator.",
                remedy="Show the refused actions alongside the plan.",
            )
        return CriticCheck(
            "no_constraint_violations", True, BLOCKING,
            "No hard-constraint violation was reported by the producing model.",
        )

    def _check_impact_claim(self, recommendation: Recommendation) -> CriticCheck:
        """A recommendation must claim a measurable benefit, or it is not one."""
        impact = recommendation.expected_impact
        if not impact:
            return CriticCheck(
                "impact_quantified", False, QUALIFYING,
                "No expected impact was quantified, so this cannot be scored against "
                "what actually happens.",
                remedy="Present as advisory context rather than as a recommended action.",
            )
        positive = [k for k, v in impact.items() if isinstance(v, (int, float)) and v > 0]
        if not positive:
            return CriticCheck(
                "impact_quantified", False, QUALIFYING,
                f"The claimed impact is not positive: {impact}.",
                remedy="State plainly that the action is neutral on the measured terms.",
            )
        return CriticCheck(
            "impact_quantified", True, QUALIFYING,
            f"Claims a measurable benefit: "
            + ", ".join(f"{k}={impact[k]}" for k in positive[:3]) + ".",
        )

    def _check_disagreement(
        self,
        recommendation: Recommendation,
        agent_results: Sequence[AgentResult],
    ) -> CriticCheck:
        """Whether the contributing agents actually agreed.

        Two agents reaching opposite conclusions is a real and common state --
        the weather agent sees a clearing window while the fleet agent sees a
        closing deadline -- and it should reach the operator as disagreement
        rather than being averaged into false consensus.
        """
        blocked = [r for r in agent_results if r.outcome == "blocked"]
        partial = [r for r in agent_results if r.outcome == "partial"]
        if blocked:
            return CriticCheck(
                "contributors_agree", False, QUALIFYING,
                f"{len(blocked)} contributing agent(s) could not run at all: "
                f"{', '.join(r.agent for r in blocked)}.",
                remedy="Show which evidence is missing rather than implying it was checked.",
            )
        if partial:
            return CriticCheck(
                "contributors_agree", False, QUALIFYING,
                f"{len(partial)} contributing agent(s) ran with missing evidence: "
                f"{', '.join(r.agent for r in partial)}.",
                remedy="Attach the gaps each agent reported.",
            )
        return CriticCheck(
            "contributors_agree", True, QUALIFYING,
            f"All {len(agent_results)} contributing agent(s) completed.",
        )

    @classmethod
    def describe(cls) -> Dict[str, Any]:
        return {
            "name": cls.name,
            "purpose": cls.purpose,
            "verdicts": list(VERDICTS),
            "checks": [
                "supported_by_evidence", "confidence_actionable", "evidence_fresh",
                "physical_envelope", "action_still_available",
                "no_constraint_violations", "impact_quantified", "contributors_agree",
            ],
            "note": (
                "The Critic reports hard-constraint violations and never relaxes them. "
                "It can only lower confidence, never raise it."
            ),
        }


def recommendation_from_agents(
    results: Sequence[AgentResult],
    *,
    kind: str,
    subject: str,
    action: str,
    values: Optional[Dict[str, Any]] = None,
    expected_impact: Optional[Dict[str, float]] = None,
    reason: str = "",
    evidence: Optional[Dict[str, Any]] = None,
) -> Recommendation:
    """Build a reviewable recommendation out of an agent chain's output.

    The confidence is the *minimum* across the contributing agents, not a mean:
    a chain is as reliable as its weakest evidence, and this is the same rule
    :func:`~src.portwatch_os.agents.base.propagate_confidence` applies inside an
    agent.
    """
    confidences = [r.confidence for r in results if r.confidence is not None]
    tools = sorted({call.tool for r in results for call in r.calls if call.ok})
    return Recommendation(
        kind=kind, subject=subject, action=action,
        values=dict(values or {}),
        expected_impact=dict(expected_impact or {}),
        confidence=min(confidences) if confidences else None,
        evidence_tools=tools,
        evidence=dict(evidence or {}),
        reason=reason,
    )


__all__ = [
    "APPROVED",
    "BLOCKING",
    "MAX_ARRIVAL_SHIFT_HOURS",
    "MIN_ACTIONABLE_CONFIDENCE",
    "MODIFIED",
    "QUALIFYING",
    "REJECTED",
    "SPEED_ENVELOPE_KN",
    "STALE_HOURS",
    "VERDICTS",
    "Critic",
    "CriticCheck",
    "CriticVerdict",
    "Recommendation",
    "recommendation_from_agents",
]
