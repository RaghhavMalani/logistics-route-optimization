"""Verified request identity and server-owned workspace scope.

The default verified mode accepts revocable opaque sessions from the identity
store. Client role, actor and membership headers are replaced before route
dependencies run. Asserted demo and legacy proxy-required modes are explicit
compatibility settings; private cameras and evidence writes still require a
verified session. Authentication uses wall time independently of replay.
"""

from __future__ import annotations

import os
from contextvars import ContextVar
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
VERIFIED = "verified"
IDENTITY_MODES: Tuple[str, ...] = (ASSERTED, REQUIRED, VERIFIED)
current_identity: ContextVar[Optional["Identity"]] = ContextVar("verified_identity", default=None)


def identity_mode() -> str:
    value = (os.getenv("PORTWATCH_IDENTITY_MODE") or VERIFIED).strip().lower()
    return value if value in IDENTITY_MODES else VERIFIED


def describe() -> dict:
    mode = identity_mode()
    return {
        "mode": mode,
        "source": "PORTWATCH_IDENTITY_MODE" if os.getenv("PORTWATCH_IDENTITY_MODE") else "default",
        "verified": mode == VERIFIED,
        "statement": (
            "explicit demo mode: identity headers are asserted; private cameras and evidence writes require a verified session"
            if mode == ASSERTED else
            "opaque sessions are verified against server-managed accounts; roles and memberships come from the server"
            if mode == VERIFIED else
            "identity headers are required on every scoped route; a request with no role is refused"
        ),
        "privateCameraIdentity": "verified session required in every mode",
        "adminFlagHonoured": False,
    }


def resolve_role(role: Optional[str], *, admin_surface: bool = False) -> str:
    """The workspace role a request acts as, or a refusal.

    ``admin_surface`` marks a route that must never be reached by default:
    the header has to be there, and it has to say NATIONAL_ADMIN.
    """
    principal = current_identity.get()
    if principal:
        role = principal.role
    elif identity_mode() == VERIFIED:
        raise HTTPException(401, "A verified session is required")
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
        # Compatibility only for explicitly selected demo mode. The default VERIFIED
        # mode is refused above; private cameras always require_verified independently.
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
    """Workspace scope, marked verified only by the server session middleware."""

    role: str
    actor: Optional[str] = None
    port_code: Optional[str] = None
    organisation: Optional[str] = None
    vessel_ids: Tuple[str, ...] = field(default_factory=tuple)
    port_codes: Tuple[str, ...] = field(default_factory=tuple)
    verified: bool = False

    @property
    def is_admin(self) -> bool:
        return self.role == NATIONAL_ADMIN

    def to_dict(self) -> dict:
        return {"role": self.role, "actor": self.actor, "portCode": self.port_code,
                "organisation": self.organisation, "vesselIds": list(self.vessel_ids),
                "portCodes": list(self.port_codes), "verified": self.verified}


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
    if current_identity.get():
        return current_identity.get()
    return Identity(
        role=resolved,
        actor=(actor or "").strip() or None,
        port_code=(port_code or "").strip().upper() or None,
        organisation=(organisation or "").strip() or None,
        vessel_ids=tuple(v.strip() for v in (vessel_ids or "").split(",") if v.strip()),
    )


def require_verified() -> Identity:
    principal = current_identity.get()
    if not principal or not principal.verified:
        raise HTTPException(401, "Private cameras and evidence writes require a verified session")
    return principal


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
    "VERIFIED",
    "describe",
    "identity_from_headers",
    "identity_mode",
    "may_see_decision",
    "require_roles",
    "require_verified",
    "resolve_role",
]
