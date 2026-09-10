"""The tool layer, and the safety boundary that runs through it.

Every capability an agent has is a tool registered here. Agents contain no
business logic: they choose which tools to call, in what order, and how to
reconcile what comes back. The numbers come from the deterministic models the
tools wrap.

**The four-way split is the safety model, and it is enforced at call time.**

    READ      Observe. No state changes, no side effects. Always available.
    SIMULATE  Run a model or a what-if. Still no state changes, but expensive
              enough that it is separated from READ.
    PROPOSE   Produce a draft for a human to review. Creates a record in a
              pending state; nothing reaches an operator or a vessel.
    EXECUTE   Act. Sends an approved advisory, commits a plan. Requires an
              explicit approval context naming the human who approved it, and
              :func:`ToolRegistry.call` refuses without one.

An LLM orchestrator can reach READ, SIMULATE and PROPOSE freely. It can never
reach EXECUTE, because :class:`ApprovalContext` cannot be constructed from model
output -- it is built by the API from an authenticated session, and the registry
checks its provenance flag. That is the line the mission draws, and it is a
runtime check rather than a docstring.
"""

from __future__ import annotations

import inspect
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

from src.utils.logging_utils import get_logger

log = get_logger(__name__)

READ = "READ"
SIMULATE = "SIMULATE"
PROPOSE = "PROPOSE"
EXECUTE = "EXECUTE"

ACCESS_LEVELS: Tuple[str, ...] = (READ, SIMULATE, PROPOSE, EXECUTE)

#: Ordering, so "at most PROPOSE" is expressible.
_LEVEL_RANK: Dict[str, int] = {level: index for index, level in enumerate(ACCESS_LEVELS)}


class ToolError(RuntimeError):
    """A tool failed. Carries whether the failure is the caller's fault."""

    def __init__(self, message: str, *, recoverable: bool = True) -> None:
        super().__init__(message)
        self.recoverable = recoverable


class ToolUnavailable(ToolError):
    """The tool exists but its data does not. Distinct from a bug.

    An agent must be able to tell "the weather artefact has not been exported"
    from "the weather tool crashed", because the first is a state the product
    reports honestly and the second is a defect.
    """


class ApprovalRequired(ToolError):
    """An EXECUTE tool was called without a human approval context."""

    def __init__(self, tool_name: str) -> None:
        super().__init__(
            f"{tool_name} is an EXECUTE tool and requires an approval context naming "
            "the human who authorised it. Model-driven callers cannot construct one.",
            recoverable=False,
        )


@dataclass(frozen=True)
class ApprovalContext:
    """Proof that a human authorised an EXECUTE call.

    Built by the API from an authenticated session and never from anything a
    model produced. ``human_verified`` is the flag the registry checks; it is
    set only by :func:`approval_from_session`, which requires a real session
    identifier. An agent constructing this object directly gets
    ``human_verified=False`` and the call is refused.
    """

    actor: str
    actor_role: str
    #: The session the approval came from. Absent means it did not come from one.
    session_id: Optional[str] = None
    human_verified: bool = False
    reason: Optional[str] = None
    #: The specific artefact being approved, e.g. an advisory id.
    subject: Optional[str] = None
    #: The authenticated operator's own scope, carried from the session that
    #: authenticated them. An EXECUTE handler must authorise against *this*,
    #: never against a field read off the record being acted on -- deriving the
    #: scope from the target makes the store's authorisation check vacuous.
    port_code: Optional[str] = None
    organisation: Optional[str] = None
    vessel_ids: Tuple[str, ...] = ()
    is_admin: bool = False

    def authorises(self, subject: str) -> bool:
        """Whether this approval was granted for ``subject`` specifically.

        An approval with no subject is a blanket mandate and authorises nothing
        in particular; handlers that act on a named record require a match.
        """
        return bool(self.subject) and self.subject == subject

    def to_dict(self) -> Dict[str, Any]:
        return {
            "actor": self.actor,
            "actorRole": self.actor_role,
            "sessionId": self.session_id,
            "humanVerified": self.human_verified,
            "reason": self.reason,
            "subject": self.subject,
            "portCode": self.port_code,
            "organisation": self.organisation,
            "vesselIds": list(self.vessel_ids),
            "isAdmin": self.is_admin,
        }


