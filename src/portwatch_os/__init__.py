"""India PortWatch — the agentic maritime operations layer.

Everything under this package sits *above* the forecasting stack in
:mod:`src.forecasting`, :mod:`src.experts` and :mod:`src.decision`, and below
the API in :mod:`backend.app`. It is the part of the product that closes the
loop:

    OBSERVE -> UNDERSTAND -> FORECAST -> SIMULATE -> DECIDE -> ACT -> LEARN

The division of labour is deliberate and enforced by the module boundaries:

    ``global_eye``  turns a raw event feed into typed, deduplicated maritime
                    events with measured exposure through chokepoints, lanes,
                    vessels and ports.
    ``twin``        holds one logical port state, a deterministic simulator over
                    it, optimisers and learned policies. The 3D renderer and the
                    RL environment consume the *same* state object.
    ``cargo``       transshipment feasibility and assignment.
    ``advisories``  the human-in-the-loop port-to-vessel workflow.
    ``ledger``      every prediction and decision this system emits, and what
                    actually happened afterwards.
    ``learning``    scores the ledger, updates reliability, calibrates event
                    probabilities and attributes error to contributors.
    ``agents``      orchestration only. Agents call tools; tools call the
                    deterministic models above. No agent computes an operational
                    number itself.
    ``mcp``         the same tools, exposed over Model Context Protocol, split
                    into READ / SIMULATE / PROPOSE / EXECUTE.
"""

__all__ = [
    "advisories",
    "agents",
    "cargo",
    "fleet",
    "global_eye",
    "learning",
    "ledger",
    "mcp",
    "twin",
]
