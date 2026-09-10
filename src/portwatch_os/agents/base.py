"""What an agent is, and what it is not allowed to be.

An agent in this system does four things:

    1.  decides which tools to call, and in what order;
    2.  passes results between them;
    3.  reconciles what comes back, including disagreement and absence;
    4.  says what it found, with the provenance of every number.

It does **not** compute operational numbers. Every figure an agent reports came
out of a tool, and every tool names the deterministic module that produced it.
:meth:`Agent.run` returns an :class:`AgentResult` whose ``findings`` are values
lifted from tool results -- there is no arithmetic in an agent subclass, and the
tests check that the numbers in an agent's output appear in its trace.

Confidence propagates rather than being asserted. An agent's confidence is
bounded by the worst input it relied on, because a chain of reasoning is no more
reliable than its weakest evidence, and an agent that reported 0.9 off a stale
artefact would be worse than useless.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Sequence, Tuple

from src.portwatch_os.agents.tools import (
    PROPOSE,
    READ,
    ApprovalContext,
    ToolCall,
    ToolRegistry,
)
from src.portwatch_os.roles import NATIONAL_ADMIN

#: What an agent concluded about its own output.
COMPLETE = "complete"
PARTIAL = "partial"
BLOCKED = "blocked"

OUTCOMES: Tuple[str, ...] = (COMPLETE, PARTIAL, BLOCKED)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass
class Finding:
    """One thing an agent established, and where it came from.

    ``source_tool`` is not decoration. It is how a reader -- and the test suite --
    checks that the agent did not make the number up.
    """

    label: str
    value: Any
    source_tool: str
    #: One line on what this means operationally.
    detail: str = ""
    confidence: Optional[float] = None
    unit: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "label": self.label,
            "value": self.value,
            "sourceTool": self.source_tool,
            "detail": self.detail,
            "confidence": self.confidence,
            "unit": self.unit,
        }


@dataclass
class AgentResult:
    """What one agent produced in one run."""

    agent: str
    outcome: str
    summary: str
    findings: List[Finding] = field(default_factory=list)
    calls: List[ToolCall] = field(default_factory=list)
    #: Bounded by the worst evidence. See :func:`propagate_confidence`.
    confidence: Optional[float] = None
    #: Things the agent could not establish, and why. Never silently dropped.
    gaps: List[str] = field(default_factory=list)
    #: Structured output for the next agent in the chain.
    data: Dict[str, Any] = field(default_factory=dict)
    ran_at: str = field(default_factory=utc_now)

    @property
    def failed_calls(self) -> List[ToolCall]:
        return [c for c in self.calls if not c.ok]

    @property
    def unavailable_tools(self) -> List[str]:
        return sorted({c.tool for c in self.calls if c.unavailable})

    def to_dict(self, *, include_results: bool = False) -> Dict[str, Any]:
        return {
            "agent": self.agent,
            "outcome": self.outcome,
            "summary": self.summary,
            "confidence": None if self.confidence is None else round(self.confidence, 3),
            "findings": [f.to_dict() for f in self.findings],
            "gaps": self.gaps,
            "trace": [c.to_dict(include_result=include_results) for c in self.calls],
            "toolsUsed": sorted({c.tool for c in self.calls}),
            "unavailableTools": self.unavailable_tools,
            "ranAt": self.ran_at,
            "data": self.data if include_results else {},
        }


def propagate_confidence(
    inputs: Sequence[Optional[float]],
    *,
    failures: int = 0,
    gaps: int = 0,
) -> Optional[float]:
    """Combine input confidences into an output confidence.

    Two rules, both conservative on purpose:

    *   The result is bounded above by the *minimum* input confidence. A chain is
        as weak as its weakest link, and taking a mean would let three confident
        reads paper over one stale one.
    *   Each failed tool call and each unfilled gap costs a further multiplier.
        An answer assembled from half the evidence is not as good as one
        assembled from all of it, and the number should say so.

    Returns ``None`` when there is no evidence at all, which the caller must
    render as "unknown" rather than as zero.
    """
    known = [c for c in inputs if c is not None]
    if not known:
        return None
    floor = min(known)
    penalty = (0.82 ** failures) * (0.9 ** gaps)
    return float(max(0.0, min(1.0, floor * penalty)))


class Agent:
    """Base class. Subclasses implement :meth:`run` and nothing else.

    ``allowed_tools`` is the agent's own declaration of what it needs, checked
    against the registry at construction. It is documentation that cannot go
    stale: an agent that names a tool the registry does not have fails loudly at
    startup rather than silently at 3 a.m.
    """

    name: str = "agent"
    purpose: str = ""
    allowed_tools: Tuple[str, ...] = ()
    #: The highest access level this agent may reach. Specialists are READ or
    #: SIMULATE; only the advisory agent reaches PROPOSE, and nothing reaches
    #: EXECUTE.
    max_access: str = READ
    failure_modes: Tuple[str, ...] = ()

    def __init__(self, registry: ToolRegistry) -> None:
        self.registry = registry
        missing = [name for name in self.allowed_tools if registry.get(name) is None]
        if missing:
            raise ValueError(
                f"{self.name} declares tools that are not registered: "
                f"{', '.join(missing)}"
            )

    # -- tool access -------------------------------------------------------
    def call(
        self,
        tool: str,
        arguments: Optional[Dict[str, Any]] = None,
        *,
        trace: Optional[List[ToolCall]] = None,
    ) -> ToolCall:
        """Invoke a tool, refusing anything this agent did not declare.

        The declaration is enforced rather than advisory. An agent that reached
        for a tool outside its remit would be a capability escalation, and the
        refusal is recorded in the trace so it is visible rather than silent.
        """
        if tool not in self.allowed_tools:
            call = ToolCall(
                tool=tool, access="DENIED", arguments=dict(arguments or {}),
                ok=False, duration_ms=0.0,
                error=(
                    f"{self.name} is not permitted to call {tool}. Its declared tools "
                    f"are: {', '.join(self.allowed_tools)}"
                ),
            )
        else:
            call = self.registry.call(tool, arguments, max_access=self.max_access)
        if trace is not None:
            trace.append(call)
        return call

    def run(self, request: "AgentRequest") -> AgentResult:  # pragma: no cover - abstract
        raise NotImplementedError

    # -- description -------------------------------------------------------
    @classmethod
    def describe(cls) -> Dict[str, Any]:
        """The agent card. Rendered in the UI and in docs/AGENTIC_AI.md."""
        return {
            "name": cls.name,
            "purpose": cls.purpose,
            "allowedTools": list(cls.allowed_tools),
            "maxAccess": cls.max_access,
            "failureModes": list(cls.failure_modes),
        }


@dataclass
class AgentRequest:
    """Everything an agent needs to run, and nothing it should not have.

    Notably absent: any approval context. Agents cannot be handed one, which is
    what makes the EXECUTE boundary structural rather than procedural.
    """

    #: The operator's question, verbatim.
    question: str = ""
    port_code: Optional[str] = None
    vessel_id: Optional[str] = None
    company_id: Optional[str] = None
    event_id: Optional[str] = None
    horizon_hours: float = 72.0
    #: The role the answer is for. Changes emphasis, never the numbers.
    role: str = NATIONAL_ADMIN
    #: Output from earlier agents in the same run.
    context: Dict[str, Any] = field(default_factory=dict)

    def with_context(self, **updates: Any) -> "AgentRequest":
        return AgentRequest(
            question=self.question, port_code=self.port_code, vessel_id=self.vessel_id,
            company_id=self.company_id, event_id=self.event_id,
            horizon_hours=self.horizon_hours, role=self.role,
            context={**self.context, **updates},
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "question": self.question, "portCode": self.port_code,
            "vesselId": self.vessel_id, "companyId": self.company_id,
            "eventId": self.event_id, "horizonHours": self.horizon_hours,
            "role": self.role,
        }


def summarise_gaps(calls: Sequence[ToolCall]) -> List[str]:
    """Turn failed calls into sentences an operator can act on."""
    gaps: List[str] = []
    for call in calls:
        if call.ok:
            continue
        if call.unavailable:
            gaps.append(f"{call.tool} is unavailable: {call.error}")
        else:
            gaps.append(f"{call.tool} failed: {call.error}")
    return gaps


__all__ = [
    "BLOCKED",
    "COMPLETE",
    "OUTCOMES",
    "PARTIAL",
    "Agent",
    "AgentRequest",
    "AgentResult",
    "Finding",
    "propagate_confidence",
    "summarise_gaps",
    "utc_now",
]