def approval_from_session(
    *,
    actor: str,
    actor_role: str,
    session_id: str,
    subject: Optional[str] = None,
    reason: Optional[str] = None,
    port_code: Optional[str] = None,
    organisation: Optional[str] = None,
    vessel_ids: Optional[Sequence[str]] = None,
    is_admin: bool = False,
) -> ApprovalContext:
    """The only way to produce a verified approval context.

    Called by an API route that has already authenticated the session. There is
    deliberately no path from agent output to this function: an agent that wants
    something executed has to produce a PROPOSE draft and let a person approve
    it through the interface.
    """
    if not actor or not session_id:
        raise ApprovalRequired("approval_from_session")
    return ApprovalContext(
        actor=actor,
        actor_role=actor_role,
        session_id=session_id,
        human_verified=True,
        reason=reason,
        subject=subject,
        port_code=port_code,
        organisation=organisation,
        vessel_ids=tuple(vessel_ids or ()),
        is_admin=is_admin,
    )


@dataclass
class ToolSpec:
    """One registered capability."""

    name: str
    access: str
    summary: str
    handler: Callable[..., Any]
    #: Argument names and a one-line description each, for the MCP schema.
    arguments: Dict[str, str] = field(default_factory=dict)
    required: Tuple[str, ...] = ()
    #: What the tool returns, in one line.
    returns: str = ""
    #: The deterministic module the numbers actually come from. Shown in traces
    #: so a reader can see that no agent invented them.
    computed_by: str = ""
    #: Known failure modes, so an agent can plan around them rather than retrying.
    failure_modes: Tuple[str, ...] = ()

    def to_schema(self) -> Dict[str, Any]:
        """JSON-schema-ish description, for MCP tool listing."""
        return {
            "name": self.name,
            "description": self.summary,
            "access": self.access,
            "computedBy": self.computed_by,
            "returns": self.returns,
            "failureModes": list(self.failure_modes),
            "inputSchema": {
                "type": "object",
                "properties": {
                    key: {"type": "string", "description": description}
                    for key, description in self.arguments.items()
                },
                "required": list(self.required),
            },
        }


@dataclass
class ToolCall:
    """One invocation, recorded for the trace."""

    tool: str
    access: str
    arguments: Dict[str, Any]
    ok: bool
    duration_ms: float
    result: Any = None
    error: Optional[str] = None
    unavailable: bool = False
    computed_by: str = ""

    def to_dict(self, *, include_result: bool = False) -> Dict[str, Any]:
        payload: Dict[str, Any] = {
            "tool": self.tool,
            "access": self.access,
            "arguments": _safe(self.arguments),
            "ok": self.ok,
            "durationMs": round(self.duration_ms, 2),
            "error": self.error,
            "unavailable": self.unavailable,
            "computedBy": self.computed_by,
        }
        if include_result:
            payload["result"] = _safe(self.result)
        return payload


