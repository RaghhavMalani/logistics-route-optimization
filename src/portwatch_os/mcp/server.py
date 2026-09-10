"""PortWatch over Model Context Protocol.

Exposes the same :class:`~src.portwatch_os.agents.tools.ToolRegistry` the
internal agents use. One registry, so a capability cannot exist over MCP that
does not exist internally, or carry a different access level there.

**What an MCP client can and cannot do.** The server is constructed with a
ceiling, defaulting to ``PROPOSE``. At that ceiling the EXECUTE tools are not
merely refused when called -- they are absent from ``tools/list``, so a client
never sees a capability it cannot use. Raising the ceiling to EXECUTE requires
running the server with ``--allow-execute`` *and* every call then supplying an
approval context; a model client cannot construct one, which is the point.

The transport is stdio JSON-RPC, which is what MCP clients speak. The protocol
surface is small on purpose: ``initialize``, ``tools/list``, ``tools/call``,
``resources/list`` and ``resources/read``. There is no third-party MCP SDK
dependency, because the protocol at this level is a few JSON shapes and adding a
dependency for them would be worse than writing them out.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from typing import Any, Callable, Dict, Iterable, List, Optional, TextIO

from src.portwatch_os.agents.portwatch_tools import build_registry
from src.portwatch_os.agents.tools import (
    ACCESS_LEVELS,
    EXECUTE,
    PROPOSE,
    READ,
    SIMULATE,
    ApprovalContext,
    ToolRegistry,
    ToolScope,
    approval_from_session,
)
from src.portwatch_os.roles import NATIONAL_ADMIN, WORKSPACE_ROLES, is_workspace_role

PROTOCOL_VERSION = "2024-11-05"

SERVER_INFO = {
    "name": "india-portwatch",
    "version": "2.0.0",
}

SERVER_INSTRUCTIONS = """\
India PortWatch — agentic maritime operations.

Tools are split by what they do to the world:

  READ      observe. No side effects.
  SIMULATE  run a model or a what-if. No side effects.
  PROPOSE   create a draft for a human to review. Nothing reaches an operator.
  EXECUTE   act. Requires an approval context naming the human who authorised it,
            and is not exposed at the default ceiling.

Numbers come from deterministic models, never from a language model. Every tool
declares the module that computed its result in `computedBy`. Where an artefact
is missing, the tool says so rather than returning a plausible empty result.

