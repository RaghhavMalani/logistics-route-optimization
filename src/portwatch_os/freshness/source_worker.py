"""Run source jobs in a dedicated process. No API dependency imports collectors."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta

from src.portwatch_os.clock import wall_now
from src.portwatch_os.fabric.licence import ALLOWED
from src.portwatch_os.fabric.model import deployment_mode
from src.portwatch_os.fabric.products import ProviderProduct
from src.portwatch_os.freshness.source_snapshots import Attempt, Snapshot, SnapshotStore

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class SourceJob:
    product: ProviderProduct
    collect: Callable[[], Snapshot]
    cadence: timedelta
    scope: str
    trial_permitted: bool = False
    publication_approved: bool = False
    retry_base: timedelta = timedelta(seconds=30)
    retry_limit: int = 3
    breaker_cooldown: timedelta = timedelta(minutes=15)

    def __post_init__(self) -> None:
        licence = self.product.policy
        evidence = licence.evidence
        if not (evidence.reviewed_at and evidence.finding and evidence.checked_urls):
            raise ValueError("Collection requires product-specific terms evidence")
        if self.scope == "published":
            if (not self.publication_approved or licence.redistribution != ALLOWED
                    or not licence.permits(deployment_mode())[0]):
                raise ValueError("Publication requires deployment permission, redistribution permission and trial approval")
        elif not self.scope.startswith("trial-") or not self.trial_permitted:
            raise ValueError("Trial collection requires verified permission and an isolated trial scope")
        if min(self.cadence, self.retry_base, self.breaker_cooldown) <= timedelta(0) or self.retry_limit < 1:
            raise ValueError("Cadence, retry and circuit breaker settings must be positive")

    def next_attempt(self, attempts: list[Attempt], now: datetime) -> datetime:
        if not attempts:
            return now
        latest = attempts[0]
        if latest.error is None:
            return latest.finished_at + self.cadence
        failures = 0
        for attempt in attempts:
            if attempt.error is None:
                break
            failures += 1
        if failures >= self.retry_limit:
            return latest.finished_at + self.breaker_cooldown
        return latest.finished_at + min(self.breaker_cooldown, self.retry_base * 2 ** (failures - 1))


def collect_due(store: SnapshotStore, job: SourceJob, clock: Callable[[], datetime] = wall_now) -> bool:
    product = job.product.product_id
    with store.claim(job.scope, product) as acquired:
        if not acquired:
            return False
        now = clock()
        attempts = store.attempts(job.scope, product, limit=job.retry_limit)
        if job.next_attempt(attempts, now) > now:
            return False
        try:
            sample = job.collect()
            store.record(job.scope, product, clock(), snapshot=sample)
        except Exception as exc:
            # Provider errors may contain URL credentials or response bodies.
            log.warning("Source %s collection failed (%s)", product, type(exc).__name__)
            store.record(job.scope, product, clock(), error=type(exc).__name__)
        return True


async def run_worker(store: SnapshotStore, jobs: list[SourceJob], *, until: datetime) -> None:
    async def run(job: SourceJob) -> None:
        # wall-clock: a source trial ends after elapsed time, even during app replay.
        while wall_now() < until:
            try:
                await asyncio.to_thread(collect_due, store, job)
            except Exception as exc:
                log.error("Snapshot storage failed for %s (%s)", job.product.product_id, type(exc).__name__)
            await asyncio.sleep(min(5, job.cadence.total_seconds()))

    await asyncio.gather(*(run(job) for job in jobs))
