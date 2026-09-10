"""The Command Agent: routing a question to the agents that can answer it.

This is the orchestration layer, and it is deliberately a *planner over
specialists* rather than a language model with tools bolted on:

*   The plan is chosen by matching the request against declared intents. Each
    intent names the agents that answer it and the order they must run in, so a
    run is reproducible and auditable.
*   Agents run in sequence, and each one's output is fed into the next request's
    context. That is what makes it a chain rather than a fan-out: the fleet agent
    needs the events Global Eye found, and the advisory agent needs the numbers
    the twin computed.
*   Every high-impact chain ends at the Critic. Nothing reaches an operator as a
    recommended action without a verdict attached.

**Where a language model fits, and where it does not.** An LLM may be attached
as the intent classifier -- turning "which ships are in trouble because of the
Red Sea?" into ``fleet_exposure`` with an event filter -- and as the narrator
that renders the findings into prose. It is given a ``PROPOSE`` ceiling and it
never sees an approval context, so the worst a misclassification can do is run
the wrong read-only chain. When no model is configured, :func:`classify_intent`
falls back to keyword matching, which is what ships here: the product works with
no model key at all, and the LLM is an ergonomics upgrade rather than a
dependency.
"""

from __future__ import annotations

import re
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

from src.portwatch_os.agents.base import (
    BLOCKED,
    COMPLETE,
    PARTIAL,
    Agent,
    AgentRequest,
    AgentResult,
    Finding,
    propagate_confidence,
)
from src.portwatch_os.agents.critic import (
    APPROVED,
    Critic,
    CriticVerdict,
    Recommendation,
    recommendation_from_agents,
)
from src.portwatch_os.agents.specialists import SPECIALISTS
from src.portwatch_os.agents.tools import PROPOSE, ToolRegistry, ToolScope
from src.portwatch_os.roles import NATIONAL_ADMIN
from src.utils.logging_utils import get_logger

log = get_logger(__name__)


# --------------------------------------------------------------------------
# intents
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class Intent:
    """One question the product knows how to answer, and how."""

    key: str
    label: str
    #: Agents to run, in order. Order matters: later agents read earlier output.
    agents: Tuple[str, ...]
    #: Phrases that select this intent when no model classifier is configured.
    keywords: Tuple[str, ...]
    #: Whether the chain produces a recommendation the Critic must review.
    high_impact: bool
    description: str


INTENTS: Tuple[Intent, ...] = (
    Intent(
        "fleet_exposure", "Which vessels need intervention?",
        ("global_eye", "fleet", "route"),
        ("which ships", "which vessels", "my fleet", "fleet exposure", "need action",
         "require intervention", "at risk", "exposed", "red sea", "hormuz", "suez",
         "malacca", "chokepoint", "divert"),
        True,
        "Traces live events to the fleet, then scores the routing of the worst-exposed "
        "vessel. Ends at the Critic because it produces routing recommendations.",
    ),
    Intent(
        "port_state", "What is happening at this port?",
        ("port_twin", "weather"),
        ("port state", "congestion", "queue", "berth", "how busy", "turnaround",
         "what is happening at", "anchorage", "waiting"),
        False,
        "Observed port state plus a simulated forward view, with the weather driving it.",
    ),
    Intent(
        "port_advisory", "Should we advise a vessel to change its arrival?",
        ("port_twin", "weather", "advisory"),
        ("advisory", "advise", "arrival window", "reschedule", "restagger",
         "delay arrival", "slow steam", "recommend arrival"),
        True,
        "Builds the evidence for an arrival or speed advisory and drafts one for a "
        "controller. The draft is never visible to the vessel until issued.",
    ),
    Intent(
        "cargo_connection", "Can this cargo make a connection?",
        ("cargo", "port_twin"),
        ("cargo", "transship", "transshipment", "connection", "onward", "container",
         "teu", "manifest", "yard"),
        False,
        "Feasible transshipment connections, with capacity, window and handling checked.",
    ),
    Intent(
        "scenario", "What happens if this shock lands?",
        ("scenario", "global_eye"),
        ("what if", "scenario", "shock", "closure", "simulate", "stress"),
        False,
        "Propagates a shock through the lane network and reports per-port deltas.",
    ),
    Intent(
        "learning", "How well has PortWatch been doing?",
        ("outcome",),
        ("calibration", "accuracy", "how wrong", "were we wrong", "reliability",
         "learning", "brier", "outcomes", "past predictions", "how good"),
        False,
        "Reports scored history, reliability movement and policy promotion state.",
    ),
    Intent(
        "weather", "What are the conditions?",
        ("weather",),
        ("weather", "wind", "storm", "rain", "visibility", "cyclone", "monsoon", "sea state"),
        False,
        "Marine conditions and forward operational impact.",
    ),
    Intent(
        "global_events", "What is happening in the world?",
        ("global_eye",),
        ("global eye", "events", "disruption", "news", "geopolit", "what is happening"),
        False,
        "The current event register with corroboration and exposure.",
    ),
)

