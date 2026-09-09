"""Storage for the ledger.

The interface is :class:`LedgerStore`; the implementation that ships is SQLite,
because the demo has to run from a clone with no infrastructure. Everything the
rest of the system touches goes through the abstract methods, so replacing this
with Postgres is a new subclass and a connection string -- not a refactor of the
learning layer.

Two properties this module guarantees, and the tests hold it to:

*   **Idempotent writes.** Ids are content-derived (see ``schema._stable_id``),
    so re-running the pipeline over the same window updates rows rather than
    accumulating near-duplicates. A ledger that double-counts is worse than no
    ledger, because the calibration it feeds looks more confident than it is.

*   **No retroactive editing of a claim.** ``resolve_prediction`` writes the
    observation columns only. The predicted value, the context and the
    contributions are immutable once written; an attempt to change them through
    ``record_prediction`` on a resolved row is refused.
"""

from __future__ import annotations

import sqlite3
import threading
from abc import ABC, abstractmethod
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, Iterator, List, Optional, Sequence

from src.portwatch_os.ledger.schema import (
    APPROVED,
    DecisionRecord,
    EventOutcomeRecord,
    OPEN,
    PolicyRecord,
    PredictionRecord,
    RESOLVED,
    ReliabilityRecord,
    can_transition,
    utc_now,
)
from src.utils.config import OUTPUTS_DIR

DEFAULT_LEDGER_PATH = OUTPUTS_DIR / "portwatch_ledger.db"


class LedgerError(RuntimeError):
    """Raised when a write would violate the ledger's integrity rules."""


class LedgerStore(ABC):
    """What the rest of the system is allowed to ask of the ledger."""

    # -- predictions -------------------------------------------------------
    @abstractmethod
    def record_prediction(self, record: PredictionRecord) -> str: ...

    @abstractmethod
    def get_prediction(self, prediction_id: str) -> Optional[PredictionRecord]: ...

    @abstractmethod
    def resolve_prediction(
        self,
        prediction_id: str,
        observed_value: float,
        observed_at: str,
        observation_source: str,
        metrics: Optional[Dict[str, Any]] = None,
    ) -> Optional[PredictionRecord]: ...

    @abstractmethod
    def predictions(
        self,
        *,
        domain: Optional[str] = None,
        model: Optional[str] = None,
        subject: Optional[str] = None,
        status: Optional[str] = None,
        issued_before: Optional[str] = None,
        valid_before: Optional[str] = None,
        limit: Optional[int] = None,
    ) -> List[PredictionRecord]: ...

    # -- decisions ---------------------------------------------------------
    @abstractmethod
    def record_decision(self, record: DecisionRecord) -> str: ...

    @abstractmethod
    def get_decision(self, decision_id: str) -> Optional[DecisionRecord]: ...

    @abstractmethod
    def resolve_decision(
        self,
        decision_id: str,
        action_state: str,
        observed_outcome: Dict[str, float],
        observed_at: str,
        operational_reward: Optional[float] = None,
        impact_error: Optional[float] = None,
    ) -> Optional[DecisionRecord]: ...

    @abstractmethod
    def decisions(
        self,
        *,
        kind: Optional[str] = None,
        subject: Optional[str] = None,
        status: Optional[str] = None,
        limit: Optional[int] = None,
    ) -> List[DecisionRecord]: ...

    # -- event outcomes ----------------------------------------------------
    @abstractmethod
    def record_event_outcome(self, record: EventOutcomeRecord) -> str: ...

    @abstractmethod
    def resolve_event_outcome(
        self,
        outcome_id: str,
        occurred: bool,
        observed_at: str,
        observation_source: str,
        observed_impact: Optional[Dict[str, float]] = None,
        metrics: Optional[Dict[str, Any]] = None,
    ) -> Optional[EventOutcomeRecord]: ...

    @abstractmethod
    def event_outcomes(
        self,
        *,
        category: Optional[str] = None,
        status: Optional[str] = None,
        resolve_before: Optional[str] = None,
        limit: Optional[int] = None,
    ) -> List[EventOutcomeRecord]: ...

    # -- reliability -------------------------------------------------------
    @abstractmethod
    def upsert_reliability(self, record: ReliabilityRecord) -> None: ...

    @abstractmethod
    def reliability(
        self,
        *,
        contributor: Optional[str] = None,
        context_key: Optional[str] = None,
    ) -> List[ReliabilityRecord]: ...

    # -- policies ----------------------------------------------------------
    @abstractmethod
    def upsert_policy(self, record: PolicyRecord) -> None: ...

    @abstractmethod
    def get_policy(self, policy_id: str) -> Optional[PolicyRecord]: ...

    @abstractmethod
    def policies(self, *, state: Optional[str] = None) -> List[PolicyRecord]: ...

    @abstractmethod
    def transition_policy(
        self,
        policy_id: str,
        target_state: str,
        *,
        actor: Optional[str] = None,
        reason: Optional[str] = None,
        evaluation: Optional[Dict[str, Any]] = None,
        safety_checks: Optional[Dict[str, bool]] = None,
    ) -> PolicyRecord: ...


