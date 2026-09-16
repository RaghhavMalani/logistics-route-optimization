"""The refresh coordinator: artifacts kept current without an operator.

Responsibilities, each of which has a test:

*   **know the SLA** of every artifact, from its policy;
*   **refresh before expiry**: a job is due ``lead`` before its SLA elapses,
    and the scheduler runs due jobs on every tick;
*   **never run the same job twice at once**: a request for a running job
    joins it rather than starting another;
*   **preserve the last known good**: a job that fails leaves the artifact
    and its instant untouched, and the state says EXPIRED or STALE from the
    real age -- never FRESH because a timestamp was rewritten;
*   **expose failure**: every attempt's result is kept, with its error;
*   **retry with bounded backoff**: attempts double their wait up to a cap
    and stop at ``max_attempts`` until the next scheduler cycle;
*   **invalidate only what changed**: when an artifact changes, the artifacts
    it feeds are told, and nothing else is.

The coordinator measures age on the wall, and says so: how old a file is on
disk is a fact about the real present whatever mode the WorldClock is in. A
mission replayed at 2021 still runs on a 2026 event register whose age is
measured in 2026.
"""

from __future__ import annotations

import logging
import threading
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Callable, Dict, List, Optional

from src.portwatch_os import telemetry
from src.portwatch_os.clock import wall_now
from src.portwatch_os.freshness.job import JobOutcome, RefreshContext, RefreshJob, RefreshResult
from src.portwatch_os.freshness.policy import (
    DISABLED,
    DUE,
    EXPIRED,
    FAILED,
    FRESH,
    IDLE,
    MISSING,
    NOT_APPLICABLE,
    RETRY_SCHEDULED,
    RUNNING,
    SIMULATED,
    STALE,
    ArtifactProbe,
)

log = logging.getLogger(__name__)

#: Results kept per artifact, newest last.
HISTORY = 12


@dataclass
class JobRecord:
    """The coordinator's own memory of one job."""

    job: RefreshJob
    running: bool = False
    attempts_this_cycle: int = 0
    next_attempt_at: Optional[datetime] = None
    last_result: Optional[RefreshResult] = None
    last_good: Optional[RefreshResult] = None
    history: List[RefreshResult] = field(default_factory=list)
    invalidated_by: List[str] = field(default_factory=list)
    lock: threading.Lock = field(default_factory=threading.Lock)
    thread: Optional[threading.Thread] = None

    def job_state(self, now: datetime) -> str:
        if self.running:
            return RUNNING
        if self.job.eligibility() is not None:
            return DISABLED
        failed = self.last_result is not None and not self.last_result.ok and not self.last_result.skipped
        if failed and self.attempts_this_cycle >= self.job.policy.max_attempts:
            # Out of attempts: FAILED until the hold-off elapses and a new
            # cycle may begin, however the next attempt is scheduled.
            return FAILED
        if self.next_attempt_at is not None and self.next_attempt_at > now:
            return RETRY_SCHEDULED
        if failed:
            return RETRY_SCHEDULED
        return IDLE


