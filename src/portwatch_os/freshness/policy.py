"""Freshness policy: what "current" means for each artifact, in writing.

An artifact is a thing the product serves that came from somewhere else at
some instant: the event register, the marine grid, the port forecasts, the
macro series, the traffic feed. Each has a different natural cadence, and a
single "refresh every fifteen minutes" would either hammer a daily source or
let an hourly one lapse. So the cadence is a policy per artifact, stated in
three durations:

    fresh_for      the SLA. Within this age of its own recorded instant the
                   artifact is FRESH.
    lead           how long before the SLA elapses the coordinator starts a
                   refresh, so a healthy source never lapses at all.
    stale_after    past this age the artifact is STALE: still served as the
                   last known good, and labelled so on every surface.

Between ``fresh_for`` and ``stale_after`` the artifact is EXPIRED -- served,
labelled, and being refreshed. The states are computed from the artifact's
own recorded timestamp against the wall. Nothing here, and nothing in the
coordinator, ever writes a timestamp to make an artifact look current: a
failed refresh leaves the previous file and its previous instant in place.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Dict, Optional, Tuple

# Artifact states, from the artifact's own instant.
MISSING = "MISSING"          # no artifact has ever been produced here
FRESH = "FRESH"              # within the SLA
DUE = "DUE"                  # within `lead` of the SLA; a refresh is scheduled
EXPIRED = "EXPIRED"          # past the SLA; last known good, labelled, refreshing
STALE = "STALE"              # past stale_after; last known good, labelled stale
NOT_APPLICABLE = "NOT_APPLICABLE"  # the artifact cannot exist in this deployment (licence, no key)
SIMULATED = "SIMULATED"      # a deterministic replay stands in; freshness is not the question

ARTIFACT_STATES = (MISSING, FRESH, DUE, EXPIRED, STALE, NOT_APPLICABLE, SIMULATED)

# Job states, from the coordinator's own record.
IDLE = "IDLE"
RUNNING = "RUNNING"
RETRY_SCHEDULED = "RETRY_SCHEDULED"
FAILED = "FAILED"            # every bounded attempt failed; waiting for the next cycle
DISABLED = "DISABLED"        # the job may not run here, and says why

JOB_STATES = (IDLE, RUNNING, RETRY_SCHEDULED, FAILED, DISABLED)


@dataclass(frozen=True)
class FreshnessPolicy:
    """One artifact's cadence and where it comes from."""

    artifact: str
    provider: str
    fresh_for: timedelta
    stale_after: timedelta
    lead: timedelta = timedelta(0)
    #: Bounded retry: attempts per cycle, base delay, cap.
    max_attempts: int = 3
    backoff_base: timedelta = timedelta(seconds=30)
    backoff_cap: timedelta = timedelta(minutes=15)
    #: Artifacts recomputed from this one. When this one changes, they are
    #: invalidated -- and nothing else is.
    feeds: Tuple[str, ...] = ()
    #: Why the cadence is what it is, for the diagnostics page.
    rationale: str = ""
    #: Human label.
    label: str = ""

    def __post_init__(self) -> None:
        if self.fresh_for <= timedelta(0):
            raise ValueError(f"{self.artifact}: fresh_for must be positive")
        if self.stale_after < self.fresh_for:
            raise ValueError(f"{self.artifact}: stale_after must not be shorter than fresh_for")
        if self.lead < timedelta(0) or self.lead >= self.fresh_for:
            raise ValueError(f"{self.artifact}: lead must be within [0, fresh_for)")
        if self.max_attempts < 1:
            raise ValueError(f"{self.artifact}: at least one attempt")

    def state_for(self, age: Optional[timedelta]) -> str:
        if age is None:
            return MISSING
        if age > self.stale_after:
            return STALE
        if age > self.fresh_for:
            return EXPIRED
        if age >= self.fresh_for - self.lead:
            return DUE
        return FRESH

    def backoff(self, attempt: int) -> timedelta:
        """Delay before attempt ``attempt`` (1-based); doubles, capped."""
        exponent = max(0, attempt - 1)
        delay = self.backoff_base * (2 ** exponent)
        return min(delay, self.backoff_cap)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "artifact": self.artifact,
            "label": self.label or self.artifact,
            "provider": self.provider,
            "freshForSeconds": self.fresh_for.total_seconds(),
            "leadSeconds": self.lead.total_seconds(),
            "staleAfterSeconds": self.stale_after.total_seconds(),
            "maxAttempts": self.max_attempts,
            "backoffBaseSeconds": self.backoff_base.total_seconds(),
            "backoffCapSeconds": self.backoff_cap.total_seconds(),
            "feeds": list(self.feeds),
            "rationale": self.rationale,
        }


@dataclass(frozen=True)
class ArtifactProbe:
    """What the artifact says about itself right now. Read, never written."""

    #: When the artifact was produced or fetched, from its own record.
    observed_at: Optional[datetime]
    #: The instant of the newest underlying data, where the artifact states one.
    source_timestamp: Optional[datetime] = None
    #: NOT_APPLICABLE / SIMULATED with the reason, when freshness is not the question.
    override_state: Optional[str] = None
    reason: str = ""
    detail: Dict[str, Any] = field(default_factory=dict)


__all__ = [
    "ARTIFACT_STATES",
    "ArtifactProbe",
    "DISABLED",
    "DUE",
    "EXPIRED",
    "FAILED",
    "FRESH",
    "FreshnessPolicy",
    "IDLE",
    "JOB_STATES",
    "MISSING",
    "NOT_APPLICABLE",
    "RETRY_SCHEDULED",
    "RUNNING",
    "SIMULATED",
    "STALE",
]