# --------------------------------------------------------------------------
# SQLite implementation
# --------------------------------------------------------------------------

_SCHEMA = """
CREATE TABLE IF NOT EXISTS predictions (
    prediction_id       TEXT PRIMARY KEY,
    domain              TEXT NOT NULL,
    kind                TEXT NOT NULL,
    target              TEXT NOT NULL,
    subject             TEXT NOT NULL,
    model               TEXT NOT NULL,
    model_version       TEXT NOT NULL,
    issued_at           TEXT NOT NULL,
    valid_at            TEXT NOT NULL,
    context             TEXT NOT NULL,
    predicted_value     REAL,
    predicted_low       REAL,
    predicted_high      REAL,
    interval_nominal    REAL,
    confidence          REAL,
    features            TEXT,
    contributions       TEXT,
    provenance          TEXT,
    status              TEXT NOT NULL,
    observed_value      REAL,
    observed_at         TEXT,
    observation_source  TEXT,
    error               REAL,
    absolute_error      REAL,
    brier               REAL,
    log_loss            REAL,
    within_interval     INTEGER,
    lead_time_hours     REAL,
    notes               TEXT
);
CREATE INDEX IF NOT EXISTS ix_pred_domain   ON predictions(domain, status);
CREATE INDEX IF NOT EXISTS ix_pred_subject  ON predictions(subject, valid_at);
CREATE INDEX IF NOT EXISTS ix_pred_model    ON predictions(model, status);

CREATE TABLE IF NOT EXISTS decisions (
    decision_id         TEXT PRIMARY KEY,
    kind                TEXT NOT NULL,
    subject             TEXT NOT NULL,
    issued_at           TEXT NOT NULL,
    issuer              TEXT NOT NULL,
    recommendation      TEXT NOT NULL,
    reason              TEXT,
    prediction_ids      TEXT,
    model               TEXT,
    model_version       TEXT,
    policy_id           TEXT,
    confidence          REAL,
    expected_impact     TEXT,
    critic_verdict      TEXT,
    critic_reasons      TEXT,
    approval_state      TEXT,
    approver            TEXT,
    status              TEXT NOT NULL,
    action_state        TEXT NOT NULL,
    observed_outcome    TEXT,
    observed_at         TEXT,
    operational_reward  REAL,
    impact_error        REAL,
    notes               TEXT
);
CREATE INDEX IF NOT EXISTS ix_dec_kind ON decisions(kind, status);

CREATE TABLE IF NOT EXISTS event_outcomes (
    outcome_id              TEXT PRIMARY KEY,
    event_id                TEXT NOT NULL,
    category                TEXT NOT NULL,
    region                  TEXT,
    claim                   TEXT NOT NULL,
    horizon_hours           REAL NOT NULL,
    predicted_probability   REAL NOT NULL,
    confidence              REAL,
    source_count            INTEGER,
    sources                 TEXT,
    issued_at               TEXT,
    resolve_by              TEXT,
    status                  TEXT NOT NULL,
    occurred                INTEGER,
    observed_at             TEXT,
    observation_source      TEXT,
    observed_impact         TEXT,
    predicted_impact        TEXT,
    false_alarm             INTEGER,
    lead_time_hours         REAL,
    brier                   REAL,
    log_loss                REAL,
    impact_error            REAL,
    notes                   TEXT
);
CREATE INDEX IF NOT EXISTS ix_evo_category ON event_outcomes(category, status);

CREATE TABLE IF NOT EXISTS reliability (
    contributor         TEXT NOT NULL,
    context_key         TEXT NOT NULL,
    dimensions          TEXT NOT NULL,
    weight              REAL NOT NULL,
    previous_weight     REAL,
    sample_count        INTEGER NOT NULL,
    mean_absolute_error REAL,
    bias                REAL,
    calibration_error   REAL,
    updated_at          TEXT,
    fitted_from         TEXT,
    fitted_to           TEXT,
    notes               TEXT,
    PRIMARY KEY (contributor, context_key)
);

CREATE TABLE IF NOT EXISTS policies (
    policy_id           TEXT PRIMARY KEY,
    name                TEXT NOT NULL,
    family              TEXT NOT NULL,
    version             TEXT NOT NULL,
    state               TEXT NOT NULL,
    created_at          TEXT,
    updated_at          TEXT,
    environment         TEXT,
    training            TEXT,
    evaluation          TEXT,
    baseline_policy_id  TEXT,
    safety_checks       TEXT,
    approved_by         TEXT,
    approved_at         TEXT,
    rejection_reason    TEXT,
    notes               TEXT
);

CREATE TABLE IF NOT EXISTS ledger_audit (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    at          TEXT NOT NULL,
    entity      TEXT NOT NULL,
    entity_id   TEXT NOT NULL,
    action      TEXT NOT NULL,
    actor       TEXT,
    detail      TEXT
);
CREATE INDEX IF NOT EXISTS ix_audit_entity ON ledger_audit(entity, entity_id);
"""