class RefreshCoordinator:
    """Keeps every registered artifact within its policy. One per process."""

    def __init__(self, *, tick_seconds: float = 30.0, max_concurrent: int = 2) -> None:
        self._records: Dict[str, JobRecord] = {}
        self._lock = threading.RLock()
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self.tick_seconds = tick_seconds
        self.max_concurrent = max_concurrent
        self.ticks = 0

    # -- registration ----------------------------------------------------
    def register(self, job: RefreshJob) -> None:
        with self._lock:
            if job.artifact in self._records:
                raise ValueError(f"artifact {job.artifact} is already registered")
            self._records[job.artifact] = JobRecord(job=job)

    def artifacts(self) -> List[str]:
        with self._lock:
            return list(self._records)

    def record(self, artifact: str) -> JobRecord:
        with self._lock:
            try:
                return self._records[artifact]
            except KeyError:
                raise KeyError(f"no artifact {artifact}; known: {', '.join(sorted(self._records))}") from None

    # -- probing ---------------------------------------------------------
    def probe(self, artifact: str) -> ArtifactProbe:
        job = self.record(artifact).job
        try:
            return job.probe()
        except Exception as exc:  # noqa: BLE001 - an unreadable artifact is a missing one
            return ArtifactProbe(observed_at=None, reason=f"probe failed: {type(exc).__name__}: {exc}")

    def age(self, artifact: str, *, now: Optional[datetime] = None) -> Optional[timedelta]:
        probe = self.probe(artifact)
        if probe.observed_at is None:
            return None
        moment = now or wall_now()  # wall-clock: an artifact's age is measured in the real present
        return max(timedelta(0), moment - probe.observed_at)

    def artifact_state(self, artifact: str, *, now: Optional[datetime] = None) -> str:
        record = self.record(artifact)
        probe = self.probe(artifact)
        if probe.override_state in (NOT_APPLICABLE, SIMULATED):
            return probe.override_state
        if probe.observed_at is None:
            return MISSING
        moment = now or wall_now()  # wall-clock: see age()
        return record.job.policy.state_for(max(timedelta(0), moment - probe.observed_at))

    # -- scheduling ------------------------------------------------------
    def due(self, *, now: Optional[datetime] = None) -> List[str]:
        """Artifacts whose job should run now, in registration order."""
        moment = now or wall_now()  # wall-clock: scheduling happens in the real present
        out: List[str] = []
        with self._lock:
            for artifact, record in self._records.items():
                if not record.job.refreshable or record.running:
                    continue
                if record.job.eligibility() is not None:
                    continue
                if record.next_attempt_at is not None and record.next_attempt_at > moment:
                    continue
                state = self.artifact_state(artifact, now=moment)
                if state in (FRESH, NOT_APPLICABLE, SIMULATED):
                    continue
                if state in (MISSING, DUE, EXPIRED, STALE):
                    failed_out = (
                        record.last_result is not None and not record.last_result.ok
                        and not record.last_result.skipped
                        and record.attempts_this_cycle >= record.job.policy.max_attempts
                    )
                    if failed_out and record.next_attempt_at is not None and record.next_attempt_at > moment:
                        continue
                    out.append(artifact)
        return out

    def tick(self, *, now: Optional[datetime] = None, wait: bool = False) -> List[str]:
        """Run every due job. Returns the artifacts started."""
        moment = now or wall_now()  # wall-clock: see due()
        self.ticks += 1
        started: List[str] = []
        with self._lock:
            running = sum(1 for r in self._records.values() if r.running)
        for artifact in self.due(now=moment):
            if running >= self.max_concurrent:
                break
            if self.request(artifact, reason="scheduled", now=moment, wait=wait) == "started":
                started.append(artifact)
                running += 1
        telemetry.gauge("freshness.ticks", self.ticks)
        return started

    def request(
        self, artifact: str, *, reason: str, now: Optional[datetime] = None,
        wait: bool = False, requested: bool = False,
    ) -> str:
        """Start a job unless it is already running. Returns what happened."""
        record = self.record(artifact)
        job = record.job
        if not job.refreshable:
            return "not refreshable"
        barred = job.eligibility()
        if barred is not None:
            return f"disabled: {barred}"
        with record.lock:
            if record.running:
                return "already running"
            record.running = True
            record.thread = None
        moment = now or wall_now()  # wall-clock: the attempt starts in the real present

        def body() -> None:
            try:
                self._run(record, reason=reason, now=moment, requested=requested)
            finally:
                with record.lock:
                    record.running = False

        if wait:
            body()
            return "started"
        thread = threading.Thread(target=body, name=f"refresh-{artifact}", daemon=True)
        record.thread = thread
        thread.start()
        return "started"

    def wait(self, artifact: str, timeout: float = 600.0) -> Optional[RefreshResult]:
        record = self.record(artifact)
        thread = record.thread
        if thread is not None:
            thread.join(timeout)
        return record.last_result

    # -- the attempt -------------------------------------------------------
    def _run(self, record: JobRecord, *, reason: str, now: datetime, requested: bool) -> RefreshResult:
        job = record.job
        policy = job.policy
        # A manual request resets the bounded cycle: the operator asked.
        if requested or (record.last_result is not None and record.last_result.ok):
            record.attempts_this_cycle = 0
        record.attempts_this_cycle += 1
        attempt = record.attempts_this_cycle
        context = RefreshContext(artifact=policy.artifact, started_at=now, attempt=attempt,
                                 reason=reason, requested=requested)
        telemetry.incr("freshness.attempts", artifact=policy.artifact)
        log.info("refresh %s: attempt %d (%s)", policy.artifact, attempt, reason)
        try:
            assert job.run is not None
            with telemetry.timed("freshness.job", artifact=policy.artifact):
                outcome = job.run(context)
            if not isinstance(outcome, JobOutcome):
                raise TypeError(f"{policy.artifact}: the job returned {type(outcome).__name__}, not JobOutcome")
            finished = wall_now()  # wall-clock: the attempt ended in the real present
            if outcome.skipped_reason:
                result = RefreshResult(
                    artifact=policy.artifact, ok=True, skipped=True, started_at=now, finished_at=finished,
                    attempt=attempt, reason=reason, detail={"skipped": outcome.skipped_reason, **outcome.detail},
                )
            else:
                result = RefreshResult(
                    artifact=policy.artifact, ok=True, started_at=now, finished_at=finished, attempt=attempt,
                    reason=reason, changed=outcome.changed, observed_at=outcome.observed_at, detail=outcome.detail,
                )
        except Exception as exc:  # noqa: BLE001 - every failure is a result
            finished = wall_now()  # wall-clock: see above
            result = RefreshResult(
                artifact=policy.artifact, ok=False, started_at=now, finished_at=finished, attempt=attempt,
                reason=reason, error=f"{type(exc).__name__}: {exc}",
            )
            log.warning("refresh %s failed (attempt %d): %s", policy.artifact, attempt, result.error)

        with record.lock:
            record.last_result = result
            record.history.append(result)
            del record.history[:-HISTORY]
            if result.ok and not result.skipped:
                record.last_good = result
                record.attempts_this_cycle = 0
                record.next_attempt_at = None
                record.invalidated_by = []
                telemetry.incr("freshness.succeeded", artifact=policy.artifact)
            elif result.ok:
                record.next_attempt_at = None
                telemetry.incr("freshness.skipped", artifact=policy.artifact)
            else:
                telemetry.incr("freshness.failed", artifact=policy.artifact)
                telemetry.event("freshness.failures", artifact=policy.artifact, attempt=attempt, error=result.error)
                if attempt < policy.max_attempts:
                    record.next_attempt_at = finished + policy.backoff(attempt + 1)
                else:
                    # Out of attempts for this cycle: hold off a full cap, then
                    # the scheduler may try a new cycle.
                    record.next_attempt_at = finished + policy.backoff_cap
                    record.attempts_this_cycle = policy.max_attempts

        if result.ok and result.changed:
            self._propagate(policy.artifact)
            if job.on_changed is not None:
                try:
                    job.on_changed(result)
                except Exception as exc:  # noqa: BLE001 - a hook must not fail the refresh
                    log.warning("on_changed for %s raised: %s", policy.artifact, exc)
        return result

    def _propagate(self, changed: str) -> None:
        """Tell only the artifacts fed by ``changed`` that their input moved."""
        with self._lock:
            policy = self._records[changed].job.policy
            dependants = [a for a in policy.feeds if a in self._records]
        for artifact in dependants:
            record = self._records[artifact]
            with record.lock:
                record.invalidated_by.append(changed)
            telemetry.incr("freshness.invalidations", artifact=artifact, source=changed)
            if record.job.invalidate is not None:
                try:
                    record.job.invalidate(changed)
                except Exception as exc:  # noqa: BLE001
                    log.warning("invalidate %s (by %s) raised: %s", artifact, changed, exc)

    # -- the background scheduler ------------------------------------------
    def start(self) -> None:
        if self._thread is not None and self._thread.is_alive():
            return
        self._stop.clear()

        def loop() -> None:
            while not self._stop.is_set():
                try:
                    self.tick()
                except Exception as exc:  # noqa: BLE001 - the scheduler must survive a bad tick
                    log.warning("freshness tick raised: %s", exc)
                self._stop.wait(self.tick_seconds)

        self._thread = threading.Thread(target=loop, name="freshness-coordinator", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=5.0)

    @property
    def running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    # -- the trust surface -------------------------------------------------
    def status(self, *, now: Optional[datetime] = None) -> Dict[str, Any]:
        moment = now or wall_now()  # wall-clock: ages are real
        rows = []
        for artifact in self.artifacts():
            rows.append(self.describe(artifact, now=moment))
        return {
            "at": moment.isoformat(timespec="seconds"),
            "scheduler": {"running": self.running, "tickSeconds": self.tick_seconds, "ticks": self.ticks},
            "artifacts": rows,
            "summary": {
                state: sum(1 for r in rows if r["state"] == state)
                for state in (FRESH, DUE, EXPIRED, STALE, MISSING, NOT_APPLICABLE, SIMULATED)
            },
        }

    def describe(self, artifact: str, *, now: Optional[datetime] = None) -> Dict[str, Any]:
        moment = now or wall_now()  # wall-clock: ages are real
        record = self.record(artifact)
        policy = record.job.policy
        probe = self.probe(artifact)
        state = self.artifact_state(artifact, now=moment)
        age = None if probe.observed_at is None else max(timedelta(0), moment - probe.observed_at)
        lag = (
            None if probe.source_timestamp is None or probe.observed_at is None
            else max(timedelta(0), probe.observed_at - probe.source_timestamp)
        )
        expires_at = None if probe.observed_at is None else probe.observed_at + policy.fresh_for
        with record.lock:
            job_state = record.job_state(moment)
            last = record.last_result.to_dict() if record.last_result else None
            good = record.last_good.to_dict() if record.last_good else None
            history = [r.to_dict() for r in record.history[-5:]]
            invalidated = list(record.invalidated_by)
            attempts = record.attempts_this_cycle
            next_attempt = record.next_attempt_at
        return {
            "artifact": artifact,
            "label": policy.label or artifact,
            "provider": policy.provider,
            "state": state,
            "ageSeconds": None if age is None else round(age.total_seconds(), 1),
            "observedAt": None if probe.observed_at is None else probe.observed_at.isoformat(timespec="seconds"),
            "sourceTimestamp": (
                None if probe.source_timestamp is None else probe.source_timestamp.isoformat(timespec="seconds")
            ),
            "sourceLagSeconds": None if lag is None else round(lag.total_seconds(), 1),
            "expiresAt": None if expires_at is None else expires_at.isoformat(timespec="seconds"),
            "reason": probe.reason,
            "detail": dict(probe.detail),
            "policy": policy.to_dict(),
            "job": {
                "refreshable": record.job.refreshable,
                "state": job_state,
                "eligibility": record.job.eligibility(),
                "attemptsThisCycle": attempts,
                "nextAttemptAt": None if next_attempt is None else next_attempt.isoformat(timespec="seconds"),
                "lastResult": last,
                "lastGood": good,
                "history": history,
                "invalidatedBy": invalidated,
            },
        }


_COORDINATOR: Optional[RefreshCoordinator] = None
_COORDINATOR_LOCK = threading.Lock()


def get_coordinator() -> RefreshCoordinator:
    global _COORDINATOR
    with _COORDINATOR_LOCK:
        if _COORDINATOR is None:
            _COORDINATOR = RefreshCoordinator()
        return _COORDINATOR


def set_coordinator(coordinator: Optional[RefreshCoordinator]) -> None:
    global _COORDINATOR
    with _COORDINATOR_LOCK:
        if _COORDINATOR is not None and _COORDINATOR is not coordinator:
            _COORDINATOR.stop()
        _COORDINATOR = coordinator


def reset_coordinator() -> None:
    set_coordinator(None)


__all__ = [
    "HISTORY",
    "JobRecord",
    "RefreshCoordinator",
    "get_coordinator",
    "reset_coordinator",
    "set_coordinator",
]
