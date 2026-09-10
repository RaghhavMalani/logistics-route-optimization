"""The Attention Engine: what requires action, and what it costs to ignore.

A ranked queue of at most a handful of things, framed from cascades the World
State Engine computed. Nothing here produces a number of its own -- see
:mod:`~src.portwatch_os.attention.engine` for why that constraint is the whole
design.
"""

from src.portwatch_os.attention.engine import attention_for
from src.portwatch_os.attention.model import (
    ACTIONABLE,
    ACT_NOW,
    ACT_SOON,
    AttentionItem,
    Effect,
    MONITOR_ONLY,
    NO_ACTION_AVAILABLE,
    Option,
    STATUSES,
    WATCH,
    order,
    rank,
    urgency_multiplier,
    urgency_score,
)

__all__ = [
    "ACTIONABLE",
    "ACT_NOW",
    "ACT_SOON",
    "AttentionItem",
    "Effect",
    "MONITOR_ONLY",
    "NO_ACTION_AVAILABLE",
    "Option",
    "STATUSES",
    "WATCH",
    "attention_for",
    "order",
    "rank",
    "urgency_multiplier",
    "urgency_score",
]
