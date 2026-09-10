"""Advisory persistence and the authorisation boundary.

The state machine in :mod:`~src.portwatch_os.advisories.model` says what
transitions are legal. This module says *who* may attempt them, and it is the
layer an API route calls.

Authorisation here is deliberately narrow and explicit:

*   A port controller may act as ISSUER only for the port they hold.
*   A company or vessel operator may act as RECIPIENT only for advisories
    addressed to their own vessel or organisation.
*   Nobody may act as SYSTEM. Expiry is driven by the clock through
    :func:`AdvisoryStore.expire_due`, and there is no caller-supplied path to it.

A denied action raises rather than returning an empty result, so a caller cannot
mistake "you may not" for "there is nothing there".
"""

from __future__ import annotations

import json
import sqlite3
import threading
from dataclasses import asdict
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from src.portwatch_os.advisories.model import (
    ACCEPTED,
    ADVISORY_STATES,
    DRAFT,
    ISSUED,
    ISSUER,
    RECIPIENT,
    SYSTEM,
    Advisory,
    AdvisoryError,
    AuditEntry,
    expire_due,
    modify,
    transition,
    utc_now,
)
from src.utils.config import OUTPUTS_DIR

DEFAULT_ADVISORY_PATH = OUTPUTS_DIR / "portwatch_advisories.db"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS advisories (
    advisory_id             TEXT PRIMARY KEY,
    kind                    TEXT NOT NULL,
    port_code               TEXT NOT NULL,
    issuer                  TEXT NOT NULL,
    issuer_organisation     TEXT NOT NULL,
    recipient_vessel_id     TEXT NOT NULL,
    recipient_vessel_name   TEXT NOT NULL,
    recipient_organisation  TEXT NOT NULL,
    created_at              TEXT NOT NULL,
    recommendation          TEXT NOT NULL,
    reason                  TEXT NOT NULL,
    state                   TEXT NOT NULL,
    model_confidence        REAL,
    prediction_ids          TEXT,
    evidence                TEXT,
    critic_verdict          TEXT,
    critic_reasons          TEXT,
    decision_id             TEXT,
    valid_until             TEXT,
    issued_at               TEXT,
    responded_at            TEXT,
    response_reason         TEXT,
    modified_from           TEXT,
    audit                   TEXT
);
CREATE INDEX IF NOT EXISTS ix_adv_port      ON advisories(port_code, state);
CREATE INDEX IF NOT EXISTS ix_adv_recipient ON advisories(recipient_vessel_id, state);
CREATE INDEX IF NOT EXISTS ix_adv_org       ON advisories(recipient_organisation, state);
"""


class AuthorisationError(AdvisoryError):
    """The actor is not permitted to do this. Distinct from an illegal transition."""


#: Characters an HTTP header cannot carry, and what the terminal folds them to.
_FOLD = {
    "‐": "-", "‑": "-", "‒": "-", "–": "-",
    "—": "-", "―": "-",
    "‘": "'", "’": "'", "“": '"', "”": '"',
}


def ascii_fold(value: Optional[str]) -> str:
    """Normalise a name the way an HTTP header forces the client to.

    Header values are ISO-8859-1, so a non-ASCII character makes the browser's
    `fetch` reject the request before it is sent. The terminal therefore folds
    dashes and quotes to ASCII and drops anything else before putting an
    organisation name in a header -- see `asciiHeader` in the auth types.

    That means a port authority arriving over the wire as "Chennai Port
    Authority - Control Room" has to still match the em-dashed name in the
    register, or the recipient check fails on a punctuation mark. Both sides
    fold, so both sides agree.
    """
    if not value:
        return ""
    folded = "".join(_FOLD.get(c, c) for c in value)
    return "".join(c for c in folded if 0x20 <= ord(c) <= 0x7E).strip()


class Principal:
    """Who is acting, and what they are entitled to act on.

    Constructed by the API from the authenticated session, never from a request
    body. The distinction matters: a caller that could name its own principal
    could issue advisories as any port authority it liked.
    """

    def __init__(
        self,
        *,
        actor: str,
        role: str,
        port_code: Optional[str] = None,
        organisation: Optional[str] = None,
        vessel_ids: Optional[Sequence[str]] = None,
        is_admin: bool = False,
    ) -> None:
        if role not in (ISSUER, RECIPIENT):
            raise AuthorisationError(
                f"a principal may be an {ISSUER} or a {RECIPIENT}; "
                f"'{role}' is not a role a caller may hold"
            )
        if not actor:
            raise AuthorisationError("a principal must be a named actor")
        if not is_admin and role == ISSUER and not port_code:
            raise AuthorisationError(
                f"{actor} claims the {ISSUER} role without naming a port. An issuer "
                "is scoped to the port it controls; only national command acts "
                "without one, and that is the is_admin path."
            )
        if not is_admin and role == RECIPIENT and not organisation and not vessel_ids:
            raise AuthorisationError(
                f"{actor} claims the {RECIPIENT} role without naming an organisation "
                "or any vessel. A recipient is scoped to what it operates."
            )
        self.actor = actor
        self.role = role
        self.port_code = port_code
        self.organisation = organisation
        self.vessel_ids = set(vessel_ids or [])
        self.is_admin = is_admin

    def assert_may_issue(self, advisory: Advisory) -> None:
        if self.role != ISSUER:
            raise AuthorisationError(
                f"{self.actor} holds the {self.role} role and cannot issue advisories"
            )
        if self.is_admin:
            return
        if self.port_code and advisory.port_code != self.port_code:
            raise AuthorisationError(
                f"{self.actor} controls {self.port_code} and cannot act on an advisory "
                f"issued by {advisory.port_code}"
            )

    def assert_may_respond(self, advisory: Advisory) -> None:
        if self.role != RECIPIENT:
            raise AuthorisationError(
                f"{self.actor} holds the {self.role} role and cannot respond to an "
                "advisory on the recipient's behalf"
            )
        if self.is_admin:
            return
        if self.vessel_ids and advisory.recipient_vessel_id in self.vessel_ids:
            return
        if self.organisation and ascii_fold(advisory.recipient_organisation) == ascii_fold(
            self.organisation
        ):
            return
        raise AuthorisationError(
            f"{self.actor} is not the recipient of {advisory.advisory_id}"
        )

    def may_see(self, advisory: Advisory) -> bool:
        if self.is_admin:
            return True
        if self.role == ISSUER:
            return advisory.port_code == self.port_code
        if not advisory.visible_to_recipient:
            return False
        return (
            advisory.recipient_vessel_id in self.vessel_ids
            or (
                self.organisation is not None
                and ascii_fold(advisory.recipient_organisation)
                == ascii_fold(self.organisation)
            )
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "actor": self.actor, "role": self.role, "portCode": self.port_code,
            "organisation": self.organisation, "vesselIds": sorted(self.vessel_ids),
            "isAdmin": self.is_admin,
        }


#: How a workspace role maps onto a side of the advisory workflow, and what it
#: is scoped by. National command is the only role that sees the network, and it
#: says so explicitly here rather than any caller defaulting into it.
_ROLE_MAP: Dict[str, Tuple[str, str]] = {
    "NATIONAL_ADMIN": (ISSUER, "national"),
    "PORT_AUTHORITY": (ISSUER, "port"),
    "SHIPPING_COMPANY": (RECIPIENT, "organisation"),
    "VESSEL_OPERATOR": (RECIPIENT, "vessels"),
    # Legacy request vocabulary, kept so the HTTP surface does not break.
    "ISSUER": (ISSUER, "port"),
    "PORT_OPERATOR": (ISSUER, "port"),
    "ADMIN": (ISSUER, "national"),
    "RECIPIENT": (RECIPIENT, "organisation"),
}


def principal_for_role(
    *,
    actor: str,
    role: str,
    port_code: Optional[str] = None,
    organisation: Optional[str] = None,
    vessel_ids: Optional[Sequence[str]] = None,
) -> Principal:
    """Turn a workspace role and its scope into an advisory principal.

    One mapping, used by the HTTP routes and by the tool layer, so an agent
    answering a port controller's question sees exactly what that controller
    would see over the API and not a byte more. Each role is scoped by the thing
    it actually owns, and the scope is required: a port authority that names no
    port is refused rather than quietly widened to the network.
    """
    normalised = (role or "").strip().upper()
    mapped = _ROLE_MAP.get(normalised)
    if mapped is None:
        raise AuthorisationError(
            f"'{role}' is not a role that may act on advisories. A port authority "
            "or national command acts as the issuer; a company or vessel operator "
            "as the recipient."
        )
    party, scoped_by = mapped
    if scoped_by == "national":
        return Principal(actor=actor, role=party, is_admin=True)
    if scoped_by == "port":
        return Principal(actor=actor, role=party, port_code=port_code)
    if scoped_by == "organisation":
        return Principal(
            actor=actor, role=party, organisation=organisation,
            vessel_ids=vessel_ids,
        )
    return Principal(actor=actor, role=party, vessel_ids=vessel_ids)


class AdvisoryStore:
    """SQLite-backed advisory register with the authorisation gate in front."""

    def __init__(self, path: Path | str | None = None) -> None:
        self.path = Path(path) if path is not None else DEFAULT_ADVISORY_PATH
        if str(self.path) != ":memory:":
            self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._conn = sqlite3.connect(str(self.path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        with self._lock:
            self._conn.executescript(_SCHEMA)
            self._conn.commit()

    def close(self) -> None:
        with self._lock:
            self._conn.close()

    # -- serialisation -----------------------------------------------------
    @staticmethod
    def _to_row(advisory: Advisory) -> Dict[str, Any]:
        row = asdict(advisory)
        for key in ("recommendation", "prediction_ids", "evidence",
                    "critic_reasons", "modified_from"):
            row[key] = json.dumps(getattr(advisory, key), sort_keys=True, default=str)
        row["audit"] = json.dumps([e.to_dict() for e in advisory.audit], default=str)
        return row

    @staticmethod
    def _from_row(row: Dict[str, Any]) -> Advisory:
        data = dict(row)
        for key, default in (
            ("recommendation", {}), ("prediction_ids", []), ("evidence", {}),
            ("critic_reasons", []),
        ):
            data[key] = _loads(data.get(key)) or default
        data["modified_from"] = _loads(data.get("modified_from"))
        audit = _loads(data.pop("audit", None)) or []
        advisory = Advisory(**{
            k: v for k, v in data.items()
            if k in Advisory.__dataclass_fields__ and k != "audit"
        })
        advisory.audit = [AuditEntry(**entry) for entry in audit]
        return advisory

    # -- writes ------------------------------------------------------------
    def create(self, advisory: Advisory, *, principal: Optional[Principal] = None) -> Advisory:
        """Register a new advisory. Always lands in DRAFT.

        The state is forced rather than trusted: an advisory that arrived
        claiming to be ISSUED would bypass the entire approval workflow, so the
        constructor's word on that is not accepted.
        """
        problems = advisory.validate()
        if problems:
            raise AdvisoryError(
                f"{advisory.advisory_id} is not a well-formed advisory: "
                + "; ".join(problems)
            )
        if principal is not None:
            principal.assert_may_issue(advisory)
        advisory.state = DRAFT
        if not advisory.audit:
            advisory.audit.append(
                AuditEntry(
                    at=advisory.created_at or utc_now(),
                    actor=advisory.issuer, actor_role=ISSUER, action="Draft created",
                    from_state=DRAFT, to_state=DRAFT,
                    reason="generated by the decision engine and awaiting review",
                )
            )
        self._write(advisory)
        return advisory

    def _write(self, advisory: Advisory) -> None:
        row = self._to_row(advisory)
        columns = list(row)
        placeholders = ", ".join("?" for _ in columns)
        updates = ", ".join(f"{c} = excluded.{c}" for c in columns if c != "advisory_id")
        sql = (
            f"INSERT INTO advisories ({', '.join(columns)}) VALUES ({placeholders}) "
            f"ON CONFLICT(advisory_id) DO UPDATE SET {updates}"
        )
        with self._lock:
            self._conn.execute(sql, [row[c] for c in columns])
            self._conn.commit()

    def act(
        self,
        advisory_id: str,
        target: str,
        *,
        principal: Principal,
        reason: Optional[str] = None,
        changes: Optional[Dict[str, Any]] = None,
    ) -> Advisory:
        """Attempt a transition as this principal. Raises if not permitted."""
        advisory = self.require(advisory_id)
        if principal.role == ISSUER:
            principal.assert_may_issue(advisory)
        else:
            principal.assert_may_respond(advisory)

        transition(
            advisory, target, actor=principal.actor, actor_role=principal.role,
            reason=reason, changes=changes,
        )
        self._write(advisory)
        return advisory

    def modify(
        self,
        advisory_id: str,
        changes: Dict[str, Any],
        *,
        principal: Principal,
        reason: str,
    ) -> Advisory:
        advisory = self.require(advisory_id)
        principal.assert_may_issue(advisory)
        modify(advisory, changes, actor=principal.actor, reason=reason)
        self._write(advisory)
        return advisory

    def expire_due(self, *, now: Optional[str] = None) -> List[Advisory]:
        """The only path to a SYSTEM transition, and it takes no caller identity."""
        advisories = [a for a in self.all() if a.state in (ISSUED, "acknowledged")]
        expired = expire_due(advisories, now=now)
        for advisory in expired:
            self._write(advisory)
        return expired

    # -- reads -------------------------------------------------------------
    def get(self, advisory_id: str) -> Optional[Advisory]:
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM advisories WHERE advisory_id = ?", (advisory_id,)
            ).fetchone()
        return self._from_row(dict(row)) if row else None

    def require(self, advisory_id: str) -> Advisory:
        advisory = self.get(advisory_id)
        if advisory is None:
            raise AdvisoryError(f"no advisory {advisory_id}")
        return advisory

    def all(self) -> List[Advisory]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM advisories ORDER BY created_at DESC"
            ).fetchall()
        return [self._from_row(dict(row)) for row in rows]

    def visible_to(
        self,
        principal: Principal,
        *,
        state: Optional[str] = None,
        port_code: Optional[str] = None,
        vessel_id: Optional[str] = None,
        limit: int = 200,
    ) -> List[Advisory]:
        """Everything this principal is entitled to see, filtered.

        The visibility rule is applied after the query rather than inside it, so
        there is exactly one place -- ``Principal.may_see`` -- that decides who
        sees what, and the SQL cannot drift out of step with it.
        """
        clauses: List[str] = []
        params: List[Any] = []
        if state:
            clauses.append("state = ?")
            params.append(state)
        if port_code:
            clauses.append("port_code = ?")
            params.append(port_code)
        if vessel_id:
            clauses.append("recipient_vessel_id = ?")
            params.append(vessel_id)
        sql = "SELECT * FROM advisories"
        if clauses:
            sql += " WHERE " + " AND ".join(clauses)
        sql += " ORDER BY created_at DESC"
        with self._lock:
            rows = self._conn.execute(sql, params).fetchall()
        # The caller's limit counts rows this principal may *see*. Applying it in
        # SQL would count other principals' rows against the budget, so a
        # recipient's older advisories would silently vanish once the register
        # filled up with traffic they are not entitled to.
        visible: List[Advisory] = []
        for row in rows:
            advisory = self._from_row(dict(row))
            if principal.may_see(advisory):
                visible.append(advisory)
                if len(visible) >= int(limit):
                    break
        return visible

    def counts(self, principal: Principal) -> Dict[str, int]:
        """The register by state, over the population this principal may see.

        Counting the whole table would tell a recipient how many advisories
        every port and every competitor has in flight, which the list itself is
        careful not to.
        """
        with self._lock:
            rows = self._conn.execute("SELECT * FROM advisories").fetchall()
        tally: Dict[str, int] = {}
        for row in rows:
            advisory = self._from_row(dict(row))
            if principal.may_see(advisory):
                tally[advisory.state] = tally.get(advisory.state, 0) + 1
        return tally

    def audit_trail(self, advisory_id: str, principal: Principal) -> List[Dict[str, Any]]:
        """The transition history, for a principal entitled to the advisory.

        The trail carries the issuing port's internal review -- drafter,
        reviewer, rejection reasons -- so it is gated by the same visibility
        rule as the advisory itself rather than by knowledge of the id.
        """
        advisory = self.require(advisory_id)
        if not principal.may_see(advisory):
            raise AuthorisationError(
                f"{principal.actor} is not entitled to {advisory_id}"
            )
        return [entry.to_dict() for entry in advisory.audit]


def _loads(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, (dict, list)):
        return value
    try:
        return json.loads(value)
    except (TypeError, ValueError):
        return None


_DEFAULT: Optional[AdvisoryStore] = None
_LOCK = threading.Lock()


def get_advisory_store(path: Path | str | None = None) -> AdvisoryStore:
    global _DEFAULT
    if path is not None:
        return AdvisoryStore(path)
    with _LOCK:
        if _DEFAULT is None:
            _DEFAULT = AdvisoryStore()
        return _DEFAULT


def reset_default_store() -> None:
    """Tests only."""
    global _DEFAULT
    with _LOCK:
        if _DEFAULT is not None:
            _DEFAULT.close()
        _DEFAULT = None


__all__ = [
    "DEFAULT_ADVISORY_PATH",
    "AdvisoryStore",
    "AuthorisationError",
    "Principal",
    "ascii_fold",
    "get_advisory_store",
    "reset_default_store",
]
