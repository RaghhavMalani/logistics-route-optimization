"""Spatial commands: how an agent answers with the world instead of a paragraph.

"Show me the vessels affected by the Red Sea event" has a bad answer and a good
one. The bad answer is a paragraph listing six names, which the operator then
has to find on a chart themselves. The good answer is the chart changing: the
event focused, its cascade drawn, those six hulls lit.

So an agent run may carry spatial commands alongside its findings. They are
typed, small, and declarative -- a request to look at something, never a
description of how to draw it. Two properties matter:

**A command must be grounded in a tool result.** Every command names the tool
call that justifies it, and :func:`grounded` drops any that cannot point at one.
An agent that could emit ``FOCUS_VESSEL`` for a hull no tool returned would be
inventing a subject, which is the spatial equivalent of inventing a number --
and this system's whole claim is that it does not do that.

**The client is free to ignore them.** They are hints about attention, not
remote control of somebody's screen. A command referring to something outside
the viewer's scope simply does not resolve, and the visibility rules stay where
they are enforced rather than being re-litigated here.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from src.portwatch_os.agents.tools import ToolCall

#: Look at one world event and draw its consequence.
FOCUS_EVENT = "FOCUS_EVENT"
FOCUS_VESSEL = "FOCUS_VESSEL"
FOCUS_PORT = "FOCUS_PORT"
FOCUS_CHOKEPOINT = "FOCUS_CHOKEPOINT"
#: Draw a cascade that has already been computed.
SHOW_CASCADE = "SHOW_CASCADE"
SHOW_ROUTE = "SHOW_ROUTE"
#: Move the world clock. The value is hours from now.
SET_TIME = "SET_TIME"
#: Change what the world emphasises without navigating away from it.
SET_LENS = "SET_LENS"
#: Put two projections side by side.
COMPARE_SCENARIOS = "COMPARE_SCENARIOS"
#: Raise the attention queue, optionally filtered.
SHOW_ATTENTION = "SHOW_ATTENTION"
#: Drop the current selection and emphasis, returning the world to rest.
CLEAR_CONTEXT = "CLEAR_CONTEXT"

COMMANDS: Tuple[str, ...] = (
    FOCUS_EVENT,
    FOCUS_VESSEL,
    FOCUS_PORT,
    FOCUS_CHOKEPOINT,
    SHOW_CASCADE,
    SHOW_ROUTE,
    SET_TIME,
    SET_LENS,
    COMPARE_SCENARIOS,
    SHOW_ATTENTION,
    CLEAR_CONTEXT,
)

# --------------------------------------------------------------------------
# safety classes
# --------------------------------------------------------------------------

#: Changes only what the operator is looking at. Reversible by looking
#: elsewhere, and safe to run the moment an answer arrives.
UI = "UI"
#: Runs a model. Cheap, side-effect-free and still *not* automatic outside an
#: explicit simulation context: a projection that ran because a sentence was
#: phrased a certain way is a projection nobody asked for.
SIMULATION = "SIMULATION"
#: Reaches the world outside this screen -- an advisory to a master, a
#: committed plan. Never automatic, at any confidence, under any phrasing.
OPERATIONAL = "OPERATIONAL"

SAFETY_CLASSES: Tuple[str, ...] = (UI, SIMULATION, OPERATIONAL)

#: The classification is per command kind rather than per call, so a new
#: command cannot be added without someone deciding which of these it is.
#: :func:`safety_of` raises on an unclassified kind for exactly that reason.
COMMAND_SAFETY: Dict[str, str] = {
    FOCUS_EVENT: UI,
    FOCUS_VESSEL: UI,
    FOCUS_PORT: UI,
    FOCUS_CHOKEPOINT: UI,
    SHOW_CASCADE: UI,
    SHOW_ROUTE: UI,
    SET_TIME: UI,
    SET_LENS: UI,
    SHOW_ATTENTION: UI,
    CLEAR_CONTEXT: UI,
    # Branching the world is a model run, not a camera move.
    COMPARE_SCENARIOS: SIMULATION,
}


def safety_of(kind: str) -> str:
    """The safety class of a command kind.

    Deliberately raises rather than defaulting. A command that fell through to
    UI because nobody classified it would auto-execute, and the whole point of
    this table is that adding a capability forces that decision.
    """
    try:
        return COMMAND_SAFETY[kind]
    except KeyError:
        raise SpatialError(
            f"{kind!r} has no safety class. Every command must be classified "
            f"as one of {', '.join(SAFETY_CLASSES)} before it can be dispatched."
        ) from None

#: World lenses. A lens changes emphasis and what the agent reasons about; it
#: never replaces the world with a page.
OPERATIONS = "OPERATIONS"
WEATHER = "WEATHER"
SECURITY = "SECURITY"
CARGO = "CARGO"
FINANCIAL = "FINANCIAL"
INTELLIGENCE = "INTELLIGENCE"

LENSES: Tuple[str, ...] = (
    OPERATIONS, WEATHER, SECURITY, CARGO, FINANCIAL, INTELLIGENCE,
)


class SpatialError(ValueError):
    """A command was constructed that the world cannot carry out."""


@dataclass(frozen=True)
class SpatialCommand:
    """One request to change what the world is showing."""

    kind: str
    #: What the command acts on: an event id, a vessel id, a locode, an hour.
    subject: Optional[str] = None
    #: The tool call that justifies this command. Required -- see the module
    #: docstring for why an ungrounded command is not emitted at all.
    evidence_tool: str = ""
    #: Why the operator is being shown this, in their words.
    reason: str = ""
    params: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.kind not in COMMANDS:
            raise SpatialError(f"{self.kind!r} is not a spatial command")
        if self.kind == SET_LENS and self.subject not in LENSES:
            raise SpatialError(
                f"{self.subject!r} is not a lens; expected one of "
                f"{', '.join(LENSES)}"
            )
        # Constructing an unclassified command is refused here rather than at
        # dispatch, so the mistake surfaces where it was made.
        safety_of(self.kind)

    @property
    def safety(self) -> str:
        return safety_of(self.kind)

    @property
    def auto_executable(self) -> bool:
        """Whether a client may run this without asking anybody.

        Only view changes. A simulation needs an explicit simulation context and
        an operational action needs the human approval boundary that already
        exists -- neither becomes automatic because the same object happens to
        be called a "command".
        """
        return self.safety == UI

    def to_dict(self) -> Dict[str, Any]:
        return {
            "kind": self.kind,
            "subject": self.subject,
            "evidenceTool": self.evidence_tool,
            "reason": self.reason,
            "params": self.params,
            "safety": self.safety,
            "autoExecutable": self.auto_executable,
        }


def grounded(
    commands: Sequence[SpatialCommand],
    trace: Sequence[ToolCall],
) -> List[SpatialCommand]:
    """Keep only the commands a successful tool call justifies.

    The filter is the safety property. An agent that emitted FOCUS_VESSEL for a
    hull no tool returned would be inventing a subject, and a chart that flew to
    it would be presenting that invention as observation. A command whose tool
    failed is dropped for the same reason: a refusal is not evidence.
    """
    succeeded = {call.tool for call in trace if call.ok}
    return [
        command for command in commands
        if command.evidence_tool and command.evidence_tool in succeeded
    ]


def commands_from_trace(
    trace: Sequence[ToolCall],
    *,
    lens: str = OPERATIONS,
) -> List[SpatialCommand]:
    """Derive spatial commands from what an agent's tools actually returned.

    Deliberately mechanical. The alternative -- asking a model which parts of
    the world to highlight -- would let the chart drift from the computation,
    and the chart is the part an operator believes fastest.
    """
    commands: List[SpatialCommand] = []

    for call in trace:
        if not call.ok or call.result is None:
            continue

        if call.tool == "portwatch.global_eye.exposure":
            # One EventImpact, not a list: the tool answers about the event it
            # was asked about.
            impact = call.result if isinstance(call.result, dict) else {}
            event_id = impact.get("eventId")
            if event_id:
                commands.append(SpatialCommand(
                    kind=FOCUS_EVENT, subject=str(event_id),
                    evidence_tool=call.tool,
                    reason="the event this answer is about",
                ))
                commands.append(SpatialCommand(
                    kind=SHOW_CASCADE, subject=str(event_id),
                    evidence_tool=call.tool,
                    reason="its computed consequence across lanes, hulls and ports",
                ))
                for port in _rows(impact, "ports")[:1]:
                    code = port.get("portCode")
                    if code:
                        commands.append(SpatialCommand(
                            kind=FOCUS_PORT, subject=str(code),
                            evidence_tool=call.tool,
                            reason="the worst-affected destination port",
                        ))

        if call.tool == "portwatch.company.risk":
            # Rows are already ranked worst-first by the tool, so the head of
            # the list is the hull to look at.
            for row in _rows(call.result, "rows")[:1]:
                vessel_id = row.get("vesselId")
                if vessel_id:
                    commands.append(SpatialCommand(
                        kind=FOCUS_VESSEL, subject=str(vessel_id),
                        evidence_tool=call.tool,
                        reason="the most exposed hull in the fleet",
                    ))

        if call.tool in ("portwatch.port_twin.simulate", "portwatch.port_twin.state"):
            port = _port_of(call)
            if port:
                commands.append(SpatialCommand(
                    kind=FOCUS_PORT, subject=port, evidence_tool=call.tool,
                    reason="the port this answer is about",
                ))

    if commands:
        commands.append(SpatialCommand(
            kind=SET_LENS, subject=lens, evidence_tool=commands[0].evidence_tool,
            reason="the lens this answer is framed in",
        ))
    return grounded(commands, trace)


def _rows(result: Any, key: str) -> List[Dict[str, Any]]:
    if isinstance(result, dict):
        rows = result.get(key)
        if isinstance(rows, list):
            return [r for r in rows if isinstance(r, dict)]
    if isinstance(result, list):
        return [r for r in result if isinstance(r, dict)]
    return []


def _port_of(call: ToolCall) -> Optional[str]:
    port = call.arguments.get("port_code")
    return str(port) if port else None


__all__ = [
    "CLEAR_CONTEXT",
    "COMMANDS",
    "COMMAND_SAFETY",
    "OPERATIONAL",
    "SAFETY_CLASSES",
    "SIMULATION",
    "UI",
    "safety_of",
    "COMPARE_SCENARIOS",
    "CARGO",
    "FINANCIAL",
    "FOCUS_CHOKEPOINT",
    "FOCUS_EVENT",
    "FOCUS_PORT",
    "FOCUS_VESSEL",
    "INTELLIGENCE",
    "LENSES",
    "OPERATIONS",
    "SECURITY",
    "SET_LENS",
    "SET_TIME",
    "SHOW_ATTENTION",
    "SHOW_CASCADE",
    "SHOW_ROUTE",
    "SpatialCommand",
    "SpatialError",
    "WEATHER",
    "commands_from_trace",
    "grounded",
]
