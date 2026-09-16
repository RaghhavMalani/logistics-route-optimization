"""Who is asking, and what the API will believe about it.

Identity reaches the API as headers the terminal sets from its session --
``X-PortWatch-Role``, ``X-PortWatch-Actor``, ``X-PortWatch-Port``,
``X-PortWatch-Org``, ``X-PortWatch-Vessels``. Nothing here verifies a token;
this module is the seam a verifier replaces, and until one does the API runs
in one of two identity modes:

    asserted   the default. The headers are believed. A request with no role
               is treated as national command, which is what a checkout, the
               benchmark and the in-process test client have always been. For
               a demo on a private network behind the terminal.
    required   PORTWATCH_IDENTITY_MODE=required. A request with no role is
               401; nothing is defaulted to national command. For a deployment
               behind an authenticating proxy that sets the headers from a
               verified session and strips whatever the client sent.

Two rules hold in both modes, because a default that grants administration is
not a default anyone chose:

*   an administration surface needs the role header present and equal to
    NATIONAL_ADMIN; a missing header is a refusal, never a promotion;
*   administrator standing is derived from the role alone. The legacy
    ``X-PortWatch-Admin`` flag is read only to be reported as ignored.

Readiness reports the mode, and a COMMERCIAL or GOVERNMENT deployment in
``asserted`` mode is a warning there: the licence says production, the
identity says demo.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import List, Optional, Tuple

from fastapi import HTTPException

from src.portwatch_os.roles import (
    DEFAULT_ROLE,
    NATIONAL_ADMIN,
    PORT_AUTHORITY,
    SHIPPING_COMPANY,
    VESSEL_OPERATOR,
    WORKSPACE_ROLES,
    is_workspace_role,
)

ASSERTED = "asserted"
REQUIRED = "required"
IDENTITY_MODES: Tuple[str, ...] = (ASSERTED, REQUIRED)


def identity_mode() -> str:
    value = (os.getenv("PORTWATCH_IDENTITY_MODE") or ASSERTED).strip().lower()
    return value if value in IDENTITY_MODES else ASSERTED


def describe() -> dict:
    mode = identity_mode()
    return {
        "mode": mode,
        "source": "PORTWATCH_IDENTITY_MODE" if os.getenv("PORTWATCH_IDENTITY_MODE") else "default",
        "verified": False,
        "statement": (
            "identity headers are believed as sent; a request with no role is national command"
            if mode == ASSERTED else
            "identity headers are required on every scoped route; a request with no role is refused"
        ),
        "replaceWith": "backend.app.identity.resolve_role: a verifier that reads a session token and sets the role",
        "adminFlagHonoured": False,
    }


def resolve_role(role: Optional[str], *, admin_surface: bool = False) -> str:
    """The workspace role a request acts as, or a refusal.

    ``admin_surface`` marks a route that must never be reached by default:
    the header has to be there, and it has to say NATIONAL_ADMIN.
    """
    if role is None or not role.strip():
        if admin_surface:
            raise HTTPException(
                status_code=401,
                detail="administration surfaces require the operator's identity: send X-PortWatch-Role "
                       "NATIONAL_ADMIN (and X-PortWatch-Actor); no role is defaulted to national command here",
            )
        if identity_mode() == REQUIRED:
            raise HTTPException(
                status_code=401,
                detail="this deployment requires an identity on every request: send X-PortWatch-Role with one of "
                       + ", ".join(WORKSPACE_ROLES),
            )
        return DEFAULT_ROLE
    normalised = role.strip().upper()
    if not is_workspace_role(normalised):
        raise HTTPException(
            status_code=403,
            detail=f"'{role}' is not a workspace role. Send X-PortWatch-Role with one of: {', '.join(WORKSPACE_ROLES)}.",
        )
    if admin_surface and normalised != NATIONAL_ADMIN:
        raise HTTPException(status_code=403, detail="administration surfaces are National Command only")
    return normalised


def require_roles(role: Optional[str], allowed: Tuple[str, ...], *, what: str) -> str:
    """The role, refused with 403 unless it is one of ``allowed``."""
    resolved = resolve_role(role, admin_surface=allowed == (NATIONAL_ADMIN,))
    if resolved not in allowed:
        raise HTTPException(status_code=403, detail=f"{what} is for {', '.join(allowed)}; not for {resolved}")
    return resolved


@dataclass(frozen=True)
class Identity:
    """The asserted identity, folded to what the scoping rules read."""

    role: str
    actor: Optional[str] = None
    port_code: Optional[str] = None
    organisation: Optional[str] = None
    vessel_ids: Tuple[str, ...] = field(default_factory=tuple)

    @property
    def is_admin(self) -> bool:
        return self.role == NATIONAL_ADMIN

    def to_dict(self) -> dict:
        return {"role": self.role, "actor": self.actor, "portCode": self.port_code,
                "organisation": self.organisation, "vesselIds": list(self.vessel_ids)}


def identity_from_headers(
    role: Optional[str],
    actor: Optional[str],
    port_code: Optional[str],
    organisation: Optional[str],
    vessel_ids: Optional[str],
    *,
    admin_surface: bool = False,
) -> Identity:
    resolved = resolve_role(role, admin_surface=admin_surface)
    return Identity(
        role=resolved,
        actor=(actor or "").strip() or None,
        port_code=(port_code or "").strip().upper() or None,
        organisation=(organisation or "").strip() or None,
        vessel_ids=tuple(v.strip() for v in (vessel_ids or "").split(",") if v.strip()),
    )


def _same(a: Optional[str], b: Optional[str]) -> bool:
    return bool(a) and bool(b) and a.strip().casefold() == b.strip().casefold()


def may_see_decision(identity: Identity, actor: dict, subject: dict, domain: str) -> bool:
    """Whether ``identity`` may read or move a decision held by ``actor`` about ``subject``.

    National command sees every decision. A port authority sees the decisions
    of its own port -- those it holds, and a berth decision whose subject is
    its port. A shipping company sees the decisions its organisation holds. A
    vessel operator sees the decisions about its own hulls and those its
    organisation holds. ``actor`` and ``subject`` are the problem's own
    dictionaries, so a record restored from the ledger is judged the same way.
    """
    if identity.is_admin:
        return True
    held_role = str(actor.get("role") or "")
    held_port = actor.get("portCode")
    held_org = actor.get("organisation")
    subject_id = str(subject.get("id") or "")
    if identity.role == PORT_AUTHORITY:
        if held_role == PORT_AUTHORITY and _same(held_port, identity.port_code):
            return True
        return domain == "PORT_BERTHING" and _same(subject_id, identity.port_code)
    if identity.role == SHIPPING_COMPANY:
        return held_role in (SHIPPING_COMPANY, VESSEL_OPERATOR) and _same(held_org, identity.organisation)
    if identity.role == VESSEL_OPERATOR:
        if subject_id and subject_id in identity.vessel_ids:
            return True
        return held_role in (SHIPPING_COMPANY, VESSEL_OPERATOR) and _same(held_org, identity.organisation)
    return False


__all__ = [
    "ASSERTED",
    "IDENTITY_MODES",
    "Identity",
    "REQUIRED",
    "describe",
    "identity_from_headers",
    "identity_mode",
    "may_see_decision",
    "require_roles",
    "resolve_role",
]
