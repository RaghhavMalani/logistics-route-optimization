"""Contextual reliability: which contributor to trust, where.

The existing forecast stack already learns global and per-horizon ensemble
weights during walk-forward fitting (see :mod:`src.forecasting.ensemble`). This
module does something different and complementary: it learns, from *resolved
ledger rows only*, how much a named contributor -- a weather expert, a news
expert, an event source -- deserves to be trusted in a specific context, and
exposes that as a multiplier the ensemble and Global Eye can apply.

Three rules make this defensible rather than a fudge factor:

**Leakage.** A weight may only be fitted on rows whose observation was available
before the claim it will be applied to. :func:`fit_reliability` takes an
explicit ``as_of`` and refuses rows resolved after it. The test suite asserts
this, because a reliability table fitted on the future would make every
downstream benchmark meaningless while looking like an improvement.

**Shrinkage.** A contributor with nine resolved rows in a context does not get a
0.4 weight because those nine went badly. Weights shrink toward 1.0 with a prior
strength of :data:`PRIOR_STRENGTH` observations, so a context earns influence
over the weight only as evidence accumulates.

**Bounded movement.** Weights are clamped to :data:`MIN_WEIGHT`..
:data:`MAX_WEIGHT` and move at most :data:`MAX_STEP` per update. A single bad
monsoon week cannot switch an expert off, and recovery is equally gradual.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from src.portwatch_os.ledger.schema import (
    BINARY,
    CONTINUOUS,
    PredictionRecord,
    RESOLVED,
    ReliabilityRecord,
    utc_now,
)
from src.portwatch_os.learning.scoring import brier_score

#: Observations before a fitted weight outweighs the neutral prior of 1.0.
PRIOR_STRENGTH = 24.0

MIN_WEIGHT = 0.35
MAX_WEIGHT = 1.60

#: Largest single-update movement. Reliability is a slow variable by design.
MAX_STEP = 0.12

#: Below this many resolved rows a context is reported but never applied.
MIN_SAMPLES_TO_APPLY = 8

#: The context slices reliability is learned over. Ordered coarse to fine; the
#: lookup in :func:`weight_for` walks them from most specific to least so a
#: well-evidenced narrow context wins over a broad one.
CONTEXT_DIMENSIONS: Tuple[Tuple[str, ...], ...] = (
    ("port_code", "horizon_hours", "weather_regime"),
    ("port_code", "horizon_hours"),
    ("region", "horizon_hours"),
    ("horizon_hours",),
    ("port_code",),
)

GLOBAL_CONTEXT_KEY = "global"


class LeakageError(ValueError):
    """Raised when a fit would use an observation the claim could not have had."""


@dataclass
class ContributorStats:
    """Accumulated evidence for one contributor in one context."""

    contributor: str
    context_key: str
    dimensions: Tuple[str, ...]
    count: int = 0
    absolute_error_sum: float = 0.0
    signed_error_sum: float = 0.0
    #: Squared error of the contributor's own signal, where it made a claim.
    squared_error_sum: float = 0.0
    #: Squared error of the naive reference over the same rows, so skill can be
    #: computed on exactly the rows the contributor was present for.
    reference_squared_sum: float = 0.0
    brier_sum: float = 0.0
    binary_count: int = 0
    first_observed: Optional[str] = None
    last_observed: Optional[str] = None

    @property
    def mean_absolute_error(self) -> Optional[float]:
        return self.absolute_error_sum / self.count if self.count else None

    @property
    def bias(self) -> Optional[float]:
        return self.signed_error_sum / self.count if self.count else None

    @property
    def mean_brier(self) -> Optional[float]:
        return self.brier_sum / self.binary_count if self.binary_count else None

    def skill(self) -> Optional[float]:
        """Skill of this contributor's rows against the reference on those rows."""
        if not self.count or self.reference_squared_sum <= 0:
            return None
        return 1.0 - (self.squared_error_sum / self.reference_squared_sum)


