"""The workspace role vocabulary, shared by the API and the agent layer.

These are the four roles the terminal signs a user in as, and they are the
values that arrive as ``X-PortWatch-Role``. They existed only in TypeScript
(``india-portwatch-terminal/src/auth/types.ts``), so the Python side carried a
private ``"ADMIN"`` default that no workspace recognised: an ``AgentRun`` came
back labelled with a role outside the advertised vocabulary, and a consumer
selecting a workspace or a policy from it had nothing to match.

Keep this list and ``types.ts`` in step. The advisory *party* -- issuer or
recipient -- is a separate, narrower idea and lives in
:mod:`src.portwatch_os.advisories.model`; a role maps onto a party, and two of
these four map onto neither.
"""

from __future__ import annotations

from typing import Tuple

VESSEL_OPERATOR = "VESSEL_OPERATOR"
SHIPPING_COMPANY = "SHIPPING_COMPANY"
PORT_AUTHORITY = "PORT_AUTHORITY"
NATIONAL_ADMIN = "NATIONAL_ADMIN"

WORKSPACE_ROLES: Tuple[str, ...] = (
    VESSEL_OPERATOR,
    SHIPPING_COMPANY,
    PORT_AUTHORITY,
    NATIONAL_ADMIN,
)

#: The role an unscoped caller is treated as. National command is the only role
#: that legitimately sees the whole network, and it is the workspace the API's
#: own defaults land in.
DEFAULT_ROLE = NATIONAL_ADMIN


def is_workspace_role(value: str) -> bool:
    return value in WORKSPACE_ROLES


__all__ = [
    "DEFAULT_ROLE",
    "NATIONAL_ADMIN",
    "PORT_AUTHORITY",
    "SHIPPING_COMPANY",
    "VESSEL_OPERATOR",
    "WORKSPACE_ROLES",
    "is_workspace_role",
]