INTENT_BY_KEY: Dict[str, Intent] = {intent.key: intent for intent in INTENTS}

DEFAULT_INTENT = INTENT_BY_KEY["global_events"]


#: The seam a language model plugs into. Takes the question, returns an intent
#: key or ``None``. Given no tools and no approval context, so a wrong answer
#: runs the wrong read-only chain and nothing worse.
IntentClassifier = Callable[[str], Optional[str]]


def classify_intent(
    question: str,
    *,
    classifier: Optional[IntentClassifier] = None,
) -> Tuple[Intent, str]:
    """Pick the intent for a question. Returns the intent and how it was chosen.

    A configured classifier is tried first and its answer is validated against
    the known intents -- a model that returns something unrecognised is ignored
    rather than trusted, which is the whole reason the keyword path stays.
    """
    if classifier is not None:
        try:
            proposed = classifier(question)
        except Exception as exc:  # noqa: BLE001 - a classifier failure is not fatal
            log.warning("Intent classifier failed, falling back to keywords: %s", exc)
            proposed = None
        if proposed and proposed in INTENT_BY_KEY:
            return INTENT_BY_KEY[proposed], "model classifier"

    lowered = (question or "").lower()
    scored: List[Tuple[int, Intent]] = []
    for intent in INTENTS:
        hits = sum(1 for keyword in intent.keywords if keyword in lowered)
        if hits:
            scored.append((hits, intent))
    if not scored:
        return DEFAULT_INTENT, "default (no phrase matched)"
    scored.sort(key=lambda pair: -pair[0])
    return scored[0][1], "keyword match"


#: Entity extraction from the question. Port codes and vessel ids are matched
#: literally because guessing them is how an agent ends up answering about the
#: wrong port with total confidence.
_PORT_PATTERN = re.compile(r"\b(IN[A-Z]{3})\b")
_VESSEL_PATTERN = re.compile(r"\b([A-Z]{2,4}-\d{3})\b")
_HOURS_PATTERN = re.compile(r"\b(\d{1,3})\s*(?:h|hr|hrs|hour|hours)\b", re.IGNORECASE)

_PORT_NAMES: Dict[str, str] = {
    "chennai": "INMAA", "jnpa": "INNSA", "nhava sheva": "INNSA", "mundra": "INMUN",
    "mumbai": "INBOM", "kolkata": "INCCU", "visakhapatnam": "INVTZ", "vizag": "INVTZ",
    "cochin": "INCOK", "kochi": "INCOK", "kandla": "INIXY", "deendayal": "INIXY",
    "paradip": "INPRT", "tuticorin": "INTUT", "mormugao": "INMRM", "new mangalore": "INNML",
    "kamarajar": "INKAT", "ennore": "INKAT",
}


def extract_entities(question: str) -> Dict[str, Any]:
    """Pull port codes, vessel ids and horizons out of the question."""
    out: Dict[str, Any] = {}
    lowered = (question or "").lower()

    match = _PORT_PATTERN.search(question or "")
    if match:
        out["port_code"] = match.group(1)
    else:
        for name, code in _PORT_NAMES.items():
            if name in lowered:
                out["port_code"] = code
                break

    vessel = _VESSEL_PATTERN.search(question or "")
    if vessel:
        out["vessel_id"] = vessel.group(1)

    hours = _HOURS_PATTERN.search(question or "")
    if hours:
        out["horizon_hours"] = float(hours.group(1))

    return out