def _parse(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def context_keys(record: PredictionRecord) -> List[Tuple[str, Tuple[str, ...]]]:
    """Every context bucket a resolved row contributes evidence to."""
    out: List[Tuple[str, Tuple[str, ...]]] = [(GLOBAL_CONTEXT_KEY, ())]
    for dimensions in CONTEXT_DIMENSIONS:
        if all(getattr(record.context, dim, None) is None for dim in dimensions):
            continue
        out.append((record.context.bucket_key(*dimensions), dimensions))
    return out


def accumulate(
    records: Iterable[PredictionRecord],
    *,
    as_of: Optional[str] = None,
    reference: str = "persistence",
) -> Dict[Tuple[str, str], ContributorStats]:
    """Gather per-contributor evidence from resolved rows.

    ``as_of`` is the leakage barrier. Any row observed at or after it is refused
    outright rather than skipped quietly, because a silent skip is how a leakage
    bug survives a code review.
    """
    barrier = _parse(as_of)
    stats: Dict[Tuple[str, str], ContributorStats] = {}

    for record in records:
        if record.status != RESOLVED or record.observed_value is None:
            continue
        observed_at = _parse(record.observed_at)
        if barrier is not None and observed_at is not None and observed_at >= barrier:
            raise LeakageError(
                f"prediction {record.prediction_id} was observed at {record.observed_at}, "
                f"at or after the as_of barrier {as_of}; fitting on it would leak"
            )

        contributors = record.features or {}
        if not contributors:
            continue

        # The reference the contributor is scored against. `persistence` is the
        # value the world already had -- stored in the features under a reserved
        # key by the recording side -- and falls back to the ensemble's own
        # point estimate where no persistence value was captured.
        reference_value = contributors.get(f"__{reference}__")
        if reference_value is None:
            reference_value = record.predicted_value
        ref_error = (
            (record.observed_value - reference_value) ** 2
            if reference_value is not None
            else None
        )

        for key, dimensions in context_keys(record):
            for contributor, signal in contributors.items():
                if contributor.startswith("__"):
                    continue
                bucket = stats.setdefault(
                    (contributor, key),
                    ContributorStats(contributor, key, dimensions),
                )
                if record.kind == BINARY:
                    bucket.binary_count += 1
                    bucket.brier_sum += brier_score(signal, bool(record.observed_value))
                    bucket.count += 1
                    error = float(record.observed_value) - float(signal)
                else:
                    error = float(record.observed_value) - float(signal)
                    bucket.count += 1
                bucket.absolute_error_sum += abs(error)
                bucket.signed_error_sum += error
                bucket.squared_error_sum += error * error
                if ref_error is not None:
                    bucket.reference_squared_sum += ref_error
                if record.observed_at:
                    if bucket.first_observed is None or record.observed_at < bucket.first_observed:
                        bucket.first_observed = record.observed_at
                    if bucket.last_observed is None or record.observed_at > bucket.last_observed:
                        bucket.last_observed = record.observed_at

    return stats


def _raw_weight(stat: ContributorStats, baseline_mae: Optional[float]) -> float:
    """Unshrunk weight from this contributor's error relative to its peers.

    The comparison is against the mean absolute error of *all* contributors in
    the same context, so a context where everything is hard does not penalise
    everyone: what matters is who is worse than the room.
    """
    mae = stat.mean_absolute_error
    if mae is None or baseline_mae is None or baseline_mae <= 0:
        return 1.0
    # Ratio of 1 means average. Halving the error roughly doubles the weight,
    # doubling the error roughly halves it, with the square root damping the
    # response so a single noisy context does not swing it.
    ratio = baseline_mae / max(mae, 1e-9)
    return float(ratio ** 0.5)


def shrink(raw: float, count: int, prior_strength: float = PRIOR_STRENGTH) -> float:
    """Pull a fitted weight toward 1.0 in proportion to how little evidence there is."""
    lam = count / (count + prior_strength)
    return float(1.0 + lam * (raw - 1.0))


def clamp_step(previous: Optional[float], target: float) -> float:
    value = target
    if previous is not None:
        delta = max(-MAX_STEP, min(MAX_STEP, target - previous))
        value = previous + delta
    return float(min(MAX_WEIGHT, max(MIN_WEIGHT, value)))


def fit_reliability(
    records: Sequence[PredictionRecord],
    *,
    as_of: Optional[str] = None,
    previous: Optional[Sequence[ReliabilityRecord]] = None,
    reference: str = "persistence",
) -> List[ReliabilityRecord]:
    """Learn a reliability weight per contributor per context.

    Returns records ready for :meth:`LedgerStore.upsert_reliability`. Contexts
    with fewer than :data:`MIN_SAMPLES_TO_APPLY` rows are still returned -- the
    dashboard should show that the system is watching them -- but their weight is
    held at the shrunk value, which with so little evidence is close to 1.0.
    """
    stats = accumulate(records, as_of=as_of, reference=reference)
    prior = {(r.contributor, r.context_key): r for r in (previous or [])}

    # Peer baseline per context: the mean of contributor MAEs in that context.
    by_context: Dict[str, List[ContributorStats]] = defaultdict(list)
    for stat in stats.values():
        by_context[stat.context_key].append(stat)

    out: List[ReliabilityRecord] = []
    now = utc_now()
    for context_key, group in by_context.items():
        maes = [s.mean_absolute_error for s in group if s.mean_absolute_error is not None]
        baseline = (sum(maes) / len(maes)) if maes else None
        for stat in group:
            raw = _raw_weight(stat, baseline)
            shrunk = shrink(raw, stat.count)
            existing = prior.get((stat.contributor, context_key))
            weight = clamp_step(existing.weight if existing else None, shrunk)
            out.append(
                ReliabilityRecord(
                    contributor=stat.contributor,
                    context_key=context_key,
                    dimensions=list(stat.dimensions),
                    weight=round(weight, 4),
                    previous_weight=existing.weight if existing else None,
                    sample_count=stat.count,
                    mean_absolute_error=(
                        None if stat.mean_absolute_error is None
                        else round(stat.mean_absolute_error, 4)
                    ),
                    bias=None if stat.bias is None else round(stat.bias, 4),
                    calibration_error=(
                        None if stat.mean_brier is None else round(stat.mean_brier, 4)
                    ),
                    updated_at=now,
                    fitted_from=stat.first_observed,
                    fitted_to=stat.last_observed,
                    notes=(
                        f"fitted on {stat.count} resolved rows"
                        + (f"; barrier {as_of}" if as_of else "")
                        + ("" if stat.count >= MIN_SAMPLES_TO_APPLY
                           else "; below the application threshold, reported only")
                    ),
                )
            )
    out.sort(key=lambda r: (r.contributor, r.context_key))
    return out


@dataclass
class ReliabilityTable:
    """A queryable view over reliability rows, with the specificity rule applied."""

    rows: Dict[Tuple[str, str], ReliabilityRecord] = field(default_factory=dict)

    @classmethod
    def from_records(cls, records: Iterable[ReliabilityRecord]) -> "ReliabilityTable":
        return cls({(r.contributor, r.context_key): r for r in records})

    def weight_for(
        self,
        contributor: str,
        context: Any,
        *,
        min_samples: int = MIN_SAMPLES_TO_APPLY,
    ) -> Tuple[float, Optional[ReliabilityRecord]]:
        """The applicable weight, most specific sufficiently-evidenced context first.

        Returns the weight *and* the record it came from, so a caller can show
        the operator which slice justified the adjustment rather than an
        unexplained multiplier.
        """
        for dimensions in CONTEXT_DIMENSIONS:
            if not hasattr(context, "bucket_key"):
                break
            key = context.bucket_key(*dimensions)
            record = self.rows.get((contributor, key))
            if record and record.sample_count >= min_samples:
                return record.weight, record
        record = self.rows.get((contributor, GLOBAL_CONTEXT_KEY))
        if record and record.sample_count >= min_samples:
            return record.weight, record
        return 1.0, None

    def apply(
        self,
        signals: Dict[str, float],
        context: Any,
        *,
        min_samples: int = MIN_SAMPLES_TO_APPLY,
    ) -> Tuple[Dict[str, float], Dict[str, float]]:
        """Reweight a set of contributor signals; returns (weights, normalised).

        The normalised weights sum to 1 so the caller can blend directly. Where
        no contributor has enough evidence the result is a uniform blend, which
        is exactly the behaviour before any learning happened.
        """
        weights = {
            name: self.weight_for(name, context, min_samples=min_samples)[0]
            for name in signals
        }
        total = sum(weights.values())
        if total <= 0:
            uniform = 1.0 / max(1, len(signals))
            return weights, {name: uniform for name in signals}
        return weights, {name: value / total for name, value in weights.items()}


def blend(signals: Dict[str, float], normalised: Dict[str, float]) -> Optional[float]:
    """Weighted blend of contributor signals. ``None`` when there is nothing to blend."""
    if not signals:
        return None
    return float(sum(signals[name] * normalised.get(name, 0.0) for name in signals))


__all__ = [
    "CONTEXT_DIMENSIONS",
    "GLOBAL_CONTEXT_KEY",
    "MAX_STEP",
    "MAX_WEIGHT",
    "MIN_SAMPLES_TO_APPLY",
    "MIN_WEIGHT",
    "PRIOR_STRENGTH",
    "ContributorStats",
    "LeakageError",
    "ReliabilityTable",
    "accumulate",
    "blend",
    "clamp_step",
    "context_keys",
    "fit_reliability",
    "shrink",
]