Data honesty: vessel traffic in this deployment is simulated, port twin geometry
is schematic, and cargo manifests are demo data. Each tool's result carries the
relevant disclaimer. Do not present any of it as observed AIS or as a surveyed
port plan.
"""


# --------------------------------------------------------------------------
# resources
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class Resource:
    """A read-only document an MCP client can fetch."""

    uri: str
    name: str
    description: str
    mime_type: str
    loader: Callable[[], str]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "uri": self.uri, "name": self.name,
            "description": self.description, "mimeType": self.mime_type,
        }


def _build_resources(registry: ToolRegistry, max_access: str) -> List[Resource]:
    from src.portwatch_os.agents.orchestrator import CommandAgent

    def catalogue() -> str:
        return json.dumps(registry.schema(max_access=max_access), indent=2)

    def agents() -> str:
        return json.dumps(CommandAgent(registry).describe(), indent=2)

    def honesty() -> str:
        call = registry.call("portwatch.provenance.get", max_access=READ)
        return json.dumps(
            {
                "note": (
                    "The provenance state of every source in the current run. "
                    "LIVE / CACHED_LIVE / STALE / SYNTHETIC / UNAVAILABLE."
                ),
                "available": call.ok,
                "error": call.error,
                "sources": call.result if call.ok else None,
            },
            indent=2, default=str,
        )

    def boundary() -> str:
        return json.dumps(
            {
                "accessLevels": list(ACCESS_LEVELS),
                "ceiling": max_access,
                "exposed": {
                    level: [s.name for s in registry.specs(access=level)]
                    for level in ACCESS_LEVELS
                    if ACCESS_LEVELS.index(level) <= ACCESS_LEVELS.index(max_access)
                },
                "withheld": {
                    level: [s.name for s in registry.specs(access=level)]
                    for level in ACCESS_LEVELS
                    if ACCESS_LEVELS.index(level) > ACCESS_LEVELS.index(max_access)
                },
                "rule": (
                    "EXECUTE tools require an ApprovalContext built from an "
                    "authenticated human session. A model client cannot construct "
                    "one, so an EXECUTE call from a model is refused even when the "
                    "ceiling permits the tool."
                ),
            },
            indent=2,
        )

    return [
        Resource("portwatch://tools", "Tool catalogue",
                 "Every exposed tool with its access level and computing module.",
                 "application/json", catalogue),
        Resource("portwatch://agents", "Agent architecture",
                 "The orchestrator, the specialists, the Critic and the boundary.",
                 "application/json", agents),
        Resource("portwatch://provenance", "Data provenance",
                 "What is live, cached, stale, simulated or unavailable in this run.",
                 "application/json", honesty),
        Resource("portwatch://boundary", "Access boundary",
                 "Which tools are exposed at this ceiling, and which are withheld.",
                 "application/json", boundary),
    ]


# --------------------------------------------------------------------------
# server
# --------------------------------------------------------------------------


class _ApprovalRefused(RuntimeError):
    """An EXECUTE call did not carry a valid per-call approval."""


class PortWatchMCPServer:
    """A minimal JSON-RPC MCP server over the PortWatch tool registry."""

    def __init__(
        self,
        registry: Optional[ToolRegistry] = None,
        *,
        max_access: str = PROPOSE,
        approval: Optional[ApprovalContext] = None,
        scope: Optional[ToolScope] = None,
    ) -> None:
        if max_access not in ACCESS_LEVELS:
            raise ValueError(f"unknown access ceiling {max_access}")
        self.registry = registry or build_registry()
        self.max_access = max_access
        # A *mandate*, not a ready-made approval. It records which human is
        # accountable and which session they authenticated in; it is never handed
        # to the registry as-is. Reusing one startup approval for every EXECUTE
        # call would let any client connected to a server started with
        # --allow-execute act under the operator's single standing mandate, so an
        # approval is minted per call, bound to the subject, and only for a
        # request that proves it came from the mandated session.
        self.approval = approval
        # The identity scoped reads are answered for. A server started without
        # one can still serve every unscoped tool; what it cannot do is hand a
        # connected model the national view of the advisory register because
        # nobody said whose question it was.
        self.scope = scope
        self.resources = {r.uri: r for r in _build_resources(self.registry, max_access)}
        self._initialised = False

    # -- protocol ----------------------------------------------------------
    def handle(self, message: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Handle one JSON-RPC message. ``None`` for a notification."""
        method = message.get("method")
        request_id = message.get("id")
        params = message.get("params") or {}

        if method is None:
            return None
        if request_id is None and method.startswith("notifications/"):
            if method == "notifications/initialized":
                self._initialised = True
            return None

        try:
            result = self._dispatch(method, params)
        except _RpcError as exc:
            return {"jsonrpc": "2.0", "id": request_id,
                    "error": {"code": exc.code, "message": str(exc)}}
        except Exception as exc:  # noqa: BLE001 - never take the server down
            return {"jsonrpc": "2.0", "id": request_id,
                    "error": {"code": -32603, "message": f"{type(exc).__name__}: {exc}"}}

        if request_id is None:
            return None
        return {"jsonrpc": "2.0", "id": request_id, "result": result}

    def _dispatch(self, method: str, params: Dict[str, Any]) -> Dict[str, Any]:
        if method == "initialize":
            return {
                "protocolVersion": PROTOCOL_VERSION,
                "serverInfo": SERVER_INFO,
                "capabilities": {"tools": {"listChanged": False},
                                 "resources": {"subscribe": False, "listChanged": False}},
                "instructions": SERVER_INSTRUCTIONS,
            }
        if method == "ping":
            return {}
        if method == "tools/list":
            return {"tools": self.registry.schema(max_access=self.max_access)}
        if method == "tools/call":
            return self._call_tool(params)
        if method == "resources/list":
            return {"resources": [r.to_dict() for r in self.resources.values()]}
        if method == "resources/read":
            return self._read_resource(params)
        raise _RpcError(-32601, f"unknown method {method}")

    def _approval_for(
        self,
        arguments: Dict[str, Any],
        requested: Any,
    ) -> ApprovalContext:
        """Mint a fresh, subject-bound approval for one EXECUTE call.

        The client supplies the session it is acting in and the subject it wants
        approved. Everything that confers authority -- the accountable human and
        their scope -- comes from the operator's mandate, so a client can never
        widen its own reach; the most it can do is name a subject the mandate
        already covers.
        """
        mandate = self.approval
        if mandate is None or not mandate.human_verified:
            raise _ApprovalRefused(
                "this server holds no execute mandate. Start it with --allow-execute "
                "--approver --session-id, or produce a PROPOSE draft instead."
            )
        if not isinstance(requested, dict):
            raise _ApprovalRefused(
                "an EXECUTE call must carry an 'approval' object naming the session "
                "it was authorised in and the subject it approves. A standing "
                "server mandate does not authorise individual actions."
            )
        session_id = str(requested.get("sessionId") or "")
        if not session_id or session_id != mandate.session_id:
            raise _ApprovalRefused(
                "the approval does not come from the session this server was "
                "mandated in, so it does not name an accountable human."
            )
        subject = str(requested.get("subject") or "")
        if not subject:
            raise _ApprovalRefused(
                "an EXECUTE approval must name the subject it approves."
            )
        target = arguments.get("advisory_id")
        if target is not None and subject != str(target):
            raise _ApprovalRefused(
                f"the approval names {subject} but the call acts on {target}."
            )
        return approval_from_session(
            actor=mandate.actor,
            actor_role=mandate.actor_role,
            session_id=mandate.session_id or "",
            subject=subject,
            reason=str(requested.get("reason") or mandate.reason or ""),
            port_code=mandate.port_code,
            organisation=mandate.organisation,
            vessel_ids=mandate.vessel_ids,
            is_admin=mandate.is_admin,
        )

    def _call_tool(self, params: Dict[str, Any]) -> Dict[str, Any]:
        name = params.get("name")
        if not name:
            raise _RpcError(-32602, "tools/call requires a tool name")
        arguments = params.get("arguments") or {}

        spec = self.registry.get(name)
        approval: Optional[ApprovalContext] = None
        if spec is not None and spec.access == EXECUTE:
            try:
                approval = self._approval_for(arguments, params.get("approval"))
            except _ApprovalRefused as exc:
                return {
                    "isError": True,
                    "content": [{"type": "text", "text": str(exc)}],
                    "structuredContent": {
                        "ok": False, "tool": name, "access": EXECUTE,
                        "unavailable": False, "error": str(exc),
                    },
                }

        call = self.registry.call(
            name, arguments, approval=approval, max_access=self.max_access,
            scope=self.scope,
        )

        if not call.ok:
            # An MCP error result rather than a protocol error: the client should
            # see the refusal as a tool outcome it can reason about, which is how
            # an agent learns that a capability needs human approval.
            return {
                "isError": True,
                "content": [{"type": "text", "text": call.error or "tool failed"}],
                "structuredContent": {
                    "ok": False,
                    "tool": call.tool,
                    "access": call.access,
                    "unavailable": call.unavailable,
                    "error": call.error,
                },
            }

        payload = {
            "ok": True,
            "tool": call.tool,
            "access": call.access,
            "computedBy": call.computed_by,
            "durationMs": round(call.duration_ms, 2),
            "result": call.result,
        }
        return {
            "isError": False,
            "content": [{"type": "text", "text": json.dumps(payload, default=str, indent=2)}],
            "structuredContent": payload,
        }

    def _read_resource(self, params: Dict[str, Any]) -> Dict[str, Any]:
        uri = params.get("uri")
        resource = self.resources.get(uri or "")
        if resource is None:
            raise _RpcError(
                -32602,
                f"unknown resource {uri}. Available: {', '.join(self.resources)}",
            )
        return {
            "contents": [{
                "uri": resource.uri,
                "mimeType": resource.mime_type,
                "text": resource.loader(),
            }]
        }

    # -- transport ---------------------------------------------------------
    def serve_stdio(
        self,
        stdin: Optional[TextIO] = None,
        stdout: Optional[TextIO] = None,
    ) -> None:
        """Run the newline-delimited JSON-RPC loop until stdin closes."""
        reader = stdin or sys.stdin
        writer = stdout or sys.stdout
        for line in reader:
            line = line.strip()
            if not line:
                continue
            try:
                message = json.loads(line)
            except json.JSONDecodeError as exc:
                writer.write(json.dumps({
                    "jsonrpc": "2.0", "id": None,
                    "error": {"code": -32700, "message": f"parse error: {exc}"},
                }) + "\n")
                writer.flush()
                continue

            response = self.handle(message)
            if response is not None:
                writer.write(json.dumps(response, default=str) + "\n")
                writer.flush()