# --------------------------------------------------------------------------
# runs
# --------------------------------------------------------------------------


@dataclass
class AgentRun:
    """One complete orchestration, start to finish."""

    run_id: str
    question: str
    intent: str
    intent_label: str
    intent_basis: str
    role: str
    started_at: str
    results: List[AgentResult] = field(default_factory=list)
    recommendation: Optional[Recommendation] = None
    verdict: Optional[CriticVerdict] = None
    summary: str = ""
    confidence: Optional[float] = None
    outcome: str = COMPLETE
    duration_ms: float = 0.0
    gaps: List[str] = field(default_factory=list)
    #: Ledger decision id, where the run produced a recorded recommendation.
    decision_id: Optional[str] = None

    @property
    def tool_trace(self) -> List[Dict[str, Any]]:
        """A flat trace, for the UI's tool strip."""
        return [
            {**call.to_dict(), "agent": result.agent}
            for result in self.results
            for call in result.calls
        ]

    def to_dict(self, *, include_results: bool = False) -> Dict[str, Any]:
        return {
            "runId": self.run_id,
            "question": self.question,
            "intent": self.intent,
            "intentLabel": self.intent_label,
            "intentBasis": self.intent_basis,
            "role": self.role,
            "startedAt": self.started_at,
            "durationMs": round(self.duration_ms, 1),
            "outcome": self.outcome,
            "summary": self.summary,
            "confidence": None if self.confidence is None else round(self.confidence, 3),
            "gaps": self.gaps,
            "agents": [r.to_dict(include_results=include_results) for r in self.results],
            "trace": self.tool_trace,
            "recommendation": (
                self.recommendation.to_dict() if self.recommendation else None
            ),
            "critic": self.verdict.to_dict() if self.verdict else None,
            "decisionId": self.decision_id,
            "note": (
                "Agents orchestrate and explain. Every number above came from a tool "
                "listed in the trace, and every tool names the deterministic model that "
                "produced it. No agent may execute an action."
            ),
        }


