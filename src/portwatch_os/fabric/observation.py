"""Observations: what a provider actually said, and how much to believe it.

The registry answers "may we use this source". This module answers the harder
question that follows: *this particular reading arrived — is it any good?*

Every observation carries its own provenance and its own verdict. That is not
bookkeeping for its own sake. A world model assembled from several sources has
to be able to say, of any number on screen, which provider produced it, when
that provider observed it, when we received it, how long it stays true and
whether anything about it looked wrong on arrival. Without that, a stale reading
and a fresh one are indistinguishable the moment they are drawn on the same map.

Three distinctions the rest of the system depends on:

*   **Source time is not ingest time.** A forecast issued six hours ago and
    fetched thirty seconds ago is six hours old, not thirty seconds old, and a
    freshness indicator built on the wrong one is worse than none.
*   **Valid-until is not a guess about the future.** It is what the provider
    says about its own reading, or a stated assumption where the provider says
    nothing. Where it is assumed, it says so.
*   **A failed quality check is not a discarded observation.** It is a recorded
    one that the world layer may decline to use. Silently dropping bad readings
    hides that a source has started producing them.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Sequence, Tuple

from src.portwatch_os.fabric.model import MODES

# --------------------------------------------------------------------------
# quality
# --------------------------------------------------------------------------

#: Nothing about this reading looked wrong.
OK = "OK"
#: Usable, with a caveat worth carrying to whoever reads it.
DEGRADED = "DEGRADED"
#: Kept for the record, not fit to draw. The world layer declines it.
REJECTED = "REJECTED"

QUALITY_LEVELS: Tuple[str, ...] = (OK, DEGRADED, REJECTED)

#: A reading whose source time is further ahead of us than this is not a
#: forecast, it is a clock problem, and treating it as observation would place
#: a vessel somewhere it has not been yet.
MAX_CLOCK_SKEW_MINUTES = 5.0


@dataclass(frozen=True)
class QualityVerdict:
    """What the checks made of one observation."""

    level: str
    reasons: Tuple[str, ...] = ()

    @property
    def usable(self) -> bool:
        return self.level in (OK, DEGRADED)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "level": self.level,
            "usable": self.usable,
            "reasons": list(self.reasons),
        }


GOOD = QualityVerdict(OK)


class ObservationError(ValueError):
    """An observation was constructed that cannot be reasoned about."""


@dataclass(frozen=True)
class Observation:
    """One reading from one provider, with everything needed to judge it."""

    provider_id: str
    capability: str
    #: The payload, already normalised into whatever shape the capability uses.
    value: Any

    #: When the provider observed or issued it. Not when we fetched it.
    source_timestamp: datetime
    #: When this deployment received it.
    ingested_at: datetime
    #: The window this reading describes. ``valid_to`` of ``None`` means the
    #: provider stated no expiry, which is different from "valid forever".
    valid_from: Optional[datetime] = None
    valid_to: Optional[datetime] = None
    #: True when ``valid_to`` is this deployment's assumption rather than the
    #: provider's statement. Surfaced so an operator can tell them apart.
    validity_assumed: bool = False
    #: False when the payload carried no time of its own and the value above is
    #: a stand-in. Freshness then reports UNKNOWN rather than a number computed
    #: from a timestamp nobody supplied -- the alternative is an artefact of
    #: unknown age confidently reporting itself as LIVE.
    source_time_known: bool = True

    #: Where in the world this reading applies. Free text, matching the
    #: registry's coverage field -- a claim to more precision than we have
    #: would be its own kind of dishonesty.
    coverage: str = "unspecified"
    #: The deployment mode this was gathered under, so a payload cannot be
    #: reused in a mode its licence does not permit.
    licence_mode: str = "RESEARCH"

    quality: QualityVerdict = GOOD
    #: Anything the adapter wants to carry: upstream ids, units, revision.
    provenance: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.licence_mode not in MODES:
            raise ObservationError(
                f"{self.licence_mode!r} is not a deployment mode"
            )
        if self.quality.level not in QUALITY_LEVELS:
            raise ObservationError(f"{self.quality.level!r} is not a quality level")

    # -- time ------------------------------------------------------------
    def age_seconds(self, *, now: Optional[datetime] = None) -> float:
        """How old the *reading* is, measured from when it was observed."""
        moment = now or datetime.now(timezone.utc)
        return max(0.0, (moment - self.source_timestamp).total_seconds())

    def latency_seconds(self) -> float:
        """How long it took to reach us. A property of the pipe, not the data."""
        return max(0.0, (self.ingested_at - self.source_timestamp).total_seconds())

    def expired(self, *, now: Optional[datetime] = None) -> bool:
        if self.valid_to is None:
            return False
        return (now or datetime.now(timezone.utc)) > self.valid_to

    def freshness(
        self,
        *,
        now: Optional[datetime] = None,
        live_within_seconds: float = 120.0,
        stale_after_seconds: float = 3600.0,
    ) -> str:
        """LIVE, CACHED, STALE or EXPIRED, on the reading's own age.

        The thresholds are arguments because "live" means seconds for AIS and
        minutes for a forecast; a single global constant would call one of them
        the wrong thing.
        """
        if not self.source_time_known:
            return "UNKNOWN"
        if self.expired(now=now):
            return "EXPIRED"
        age = self.age_seconds(now=now)
        if age <= live_within_seconds:
            return "LIVE"
        if age <= stale_after_seconds:
            return "CACHED"
        return "STALE"

    def to_dict(self, *, now: Optional[datetime] = None) -> Dict[str, Any]:
        return {
            "providerId": self.provider_id,
            "capability": self.capability,
            "sourceTimestamp": self.source_timestamp.isoformat(),
            "ingestedAt": self.ingested_at.isoformat(),
            "validFrom": None if self.valid_from is None else self.valid_from.isoformat(),
            "validTo": None if self.valid_to is None else self.valid_to.isoformat(),
            "validityAssumed": self.validity_assumed,
            "sourceTimeKnown": self.source_time_known,
            "ageSeconds": (
                None if not self.source_time_known
                else round(self.age_seconds(now=now), 1)
            ),
            "latencySeconds": round(self.latency_seconds(), 1),
            "freshness": self.freshness(now=now),
            "coverage": self.coverage,
            "licenceMode": self.licence_mode,
            "quality": self.quality.to_dict(),
            "provenance": self.provenance,
        }


# --------------------------------------------------------------------------
# quality checks
# --------------------------------------------------------------------------


def assess(
    observation: Observation,
    *,
    now: Optional[datetime] = None,
    stale_after_seconds: float = 3600.0,
) -> QualityVerdict:
    """Judge one observation on arrival.

    Deliberately conservative about what it rejects. A reading from the future,
    or one with no payload, cannot be reasoned about at all. Everything else --
    old, briefly expired, thin provenance -- is degraded rather than dropped,
    because a source that has started producing poor readings is something an
    operator needs to see happening rather than have hidden from them.
    """
    moment = now or datetime.now(timezone.utc)
    reasons: List[str] = []
    level = OK

    skew = (observation.source_timestamp - moment).total_seconds() / 60.0
    if skew > MAX_CLOCK_SKEW_MINUTES:
        return QualityVerdict(
            REJECTED,
            (
                f"observed {skew:.0f} minutes in the future, which is a clock "
                "problem rather than a forecast",
            ),
        )

    if observation.value is None:
        return QualityVerdict(REJECTED, ("the provider returned no payload",))

    if isinstance(observation.value, (list, tuple, dict)) and len(observation.value) == 0:
        reasons.append("the provider returned an empty payload")
        level = DEGRADED

    if observation.expired(now=moment):
        reasons.append("the reading is past the validity its provider stated")
        level = DEGRADED

    if not observation.source_time_known:
        reasons.append(
            "the payload carried no timestamp, so its age cannot be established "
            "and its freshness is unknown rather than current"
        )
        level = DEGRADED

    age = observation.age_seconds(now=moment)
    if observation.source_time_known and age > stale_after_seconds:
        reasons.append(
            f"the reading is {age / 3600:.1f} h old, beyond this capability's "
            "staleness threshold"
        )
        level = DEGRADED

    if observation.validity_assumed:
        reasons.append(
            "validity is this deployment's assumption; the provider stated none"
        )
        level = DEGRADED if level == OK else level

    return QualityVerdict(level, tuple(reasons))


def observe(
    *,
    provider_id: str,
    capability: str,
    value: Any,
    source_timestamp: datetime,
    valid_for_hours: Optional[float] = None,
    coverage: str = "unspecified",
    licence_mode: str = "RESEARCH",
    now: Optional[datetime] = None,
    stale_after_seconds: float = 3600.0,
    source_time_known: bool = True,
    **provenance: Any,
) -> Observation:
    """Build an observation and judge it in one step.

    The only sanctioned constructor, so an observation cannot enter the system
    without having been assessed. A caller that built one by hand and forgot to
    check it would produce a reading that claims OK quality it never earned.
    """
    moment = now or datetime.now(timezone.utc)
    valid_to = (
        None if valid_for_hours is None
        else source_timestamp + timedelta(hours=valid_for_hours)
    )
    draft = Observation(
        provider_id=provider_id,
        capability=capability,
        value=value,
        source_timestamp=source_timestamp,
        ingested_at=moment,
        valid_from=source_timestamp,
        valid_to=valid_to,
        validity_assumed=valid_for_hours is not None,
        source_time_known=source_time_known,
        coverage=coverage,
        licence_mode=licence_mode,
        provenance=dict(provenance),
    )
    verdict = assess(draft, now=moment, stale_after_seconds=stale_after_seconds)
    return Observation(
        provider_id=draft.provider_id,
        capability=draft.capability,
        value=draft.value,
        source_timestamp=draft.source_timestamp,
        ingested_at=draft.ingested_at,
        valid_from=draft.valid_from,
        valid_to=draft.valid_to,
        validity_assumed=draft.validity_assumed,
        source_time_known=draft.source_time_known,
        coverage=draft.coverage,
        licence_mode=draft.licence_mode,
        quality=verdict,
        provenance=draft.provenance,
    )


__all__ = [
    "DEGRADED",
    "GOOD",
    "MAX_CLOCK_SKEW_MINUTES",
    "OK",
    "Observation",
    "ObservationError",
    "QUALITY_LEVELS",
    "QualityVerdict",
    "REJECTED",
    "assess",
    "observe",
]
