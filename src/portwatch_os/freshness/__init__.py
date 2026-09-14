"""Freshness: artifacts kept current by policy, not by an operator's memory.

    FreshnessPolicy     what "current" means for one artifact: SLA, lead, stale
    RefreshJob          how to probe an artifact's own instant and how to refresh it
    RefreshResult       what one attempt did, kept whether it succeeded or not
    RefreshCoordinator  runs due jobs, once each, with bounded backoff, and tells
                        only the dependants of a changed artifact

See :mod:`src.portwatch_os.freshness.jobs` for the product's own artifacts.
"""

from src.portwatch_os.freshness.coordinator import (
    RefreshCoordinator,
    get_coordinator,
    reset_coordinator,
    set_coordinator,
)
from src.portwatch_os.freshness.job import JobOutcome, RefreshContext, RefreshJob, RefreshResult
from src.portwatch_os.freshness.policy import (
    ARTIFACT_STATES,
    DISABLED,
    DUE,
    EXPIRED,
    FAILED,
    FRESH,
    IDLE,
    JOB_STATES,
    MISSING,
    NOT_APPLICABLE,
    RETRY_SCHEDULED,
    RUNNING,
    SIMULATED,
    STALE,
    ArtifactProbe,
    FreshnessPolicy,
)

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
    "JobOutcome",
    "MISSING",
    "NOT_APPLICABLE",
    "RETRY_SCHEDULED",
    "RUNNING",
    "RefreshContext",
    "RefreshCoordinator",
    "RefreshJob",
    "RefreshResult",
    "SIMULATED",
    "STALE",
    "get_coordinator",
    "reset_coordinator",
    "set_coordinator",
]