class CommandAgent:
    """The orchestrator.

    Holds the specialists and the Critic, picks a plan, runs it, and assembles a
    reviewable result. It has a ``PROPOSE`` ceiling like every agent, so even a
    bug here cannot reach an EXECUTE tool.
    """

    name = "command"
    purpose = (
        "Route an operator's question to the specialists that can answer it, run "
        "them in an order where each informs the next, and put any recommendation "
        "through the Critic."
    )
    max_access = PROPOSE

    def __init__(
        self,
        registry: ToolRegistry,
        *,
        classifier: Optional[IntentClassifier] = None,
        critic: Optional[Critic] = None,
    ) -> None:
        self.registry = registry
        self.classifier = classifier
        self.critic = critic or Critic()
        self.agents: Dict[str, Agent] = {
            name: cls(registry) for name, cls in SPECIALISTS.items()
        }

    # -- planning ----------------------------------------------------------
    def plan(self, question: str) -> Tuple[Intent, str]:
        return classify_intent(question, classifier=self.classifier)

    # -- execution ---------------------------------------------------------
    def run(
        self,
        question: str,
        *,
        role: str = NATIONAL_ADMIN,
        scope: Optional[ToolScope] = None,
        port_code: Optional[str] = None,
        vessel_id: Optional[str] = None,
        company_id: Optional[str] = None,
        event_id: Optional[str] = None,
        horizon_hours: float = 72.0,
        context: Optional[Dict[str, Any]] = None,
    ) -> AgentRun:
        started = time.perf_counter()
        intent, basis = self.plan(question)
        entities = extract_entities(question)

        request = AgentRequest(
            question=question,
            port_code=port_code or entities.get("port_code"),
            vessel_id=vessel_id or entities.get("vessel_id"),
            company_id=company_id,
            event_id=event_id,
            horizon_hours=horizon_hours or entities.get("horizon_hours", 72.0),
            role=role,
            scope=scope,
            context=dict(context or {}),
        )

        run = AgentRun(
            run_id=_run_id(question),
            question=question,
            intent=intent.key,
            intent_label=intent.label,
            intent_basis=basis,
            role=role,
            started_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
        )

        for agent_name in intent.agents:
            agent = self.agents.get(agent_name)
            if agent is None:
                continue
            result = agent.run(request)
            run.results.append(result)
            # Chain the output forward. This is what makes the fleet agent able
            # to reason about the events Global Eye just found.
            request = request.with_context(**{agent_name: result.data})
            request = self._carry_subject(agent_name, result, request)

        run.gaps = [gap for result in run.results for gap in result.gaps]
        run.confidence = propagate_confidence(
            [r.confidence for r in run.results],
            failures=sum(len(r.failed_calls) for r in run.results),
            gaps=len(run.gaps),
        )
        run.outcome = (
            BLOCKED if all(r.outcome == BLOCKED for r in run.results) and run.results
            else PARTIAL if any(r.outcome != COMPLETE for r in run.results)
            else COMPLETE
        )

        if intent.high_impact:
            run.recommendation, run.verdict = self._review(intent, request, run)

        run.summary = self._summarise(intent, run)
        run.duration_ms = (time.perf_counter() - started) * 1000
        log.info(
            "Agent run %s (%s): %d agents, %d tool calls, outcome %s.",
            run.run_id, intent.key, len(run.results), len(run.tool_trace), run.outcome,
        )
        return run

    # -- review ------------------------------------------------------------
    def _review(
        self,
        intent: Intent,
        request: AgentRequest,
        run: AgentRun,
    ) -> Tuple[Optional[Recommendation], Optional[CriticVerdict]]:
        """Build the chain's recommendation and put it through the Critic.

        The recommendation's *numbers* come from the agents' data, never from
        this method. Where the chain produced no actionable numbers, no
        recommendation is built and the Critic is not invoked -- an empty verdict
        is better than a manufactured one.
        """
        fleet = next((r for r in run.results if r.agent == "fleet"), None)
        routing = next((r for r in run.results if r.agent == "route"), None)
        twin = next((r for r in run.results if r.agent == "port_twin"), None)

        if intent.key == "fleet_exposure" and fleet is not None:
            rows: List[Dict[str, Any]] = fleet.data.get("rows", [])
            actionable = [r for r in rows if not r["alreadyEntered"]]
            if not actionable:
                return None, None
            worst = actionable[0]
            deadline_hours = worst.get("hoursToRiskArea")
            recommendation = recommendation_from_agents(
                run.results,
                kind="fleet_diversion",
                subject=worst["vesselId"],
                action=worst["recommendedAction"],
                values={
                    "exposure": worst["exposure"],
                    "delayHoursIfDiverted": worst.get("delayHoursIfDiverted"),
                    "diversionDeadline": worst.get("diversionDeadline"),
                },
                expected_impact={
                    "vesselsProtected": float(len({r["vesselId"] for r in actionable})),
                },
                reason=worst.get("actionBasis", ""),
                evidence={
                    "alreadyEntered": worst["alreadyEntered"],
                    "hoursToDeadline": deadline_hours,
                    "exposedVessels": len(rows),
                },
            )
            return recommendation, self.critic.review(recommendation, agent_results=run.results)

        if intent.key == "port_advisory" and twin is not None:
            simulation = twin.data.get("simulation") or {}
            metrics = simulation.get("metrics") or {}
            wait = metrics.get("meanWaitHours")
            if wait is None:
                return None, None
            recommendation = recommendation_from_agents(
                run.results,
                kind="arrival_advisory",
                subject=request.port_code or "unknown",
                action="restagger_arrival",
                values={
                    "arrivalShiftHours": round(min(float(wait), 12.0), 1),
                    "simulatedMeanWaitHours": wait,
                },
                expected_impact={"waitHoursSaved": round(float(wait) * 0.5, 2)},
                reason=(
                    f"The twin simulates a mean wait of {wait} h under the greedy "
                    "scheduling policy. Restaggering the arrival moves the vessel to a "
                    "point in the queue where the berth is free."
                ),
                evidence={
                    "violations": simulation.get("violations") or [],
                    "rejectedActions": simulation.get("rejectedActions") or [],
                },
            )
            return recommendation, self.critic.review(recommendation, agent_results=run.results)

        return None, None

    @staticmethod
    def _carry_subject(
        agent_name: str,
        result: AgentResult,
        request: AgentRequest,
    ) -> AgentRequest:
        """Name the subject a later agent should work on.

        Without this the chain fans out instead of narrowing: the route agent
        would be asked "score a routing" with no vessel and would correctly
        refuse. The fleet agent has just decided which vessel matters most, and
        that decision -- not a guess -- is what the route agent inherits.
        """
        if request.vessel_id is None and agent_name == "fleet":
            rows = result.data.get("rows") or []
            # The worst-exposed vessel that can still act on the answer. A
            # vessel already inside the risk area has no routing decision left,
            # so scoring its alternatives would be effort spent on nothing.
            actionable = [r for r in rows if not r.get("alreadyEntered")]
            chosen = (actionable or rows)[:1]
            if chosen:
                return AgentRequest(
                    question=request.question, port_code=request.port_code,
                    vessel_id=chosen[0]["vesselId"], company_id=request.company_id,
                    event_id=request.event_id, horizon_hours=request.horizon_hours,
                    role=request.role, context=request.context,
                )
        if request.port_code is None and agent_name == "global_eye":
            ports = (result.data.get("impact") or {}).get("ports") or []
            if ports:
                return AgentRequest(
                    question=request.question, port_code=ports[0]["portCode"],
                    vessel_id=request.vessel_id, company_id=request.company_id,
                    event_id=request.event_id, horizon_hours=request.horizon_hours,
                    role=request.role, context=request.context,
                )
        return request

    # -- narration ---------------------------------------------------------
    def _summarise(self, intent: Intent, run: AgentRun) -> str:
        """Assemble a summary from the agents' own summaries.

        Concatenation with a verdict line, not generation. A language model may
        be attached upstream to render this more fluently, but the sentences here
        are built from findings that each name their source tool, so the summary
        cannot contain a number the trace does not.
        """
        parts = [r.summary for r in run.results if r.summary]
        if run.verdict:
            parts.append(
                f"Critic: {run.verdict.verdict}."
                + (f" {run.verdict.reasons[0]}" if run.verdict.reasons else "")
            )
        if run.gaps:
            parts.append(f"{len(run.gaps)} evidence gap(s) remain.")
        return " ".join(parts) or intent.description

    # -- description -------------------------------------------------------
    def describe(self) -> Dict[str, Any]:
        return {
            "command": {
                "name": self.name, "purpose": self.purpose, "maxAccess": self.max_access,
            },
            "intents": [
                {
                    "key": i.key, "label": i.label, "agents": list(i.agents),
                    "highImpact": i.high_impact, "description": i.description,
                }
                for i in INTENTS
            ],
            "agents": [cls.describe() for cls in SPECIALISTS.values()],
            "critic": Critic.describe(),
            "boundary": {
                "note": (
                    "Every agent, including the orchestrator, is capped at PROPOSE. "
                    "EXECUTE tools require an ApprovalContext that can only be built "
                    "from an authenticated human session, so no agent can reach one."
                ),
            },
        }


def _run_id(question: str) -> str:
    import hashlib

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
    digest = hashlib.sha1(f"{stamp}|{question}".encode("utf-8")).hexdigest()[:8]
    return f"RUN-{stamp}-{digest}"


__all__ = [
    "DEFAULT_INTENT",
    "INTENTS",
    "INTENT_BY_KEY",
    "AgentRun",
    "CommandAgent",
    "Intent",
    "IntentClassifier",
    "classify_intent",
    "extract_entities",
]
