"""Refresh jobs and their results.

A job is the one thing that may produce a new version of an artifact. It is
given a context (the wall instant, the attempt number, why it was asked to
run) and returns a result that says what happened -- succeeded and changed
something, succeeded and found nothing new, or failed with the error. A job
never touches the artifact's recorded instant except by producing a new
artifact; a failure leaves the last known good exactly as it was.

Jobs are plain callables so the product's own refreshers (the event register
build, the marine fetch, the pipeline run) can be wrapped without being
rewritten, and so a test can register a scripted one.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable, Dict, Optional, Tuple

from src.portwatch_os.freshness.policy import ArtifactProbe, FreshnessPolicy


@dataclass(frozen=True)
class RefreshContext:
    artifact: str
    started_at: datetime
    attempt: int
    reason: str
    #: True when an operator or the startup command asked, not the scheduler.
    requested: bool = False


@dataclass
class RefreshResult:
    """What one attempt did."""

    artifact: str
    ok: bool
    started_at: datetime
    finished_at: datetime
    attempt: int
    reason: str
    #: True when the artifact's content is different from before.
    changed: bool = False
    #: The new artifact's own instant, when the job knows it.
    observed_at: Optional[datetime] = None
    error: Optional[str] = None
    #: Short facts for the diagnostics page: rows, cells, bytes written.
    detail: Dict[str, Any] = field(default_factory=dict)
    #: True when the job declined to run because it may not (licence, no key).
    skipped: bool = False

    @property
    def duration_seconds(self) -> float:
        return max(0.0, (self.finished_at - self.started_at).total_seconds())

    def to_dict(self) -> Dict[str, Any]:
        return {
            "artifact": self.artifact,
            "ok": self.ok,
            "skipped": self.skipped,
            "changed": self.changed,
            "startedAt": self.started_at.isoformat(timespec="seconds"),
            "finishedAt": self.finished_at.isoformat(timespec="seconds"),
            "durationSeconds": round(self.duration_seconds, 2),
            "attempt": self.attempt,
            "reason": self.reason,
            "observedAt": None if self.observed_at is None else self.observed_at.isoformat(timespec="seconds"),
            "error": self.error,
            "detail": dict(self.detail),
        }


#: A job body: given the context, do the work and describe it. It may raise;
#: the coordinator turns an exception into a failed result.
JobBody = Callable[[RefreshContext], "JobOutcome"]


@dataclass
class JobOutcome:
    """What a job body returns. Small on purpose."""

    changed: bool = False
    observed_at: Optional[datetime] = None
    detail: Dict[str, Any] = field(default_factory=dict)
    skipped_reason: Optional[str] = None


@dataclass
class RefreshJob:
    """An artifact, its policy, how to probe it and how to refresh it."""

    policy: FreshnessPolicy
    probe: Callable[[], ArtifactProbe]
    run: Optional[JobBody] = None
    #: Returns a reason when the job may not run in this deployment, else None.
    eligibility: Callable[[], Optional[str]] = lambda: None
    #: Called with the result when this job changed its artifact, after the
    #: dependants have been invalidated.
    on_changed: Optional[Callable[[RefreshResult], None]] = None
    #: Called when an upstream artifact this one feeds from changed.
    invalidate: Optional[Callable[[str], None]] = None

    @property
    def artifact(self) -> str:
        return self.policy.artifact

    @property
    def refreshable(self) -> bool:
        return self.run is not None


__all__ = ["JobBody", "JobOutcome", "RefreshContext", "RefreshJob", "RefreshResult"]