class ToolRegistry:
    """Every tool the agents and MCP share.

    One registry, so the capability an agent has and the capability exposed over
    MCP are the same object with the same access level. Two registries would
    eventually disagree, and the one that disagreed would be the one with the
    EXECUTE tool in it.
    """

    def __init__(self) -> None:
        self._tools: Dict[str, ToolSpec] = {}

    def register(
        self,
        name: str,
        access: str,
        summary: str,
        *,
        arguments: Optional[Dict[str, str]] = None,
        required: Sequence[str] = (),
        returns: str = "",
        computed_by: str = "",
        failure_modes: Sequence[str] = (),
    ) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
        if access not in ACCESS_LEVELS:
            raise ValueError(f"unknown access level {access}")

        def decorator(handler: Callable[..., Any]) -> Callable[..., Any]:
            self._tools[name] = ToolSpec(
                name=name, access=access, summary=summary, handler=handler,
                arguments=dict(arguments or {}), required=tuple(required),
                returns=returns, computed_by=computed_by,
                failure_modes=tuple(failure_modes),
            )
            return handler

        return decorator

    def add(self, spec: ToolSpec) -> None:
        self._tools[spec.name] = spec

    def get(self, name: str) -> Optional[ToolSpec]:
        return self._tools.get(name)

    def names(self, *, max_access: Optional[str] = None) -> List[str]:
        limit = _LEVEL_RANK.get(max_access or EXECUTE, _LEVEL_RANK[EXECUTE])
        return sorted(
            name for name, spec in self._tools.items()
            if _LEVEL_RANK[spec.access] <= limit
        )

    def specs(self, *, access: Optional[str] = None) -> List[ToolSpec]:
        return sorted(
            (s for s in self._tools.values() if access is None or s.access == access),
            key=lambda s: s.name,
        )

    def schema(self, *, max_access: Optional[str] = None) -> List[Dict[str, Any]]:
        limit = _LEVEL_RANK.get(max_access or EXECUTE, _LEVEL_RANK[EXECUTE])
        return [
            spec.to_schema() for spec in self.specs()
            if _LEVEL_RANK[spec.access] <= limit
        ]

    def call(
        self,
        name: str,
        arguments: Optional[Dict[str, Any]] = None,
        *,
        approval: Optional[ApprovalContext] = None,
        max_access: str = PROPOSE,
    ) -> ToolCall:
        """Invoke a tool, with the access boundary checked before anything runs.

        ``max_access`` is the ceiling the *caller* is allowed. An LLM
        orchestrator is constructed with ``PROPOSE``, so an EXECUTE tool is not
        merely refused at the approval check -- it is not reachable at all.
        """
        arguments = dict(arguments or {})
        spec = self._tools.get(name)
        started = time.perf_counter()

        if spec is None:
            return ToolCall(
                tool=name, access="UNKNOWN", arguments=arguments, ok=False,
                duration_ms=(time.perf_counter() - started) * 1000,
                error=(
                    f"no tool named {name}. Available: "
                    f"{', '.join(self.names(max_access=max_access))}"
                ),
            )

        ceiling = _LEVEL_RANK.get(max_access, _LEVEL_RANK[PROPOSE])
        if _LEVEL_RANK[spec.access] > ceiling:
            return ToolCall(
                tool=name, access=spec.access, arguments=arguments, ok=False,
                duration_ms=(time.perf_counter() - started) * 1000,
                computed_by=spec.computed_by,
                error=(
                    f"{name} is a {spec.access} tool and this caller is limited to "
                    f"{max_access}. Produce a PROPOSE draft for human approval instead."
                ),
            )

        if spec.access == EXECUTE:
            if approval is None or not approval.human_verified:
                return ToolCall(
                    tool=name, access=spec.access, arguments=arguments, ok=False,
                    duration_ms=(time.perf_counter() - started) * 1000,
                    computed_by=spec.computed_by,
                    error=str(ApprovalRequired(name)),
                )
            arguments = {**arguments, "approval": approval}

        missing = [key for key in spec.required if key not in arguments]
        if missing:
            return ToolCall(
                tool=name, access=spec.access, arguments=arguments, ok=False,
                duration_ms=(time.perf_counter() - started) * 1000,
                computed_by=spec.computed_by,
                error=f"{name} requires {', '.join(missing)}",
            )

        try:
            accepted = _accepted_arguments(spec.handler, arguments)
            result = spec.handler(**accepted)
            return ToolCall(
                tool=name, access=spec.access, arguments=arguments, ok=True,
                duration_ms=(time.perf_counter() - started) * 1000,
                result=result, computed_by=spec.computed_by,
            )
        except ToolUnavailable as exc:
            return ToolCall(
                tool=name, access=spec.access, arguments=arguments, ok=False,
                duration_ms=(time.perf_counter() - started) * 1000,
                error=str(exc), unavailable=True, computed_by=spec.computed_by,
            )
        except Exception as exc:  # noqa: BLE001 - a tool failure is data, not a crash
            log.warning("Tool %s failed: %s", name, exc)
            return ToolCall(
                tool=name, access=spec.access, arguments=arguments, ok=False,
                duration_ms=(time.perf_counter() - started) * 1000,
                error=f"{type(exc).__name__}: {exc}", computed_by=spec.computed_by,
            )


def _accepted_arguments(
    handler: Callable[..., Any],
    arguments: Dict[str, Any],
) -> Dict[str, Any]:
    """Drop arguments the handler does not take.

    Agents assemble argument dicts from context and routinely carry a key one
    tool needs and another does not. Filtering here is kinder than a TypeError
    the agent cannot act on, and the trace still records what was passed.
    """
    try:
        signature = inspect.signature(handler)
    except (TypeError, ValueError):
        return arguments
    if any(p.kind is inspect.Parameter.VAR_KEYWORD for p in signature.parameters.values()):
        return arguments
    return {k: v for k, v in arguments.items() if k in signature.parameters}


def _safe(value: Any, depth: int = 0) -> Any:
    """Make a value JSON-safe and bounded, for a trace that has to be readable."""
    if depth > 6:
        return "..."
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, ApprovalContext):
        return value.to_dict()
    if isinstance(value, dict):
        return {str(k): _safe(v, depth + 1) for k, v in list(value.items())[:60]}
    if isinstance(value, (list, tuple)):
        return [_safe(v, depth + 1) for v in list(value)[:60]]
    if hasattr(value, "to_dict"):
        try:
            return _safe(value.to_dict(), depth + 1)
        except Exception:  # noqa: BLE001
            return str(value)[:400]
    return str(value)[:400]


__all__ = [
    "ACCESS_LEVELS",
    "EXECUTE",
    "PROPOSE",
    "READ",
    "SIMULATE",
    "ApprovalContext",
    "ApprovalRequired",
    "ToolCall",
    "ToolError",
    "ToolRegistry",
    "ToolSpec",
    "ToolUnavailable",
    "approval_from_session",
]