class SqliteLedgerStore(LedgerStore):
    """The shipped ledger.

    One connection guarded by a lock rather than a pool: the write volume is a
    few thousand rows per pipeline run, and a lock is easier to reason about than
    thread-local connections when the API and a background pass both write.
    """

    def __init__(self, path: Path | str | None = None) -> None:
        self.path = Path(path) if path is not None else DEFAULT_LEDGER_PATH
        if str(self.path) != ":memory:":
            self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._conn = sqlite3.connect(str(self.path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA foreign_keys=ON")
        with self._lock:
            self._conn.executescript(_SCHEMA)
            self._conn.commit()

    # -- plumbing ----------------------------------------------------------
    @contextmanager
    def _tx(self) -> Iterator[sqlite3.Connection]:
        with self._lock:
            try:
                yield self._conn
                self._conn.commit()
            except Exception:
                self._conn.rollback()
                raise

    def close(self) -> None:
        with self._lock:
            self._conn.close()

    def _audit(
        self,
        conn: sqlite3.Connection,
        entity: str,
        entity_id: str,
        action: str,
        actor: Optional[str] = None,
        detail: Optional[str] = None,
    ) -> None:
        conn.execute(
            "INSERT INTO ledger_audit (at, entity, entity_id, action, actor, detail)"
            " VALUES (?, ?, ?, ?, ?, ?)",
            (utc_now(), entity, entity_id, action, actor, detail),
        )

    def audit_trail(self, entity: str, entity_id: str) -> List[Dict[str, Any]]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT at, entity, entity_id, action, actor, detail FROM ledger_audit"
                " WHERE entity = ? AND entity_id = ? ORDER BY id",
                (entity, entity_id),
            ).fetchall()
        return [dict(row) for row in rows]

    @staticmethod
    def _upsert(table: str, row: Dict[str, Any], key: str) -> tuple[str, Sequence[Any]]:
        columns = list(row)
        placeholders = ", ".join("?" for _ in columns)
        updates = ", ".join(f"{c} = excluded.{c}" for c in columns if c != key)
        sql = (
            f"INSERT INTO {table} ({', '.join(columns)}) VALUES ({placeholders}) "
            f"ON CONFLICT({key}) DO UPDATE SET {updates}"
        )
        return sql, [row[c] for c in columns]

    # -- predictions -------------------------------------------------------
    def record_prediction(self, record: PredictionRecord) -> str:
        existing = self.get_prediction(record.prediction_id)
        if existing is not None and existing.status == RESOLVED:
            # A resolved claim is evidence. Rewriting what we said after seeing
            # what happened is the single most damaging thing a learning system
            # can do to itself, so it is refused rather than warned about.
            raise LedgerError(
                f"prediction {record.prediction_id} is resolved and cannot be rewritten"
            )
        row = record.to_row()
        sql, values = self._upsert("predictions", row, "prediction_id")
        with self._tx() as conn:
            conn.execute(sql, values)
            self._audit(
                conn, "prediction", record.prediction_id,
                "updated" if existing else "created", record.model,
            )
        return record.prediction_id

    def record_predictions(self, records: Iterable[PredictionRecord]) -> int:
        count = 0
        for record in records:
            self.record_prediction(record)
            count += 1
        return count

    def get_prediction(self, prediction_id: str) -> Optional[PredictionRecord]:
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM predictions WHERE prediction_id = ?", (prediction_id,)
            ).fetchone()
        return PredictionRecord.from_row(dict(row)) if row else None

    def resolve_prediction(
        self,
        prediction_id: str,
        observed_value: float,
        observed_at: str,
        observation_source: str,
        metrics: Optional[Dict[str, Any]] = None,
    ) -> Optional[PredictionRecord]:
        record = self.get_prediction(prediction_id)
        if record is None:
            return None
        metrics = metrics or {}
        lead = _hours_between(record.issued_at, observed_at)
        with self._tx() as conn:
            conn.execute(
                "UPDATE predictions SET status = ?, observed_value = ?, observed_at = ?,"
                " observation_source = ?, error = ?, absolute_error = ?, brier = ?,"
                " log_loss = ?, within_interval = ?, lead_time_hours = ?"
                " WHERE prediction_id = ?",
                (
                    RESOLVED,
                    observed_value,
                    observed_at,
                    observation_source,
                    metrics.get("error"),
                    metrics.get("absolute_error"),
                    metrics.get("brier"),
                    metrics.get("log_loss"),
                    None if metrics.get("within_interval") is None
                    else int(bool(metrics["within_interval"])),
                    lead,
                    prediction_id,
                ),
            )
            self._audit(conn, "prediction", prediction_id, "resolved", observation_source)
        return self.get_prediction(prediction_id)

    def predictions(
        self,
        *,
        domain: Optional[str] = None,
        model: Optional[str] = None,
        subject: Optional[str] = None,
        status: Optional[str] = None,
        issued_before: Optional[str] = None,
        valid_before: Optional[str] = None,
        limit: Optional[int] = None,
    ) -> List[PredictionRecord]:
        clauses: List[str] = []
        params: List[Any] = []
        for column, value in (
            ("domain", domain), ("model", model), ("subject", subject), ("status", status),
        ):
            if value is not None:
                clauses.append(f"{column} = ?")
                params.append(value)
        if issued_before is not None:
            clauses.append("issued_at < ?")
            params.append(issued_before)
        if valid_before is not None:
            clauses.append("valid_at <= ?")
            params.append(valid_before)
        sql = "SELECT * FROM predictions"
        if clauses:
            sql += " WHERE " + " AND ".join(clauses)
        sql += " ORDER BY valid_at DESC, prediction_id"
        if limit:
            sql += f" LIMIT {int(limit)}"
        with self._lock:
            rows = self._conn.execute(sql, params).fetchall()
        return [PredictionRecord.from_row(dict(row)) for row in rows]

    def due_predictions(self, now: Optional[str] = None) -> List[PredictionRecord]:
        """Open claims whose ``valid_at`` has passed and can now be scored."""
        return self.predictions(status=OPEN, valid_before=now or utc_now())

    # -- decisions ---------------------------------------------------------
    def record_decision(self, record: DecisionRecord) -> str:
        row = record.to_row()
        sql, values = self._upsert("decisions", row, "decision_id")
        with self._tx() as conn:
            conn.execute(sql, values)
            self._audit(conn, "decision", record.decision_id, "created", record.issuer)
        return record.decision_id

    def get_decision(self, decision_id: str) -> Optional[DecisionRecord]:
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM decisions WHERE decision_id = ?", (decision_id,)
            ).fetchone()
        return DecisionRecord.from_row(dict(row)) if row else None

    def resolve_decision(
        self,
        decision_id: str,
        action_state: str,
        observed_outcome: Dict[str, float],
        observed_at: str,
        operational_reward: Optional[float] = None,
        impact_error: Optional[float] = None,
    ) -> Optional[DecisionRecord]:
        import json

        if self.get_decision(decision_id) is None:
            return None
        with self._tx() as conn:
            conn.execute(
                "UPDATE decisions SET status = ?, action_state = ?, observed_outcome = ?,"
                " observed_at = ?, operational_reward = ?, impact_error = ?"
                " WHERE decision_id = ?",
                (
                    RESOLVED,
                    action_state,
                    json.dumps(observed_outcome, sort_keys=True, default=str),
                    observed_at,
                    operational_reward,
                    impact_error,
                    decision_id,
                ),
            )
            self._audit(conn, "decision", decision_id, f"resolved:{action_state}")
        return self.get_decision(decision_id)

    def decisions(
        self,
        *,
        kind: Optional[str] = None,
        subject: Optional[str] = None,
        status: Optional[str] = None,
        limit: Optional[int] = None,
    ) -> List[DecisionRecord]:
        clauses: List[str] = []
        params: List[Any] = []
        for column, value in (("kind", kind), ("subject", subject), ("status", status)):
            if value is not None:
                clauses.append(f"{column} = ?")
                params.append(value)
        sql = "SELECT * FROM decisions"
        if clauses:
            sql += " WHERE " + " AND ".join(clauses)
        sql += " ORDER BY issued_at DESC, decision_id"
        if limit:
            sql += f" LIMIT {int(limit)}"
        with self._lock:
            rows = self._conn.execute(sql, params).fetchall()
        return [DecisionRecord.from_row(dict(row)) for row in rows]

    # -- event outcomes ----------------------------------------------------
    def record_event_outcome(self, record: EventOutcomeRecord) -> str:
        existing = self.get_event_outcome(record.outcome_id)
        if existing is not None and existing.status == RESOLVED:
            raise LedgerError(
                f"event outcome {record.outcome_id} is resolved and cannot be rewritten"
            )
        row = record.to_row()
        sql, values = self._upsert("event_outcomes", row, "outcome_id")
        with self._tx() as conn:
            conn.execute(sql, values)
            self._audit(conn, "event_outcome", record.outcome_id,
                        "updated" if existing else "created")
        return record.outcome_id

    def get_event_outcome(self, outcome_id: str) -> Optional[EventOutcomeRecord]:
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM event_outcomes WHERE outcome_id = ?", (outcome_id,)
            ).fetchone()
        return EventOutcomeRecord.from_row(dict(row)) if row else None

    def resolve_event_outcome(
        self,
        outcome_id: str,
        occurred: bool,
        observed_at: str,
        observation_source: str,
        observed_impact: Optional[Dict[str, float]] = None,
        metrics: Optional[Dict[str, Any]] = None,
    ) -> Optional[EventOutcomeRecord]:
        import json

        record = self.get_event_outcome(outcome_id)
        if record is None:
            return None
        metrics = metrics or {}
        # A false alarm is a confident claim that did not happen, not merely a
        # wrong one: below the confidence floor the claim was hedged and the
        # operator was told so.
        false_alarm = (not occurred) and record.predicted_probability >= 0.5
        lead = _hours_between(record.issued_at, observed_at) if occurred else None
        with self._tx() as conn:
            conn.execute(
                "UPDATE event_outcomes SET status = ?, occurred = ?, observed_at = ?,"
                " observation_source = ?, observed_impact = ?, false_alarm = ?,"
                " lead_time_hours = ?, brier = ?, log_loss = ?, impact_error = ?"
                " WHERE outcome_id = ?",
                (
                    RESOLVED,
                    int(bool(occurred)),
                    observed_at,
                    observation_source,
                    json.dumps(observed_impact or {}, sort_keys=True, default=str),
                    int(false_alarm),
                    lead,
                    metrics.get("brier"),
                    metrics.get("log_loss"),
                    metrics.get("impact_error"),
                    outcome_id,
                ),
            )
            self._audit(conn, "event_outcome", outcome_id,
                        f"resolved:{'occurred' if occurred else 'did_not_occur'}",
                        observation_source)
        return self.get_event_outcome(outcome_id)

    def event_outcomes(
        self,
        *,
        category: Optional[str] = None,
        status: Optional[str] = None,
        resolve_before: Optional[str] = None,
        limit: Optional[int] = None,
    ) -> List[EventOutcomeRecord]:
        clauses: List[str] = []
        params: List[Any] = []
        for column, value in (("category", category), ("status", status)):
            if value is not None:
                clauses.append(f"{column} = ?")
                params.append(value)
        if resolve_before is not None:
            clauses.append("resolve_by <= ?")
            params.append(resolve_before)
        sql = "SELECT * FROM event_outcomes"
        if clauses:
            sql += " WHERE " + " AND ".join(clauses)
        sql += " ORDER BY issued_at DESC, outcome_id"
        if limit:
            sql += f" LIMIT {int(limit)}"
        with self._lock:
            rows = self._conn.execute(sql, params).fetchall()
        return [EventOutcomeRecord.from_row(dict(row)) for row in rows]

    # -- reliability -------------------------------------------------------
    def upsert_reliability(self, record: ReliabilityRecord) -> None:
        row = record.to_row()
        columns = list(row)
        placeholders = ", ".join("?" for _ in columns)
        updates = ", ".join(
            f"{c} = excluded.{c}" for c in columns
            if c not in ("contributor", "context_key")
        )
        sql = (
            f"INSERT INTO reliability ({', '.join(columns)}) VALUES ({placeholders}) "
            f"ON CONFLICT(contributor, context_key) DO UPDATE SET {updates}"
        )
        with self._tx() as conn:
            conn.execute(sql, [row[c] for c in columns])

    def reliability(
        self,
        *,
        contributor: Optional[str] = None,
        context_key: Optional[str] = None,
    ) -> List[ReliabilityRecord]:
        clauses: List[str] = []
        params: List[Any] = []
        if contributor is not None:
            clauses.append("contributor = ?")
            params.append(contributor)
        if context_key is not None:
            clauses.append("context_key = ?")
            params.append(context_key)
        sql = "SELECT * FROM reliability"
        if clauses:
            sql += " WHERE " + " AND ".join(clauses)
        sql += " ORDER BY contributor, context_key"
        with self._lock:
            rows = self._conn.execute(sql, params).fetchall()
        return [ReliabilityRecord.from_row(dict(row)) for row in rows]

    # -- policies ----------------------------------------------------------
    def upsert_policy(self, record: PolicyRecord) -> None:
        row = record.to_row()
        sql, values = self._upsert("policies", row, "policy_id")
        with self._tx() as conn:
            conn.execute(sql, values)
            self._audit(conn, "policy", record.policy_id, f"upsert:{record.state}")

    def get_policy(self, policy_id: str) -> Optional[PolicyRecord]:
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM policies WHERE policy_id = ?", (policy_id,)
            ).fetchone()
        return PolicyRecord.from_row(dict(row)) if row else None

    def policies(self, *, state: Optional[str] = None) -> List[PolicyRecord]:
        sql = "SELECT * FROM policies"
        params: List[Any] = []
        if state is not None:
            sql += " WHERE state = ?"
            params.append(state)
        sql += " ORDER BY created_at DESC, policy_id"
        with self._lock:
            rows = self._conn.execute(sql, params).fetchall()
        return [PolicyRecord.from_row(dict(row)) for row in rows]

    def transition_policy(
        self,
        policy_id: str,
        target_state: str,
        *,
        actor: Optional[str] = None,
        reason: Optional[str] = None,
        evaluation: Optional[Dict[str, Any]] = None,
        safety_checks: Optional[Dict[str, bool]] = None,
    ) -> PolicyRecord:
        import json

        record = self.get_policy(policy_id)
        if record is None:
            raise LedgerError(f"unknown policy {policy_id}")
        if not can_transition(record.state, target_state):
            raise LedgerError(
                f"illegal policy transition {record.state} -> {target_state} "
                f"for {policy_id}"
            )
        if target_state == APPROVED:
            # The whole promotion workflow exists to make this impossible to
            # skip: an approved policy must carry a human approver and a
            # recorded evaluation, or it is not approved.
            merged_eval = {**record.evaluation, **(evaluation or {})}
            if not merged_eval:
                raise LedgerError(
                    f"policy {policy_id} cannot be approved without a recorded evaluation"
                )
            checks = {**record.safety_checks, **(safety_checks or {})}
            failed = [name for name, ok in checks.items() if not ok]
            if failed:
                raise LedgerError(
                    f"policy {policy_id} failed safety checks: {', '.join(sorted(failed))}"
                )
            if not actor:
                raise LedgerError(f"policy {policy_id} requires a human approver")

        now = utc_now()
        evaluation_json = (
            json.dumps({**record.evaluation, **evaluation}, sort_keys=True, default=str)
            if evaluation else None
        )
        checks_json = (
            json.dumps({**record.safety_checks, **safety_checks}, sort_keys=True)
            if safety_checks else None
        )
        with self._tx() as conn:
            conn.execute(
                "UPDATE policies SET state = ?, updated_at = ?,"
                " evaluation = COALESCE(?, evaluation),"
                " safety_checks = COALESCE(?, safety_checks),"
                " approved_by = CASE WHEN ? = 'approved' THEN ? ELSE approved_by END,"
                " approved_at = CASE WHEN ? = 'approved' THEN ? ELSE approved_at END,"
                " rejection_reason = CASE WHEN ? = 'rejected' THEN ? ELSE rejection_reason END"
                " WHERE policy_id = ?",
                (
                    target_state, now, evaluation_json, checks_json,
                    target_state, actor, target_state, now,
                    target_state, reason, policy_id,
                ),
            )
            self._audit(conn, "policy", policy_id, f"transition:{target_state}", actor, reason)
        result = self.get_policy(policy_id)
        assert result is not None
        return result

    # -- summary -----------------------------------------------------------
    def counts(self) -> Dict[str, Dict[str, int]]:
        """Row counts by status, for the learning dashboard's header."""
        out: Dict[str, Dict[str, int]] = {}
        with self._lock:
            for table in ("predictions", "decisions", "event_outcomes"):
                rows = self._conn.execute(
                    f"SELECT status, COUNT(*) AS n FROM {table} GROUP BY status"
                ).fetchall()
                out[table] = {row["status"]: int(row["n"]) for row in rows}
            out["policies"] = {
                row["state"]: int(row["n"])
                for row in self._conn.execute(
                    "SELECT state, COUNT(*) AS n FROM policies GROUP BY state"
                ).fetchall()
            }
            out["reliability"] = {
                "rows": int(
                    self._conn.execute("SELECT COUNT(*) AS n FROM reliability").fetchone()["n"]
                )
            }
        return out


