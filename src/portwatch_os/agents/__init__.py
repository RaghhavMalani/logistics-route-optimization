"""Agentic orchestration.

Agents orchestrate; tools compute; models predict; optimisers decide numbers;
the Critic checks; humans approve. The boundary is enforced at call time in
:mod:`~src.portwatch_os.agents.tools`, not by convention.
"""

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
    MODIFIED,
    REJECTED,
    Critic,
    CriticCheck,
    CriticVerdict,
    Recommendation,
    recommendation_from_agents,
)
from src.portwatch_os.agents.orchestrator import (
    INTENTS,
    AgentRun,
    CommandAgent,
    Intent,
    classify_intent,
    extract_entities,
)
from src.portwatch_os.agents.portwatch_tools import build_registry
from src.portwatch_os.agents.specialists import SPECIALISTS
from src.portwatch_os.agents.tools import (
    EXECUTE,
    PROPOSE,
    READ,
    SIMULATE,
    ApprovalContext,
    ApprovalRequired,
    ToolCall,
    ToolRegistry,
    ToolSpec,
    ToolUnavailable,
    approval_from_session,
)

__all__ = [
    "APPROVED", "BLOCKED", "COMPLETE", "EXECUTE", "INTENTS", "MODIFIED", "PARTIAL",
    "PROPOSE", "READ", "REJECTED", "SIMULATE", "SPECIALISTS", "Agent",
    "AgentRequest", "AgentResult", "AgentRun", "ApprovalContext",
    "ApprovalRequired", "CommandAgent", "Critic", "CriticCheck", "CriticVerdict",
    "Finding", "Intent", "Recommendation", "ToolCall", "ToolRegistry", "ToolSpec",
    "ToolUnavailable", "approval_from_session", "build_registry",
    "classify_intent", "extract_entities", "propagate_confidence",
    "recommendation_from_agents",
]
