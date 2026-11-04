"""Dated provider snapshots and attempt history for the standalone ingest worker."""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from functools import lru_cache
from statistics import median
from typing import Any, Iterator
from uuid import uuid4

from sqlalchemy import Column, Index, MetaData, String, Table, Text, create_engine, select, text
from sqlalchemy.engine import make_url
from sqlalchemy.types import JSON

from src.utils.settings import get_settings

_metadata = MetaData()
_attempts = Table(
    "portwatch_source_attempts",
    _metadata,
    Column("id", String(32), primary_key=True),
    Column("product", String(100), nullable=False),
    Column("scope", String(100), nullable=False),
    Column("finished", String(32), nullable=False),
    Column("observed", String(32)),
    Column("payload", JSON(none_as_null=True)),
    Column("error", Text),
)
Index("ix_portwatch_source_attempt_lookup", _attempts.c.scope, _attempts.c.product, _attempts.c.finished)


def utc(value: datetime) -> datetime:
    if value.utcoffset() is None:
        raise ValueError("Source timestamps must include a UTC offset")
    return value.astimezone(timezone.utc)


def _stamp(value: datetime) -> str:
    return utc(value).isoformat(timespec="microseconds")


@dataclass(frozen=True)
class Snapshot:
    payload: dict[str, Any]
    observed_at: datetime | None


@dataclass(frozen=True)
class Attempt:
    finished_at: datetime
    observed_at: datetime | None
    error: str | None

    @property
    def lag_seconds(self) -> float | None:
        if self.observed_at is None:
            return None
        return (self.finished_at - self.observed_at).total_seconds()


class SnapshotStore:
    def __init__(self, url: str):
        target = make_url(url)
        if target.get_backend_name() == "postgres":
            target = target.set(drivername="postgresql+psycopg2")
        if target.get_backend_name() not in {"postgresql", "sqlite"}:
            raise ValueError("Snapshot storage must be Postgres or local SQLite")
        options = {"connect_timeout": 4} if target.get_backend_name() == "postgresql" else {}
        self.engine = create_engine(target, pool_pre_ping=True, connect_args=options)

    def initialize(self) -> None:
        _metadata.create_all(self.engine)

    @contextmanager
    def claim(self, scope: str, product: str) -> Iterator[bool]:
        """Serialize collectors for a product across worker replicas on Postgres."""
        if self.engine.dialect.name != "postgresql":
            yield True  # Local SQLite is intended for one worker.
            return
        key = {"scope": scope, "product": product}
        with self.engine.connect() as conn:
            acquired = conn.execute(
                text("select pg_try_advisory_lock(hashtext(:scope), hashtext(:product))"), key
            ).scalar()
            conn.commit()
            try:
                yield bool(acquired)
            finally:
                if acquired:
                    conn.execute(
                        text("select pg_advisory_unlock(hashtext(:scope), hashtext(:product))"), key
                    )

    def record(
        self, scope: str, product: str, finished: datetime,
        *, snapshot: Snapshot | None = None, error: str | None = None,
    ) -> None:
        if (snapshot is None) == (error is None):
            raise ValueError("Record exactly one snapshot or error")
        observed = snapshot.observed_at if snapshot else None
        if observed is not None and utc(observed) > utc(finished):
            raise ValueError("Observation or issue time is in the future")
        with self.engine.begin() as conn:
            conn.execute(_attempts.insert().values(
                id=uuid4().hex, scope=scope, product=product, finished=_stamp(finished),
                observed=_stamp(observed) if observed is not None else None,
                payload=snapshot.payload if snapshot else None, error=error,
            ))

    def _for(self, scope: str, product: str):
        return (_attempts.c.scope == scope, _attempts.c.product == product)

    def latest(self, scope: str, product: str) -> Snapshot | None:
        query = select(_attempts.c.payload, _attempts.c.observed).where(
            *self._for(scope, product), _attempts.c.error.is_(None),
        ).order_by(_attempts.c.finished.desc()).limit(1)
        with self.engine.connect() as conn:
            row = conn.execute(query).first()
        return Snapshot(row.payload, datetime.fromisoformat(row.observed) if row.observed else None) if row else None

    def attempts(
        self, scope: str, product: str, *, since: datetime | None = None,
        until: datetime | None = None, limit: int | None = None, successful: bool = False,
    ) -> list[Attempt]:
        query = select(_attempts.c.finished, _attempts.c.observed, _attempts.c.error).where(
            *self._for(scope, product)
        ).order_by(_attempts.c.finished.desc())
        if since is not None:
            query = query.where(_attempts.c.finished >= _stamp(since))
        if until is not None:
            query = query.where(_attempts.c.finished <= _stamp(until))
        if successful:
            query = query.where(_attempts.c.error.is_(None))
        if limit is not None:
            query = query.limit(limit)
        with self.engine.connect() as conn:
            return [
                Attempt(datetime.fromisoformat(row.finished),
                        datetime.fromisoformat(row.observed) if row.observed else None, row.error)
                for row in conn.execute(query)
            ]

    def health(self, scope: str, product: str, now: datetime, max_age: timedelta) -> dict[str, Any]:
        week = self.attempts(scope, product, since=now - timedelta(days=7), until=now)
        successes = [item for item in week if item.error is None]
        last = successes[:1] or self.attempts(scope, product, until=now, limit=1, successful=True)
        latest = last[0] if last else None
        lags = [item.lag_seconds for item in successes if item.lag_seconds is not None]
        state = "unavailable"
        if latest:
            state = "live" if latest.observed_at and now - latest.observed_at <= max_age else "stale"
        return {
            "status": state,
            "lastSuccess": latest.finished_at if latest else None,
            "observedAt": latest.observed_at if latest else None,
            "successRate7d": len(successes) / len(week) if week else None,
            "attempts7d": len(week),
            "medianLagSeconds": median(lags) if lags else None,
        }


@lru_cache(maxsize=2)
def _open(url: str) -> SnapshotStore:
    return SnapshotStore(url)


def configured_store() -> SnapshotStore | None:
    url = get_settings().PORTWATCH_SOURCE_SNAPSHOT_URL
    return _open(url) if url else None