# --------------------------------------------------------------------------
# helpers and the process-wide default
# --------------------------------------------------------------------------


def _parse(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def _hours_between(start: Optional[str], end: Optional[str]) -> Optional[float]:
    a, b = _parse(start), _parse(end)
    if a is None or b is None:
        return None
    return round((b - a).total_seconds() / 3600.0, 4)


def shift_iso(value: str, hours: float) -> str:
    parsed = _parse(value) or datetime.now(timezone.utc)
    return (parsed + timedelta(hours=hours)).isoformat(timespec="seconds")


_DEFAULT: Optional[SqliteLedgerStore] = None
_DEFAULT_LOCK = threading.Lock()


def get_ledger(path: Path | str | None = None) -> SqliteLedgerStore:
    """The process-wide ledger.

    The API, the pipeline and the agents all want the same rows; opening a
    second connection to the same file from three places is how a demo ends up
    reading its own half-written state.
    """
    global _DEFAULT
    if path is not None:
        return SqliteLedgerStore(path)
    with _DEFAULT_LOCK:
        if _DEFAULT is None:
            _DEFAULT = SqliteLedgerStore()
        return _DEFAULT


def reset_default_ledger() -> None:
    """Drop the cached default. Tests use this; nothing else should."""
    global _DEFAULT
    with _DEFAULT_LOCK:
        if _DEFAULT is not None:
            _DEFAULT.close()
        _DEFAULT = None


__all__ = [
    "DEFAULT_LEDGER_PATH",
    "LedgerError",
    "LedgerStore",
    "SqliteLedgerStore",
    "get_ledger",
    "reset_default_ledger",
    "shift_iso",
]