class _RpcError(Exception):
    def __init__(self, code: int, message: str) -> None:
        super().__init__(message)
        self.code = code


# --------------------------------------------------------------------------
# entry point
# --------------------------------------------------------------------------


def build_server(
    *,
    max_access: str = PROPOSE,
    approver: Optional[str] = None,
    session_id: Optional[str] = None,
    port_code: Optional[str] = None,
    role: Optional[str] = None,
    organisation: Optional[str] = None,
    vessel_ids: Optional[str] = None,
) -> PortWatchMCPServer:
    approval: Optional[ApprovalContext] = None
    scope: Optional[ToolScope] = None
    if approver and role:
        normalised = role.strip().upper()
        if not is_workspace_role(normalised):
            raise ValueError(
                f"--role must be one of: {', '.join(WORKSPACE_ROLES)}"
            )
        scope = ToolScope(
            actor=approver,
            role=normalised,
            port_code=port_code,
            organisation=organisation,
            vessel_ids=tuple(
                v.strip() for v in (vessel_ids or "").split(",") if v.strip()
            ),
            elevation_reason=(
                "operator started the server at national scope"
                if normalised == NATIONAL_ADMIN else None
            ),
        )
    if max_access == EXECUTE:
        if not approver or not session_id:
            raise ValueError(
                "running the MCP server at the EXECUTE ceiling requires --approver and "
                "--session-id: an EXECUTE call must name the human accountable for it"
            )
        if not port_code:
            raise ValueError(
                "running at the EXECUTE ceiling requires --port-code: the mandate is "
                "scoped to the port the approver actually controls"
            )
        approval = approval_from_session(
            actor=approver, actor_role="ISSUER", session_id=session_id,
            reason="MCP server started with an explicit execute mandate",
            port_code=port_code,
        )
    return PortWatchMCPServer(
        max_access=max_access, approval=approval, scope=scope,
    )


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m src.portwatch_os.mcp.server",
        description="Serve India PortWatch capabilities over Model Context Protocol.",
    )
    parser.add_argument(
        "--max-access", choices=list(ACCESS_LEVELS), default=PROPOSE,
        help=(
            "Highest access level to expose. Defaults to PROPOSE, at which EXECUTE "
            "tools are not listed at all."
        ),
    )
    parser.add_argument(
        "--allow-execute", action="store_true",
        help=(
            "Shorthand for --max-access EXECUTE. Requires --approver, --session-id "
            "and --port-code. Each EXECUTE call must still carry its own approval "
            "naming that session and the subject being acted on."
        ),
    )
    parser.add_argument("--approver", help="Name of the human accountable for EXECUTE calls.")
    parser.add_argument("--session-id", help="Authenticated session the mandate came from.")
    parser.add_argument(
        "--port-code",
        help="UN/LOCODE the approver controls. Scopes every EXECUTE call to that port.",
    )
    parser.add_argument(
        "--role", choices=list(WORKSPACE_ROLES),
        help=(
            "Workspace role the operator holds. Required for tools that read "
            "records belonging to particular ports and carriers; without it those "
            "tools decline rather than returning the national view."
        ),
    )
    parser.add_argument("--organisation", help="Carrier the operator acts for.")
    parser.add_argument("--vessels", help="Comma-separated vessel ids the operator holds.")
    parser.add_argument(
        "--list-tools", action="store_true",
        help="Print the exposed tool catalogue and exit, without serving.",
    )
    args = parser.parse_args(argv)

    max_access = EXECUTE if args.allow_execute else args.max_access
    try:
        server = build_server(
            max_access=max_access, approver=args.approver,
            session_id=args.session_id, port_code=args.port_code,
            role=args.role, organisation=args.organisation,
            vessel_ids=args.vessels,
        )
    except ValueError as exc:
        parser.error(str(exc))
        return 2

    if args.list_tools:
        print(json.dumps(server.registry.schema(max_access=max_access), indent=2))
        return 0

    server.serve_stdio()
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())


__all__ = [
    "PROTOCOL_VERSION",
    "SERVER_INFO",
    "SERVER_INSTRUCTIONS",
    "PortWatchMCPServer",
    "Resource",
    "build_server",
    "main",
]
