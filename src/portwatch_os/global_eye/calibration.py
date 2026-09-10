"""Turning Global Eye severity into a calibrated probability.

The raw signal an event carries is ``severity × confidence``: a heuristic score
from a word list, multiplied by how many outlets corroborated it. That number is
not a probability and must never be shown as one. This module is what earns the
right to call something 72%.

The method is deliberately the simplest thing that is defensible:

1.  Bucket resolved event outcomes by category and by raw score.
2.  Within each bucket, the observed frequency *is* the calibrated probability
    -- that is the definition of calibration.
3.  Shrink that frequency toward the category base rate, and the base rate
    toward the global base rate, in proportion to how little evidence each has
    (Laplace-style smoothing with an explicit prior strength).
4.  Fit a monotone map so a higher raw score never yields a lower probability.

Where there is not enough evidence, :meth:`Calibrator.probability` returns
``None`` and the caller shows severity and confidence instead. A product that
prints "72%" from four historical observations is lying with a decimal point.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from src.portwatch_os.ledger.schema import EventOutcomeRecord, RESOLVED
from src.portwatch_os.learning.scoring import binary_report

#: Resolved outcomes required in a category before it gets its own curve.
MIN_CATEGORY_SAMPLES = 12

#: Resolved outcomes required overall before any probability is emitted at all.
MIN_GLOBAL_SAMPLES = 20

#: Pseudo-observations of the parent prior mixed into each bucket.
PRIOR_STRENGTH = 6.0

#: Raw-score bucket edges. Four buckets: a finer grid over a few dozen outcomes
#: would fit noise.
SCORE_EDGES: Tuple[float, ...] = (0.0, 0.25, 0.45, 0.65, 1.0001)

SCORE_LABELS: Tuple[str, ...] = ("0.00-0.25", "0.25-0.45", "0.45-0.65", "0.65-1.00")


def raw_score(severity: float, confidence: float) -> float:
    """The uncalibrated signal. Bounded to [0, 1] by construction."""
    return float(max(0.0, min(1.0, severity * confidence)))


def score_bucket(score: float) -> int:
    for index in range(len(SCORE_EDGES) - 1):
        if SCORE_EDGES[index] <= score < SCORE_EDGES[index + 1]:
            return index
    return len(SCORE_LABELS) - 1


@dataclass
class BucketFit:
    """The calibrated probability for one (category, score bucket) pair."""

    category: str
    bucket: int
    label: str
    count: int
    occurrences: int
    #: Raw observed frequency before smoothing. ``None`` when the bucket is empty.
    observed_rate: Optional[float]
    #: The value actually used, after shrinkage toward the parent prior.
    probability: float
    #: Where the shrinkage pulled toward.
    prior: float
    mean_raw_score: Optional[float] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "category": self.category,
            "bucket": self.bucket,
            "label": self.label,
            "count": self.count,
            "occurrences": self.occurrences,
            "observedRate": None if self.observed_rate is None else round(self.observed_rate, 4),
            "probability": round(self.probability, 4),
            "prior": round(self.prior, 4),
            "meanRawScore": (
                None if self.mean_raw_score is None else round(self.mean_raw_score, 4)
            ),
        }


@dataclass
class Calibrator:
    """A fitted map from (category, raw score) to probability."""

    global_base_rate: Optional[float]
    global_count: int
    category_base: Dict[str, Tuple[float, int]] = field(default_factory=dict)
    buckets: Dict[Tuple[str, int], BucketFit] = field(default_factory=dict)
    fitted_at: Optional[str] = None
    #: Scores computed on the same rows the fit used. Reported for transparency;
    #: an out-of-sample score comes from the outcome agent's own pass.
    in_sample: Dict[str, Any] = field(default_factory=dict)

    @property
    def available(self) -> bool:
        return self.global_count >= MIN_GLOBAL_SAMPLES and self.global_base_rate is not None

    def probability(
        self,
        category: str,
        severity: float,
        confidence: float,
    ) -> Tuple[Optional[float], str]:
        """Calibrated probability and the sentence explaining where it came from.

        Returns ``(None, reason)`` when there is not enough resolved history.
        The reason is shown in the UI in place of a number, so an operator can
        see that the system is withholding rather than that nothing happened.
        """
        if not self.available:
            return None, (
                f"Only {self.global_count} event claims have been resolved; "
                f"{MIN_GLOBAL_SAMPLES} are required before Global Eye states a "
                "calibrated probability. Severity and confidence are shown instead."
            )

        score = raw_score(severity, confidence)
        bucket = score_bucket(score)
        fit = self.buckets.get((category, bucket))
        if fit is not None and fit.count > 0:
            return _clamp(fit.probability), (
                f"Calibrated on {fit.count} resolved {category} claims in the "
                f"{fit.label} score band; {fit.occurrences} of them occurred."
            )

        base = self.category_base.get(category)
        if base and base[1] >= MIN_CATEGORY_SAMPLES:
            rate, count = base
            # No bucket-level evidence, so lean on the category rate and let the
            # raw score tilt it within a bounded range rather than ignoring it.
            tilt = (score - 0.45) * 0.5
            return _clamp(rate + tilt), (
                f"No resolved claims in this score band; using the {category} base "
                f"rate of {rate:.2f} over {count} outcomes, adjusted for the raw score."
            )

        assert self.global_base_rate is not None
        tilt = (score - 0.45) * 0.4
        return _clamp(self.global_base_rate + tilt), (
            f"No category-level history for {category}; using the overall base rate "
            f"of {self.global_base_rate:.2f} over {self.global_count} outcomes, "
            "adjusted for the raw score."
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "available": self.available,
            "fittedAt": self.fitted_at,
            "globalBaseRate": (
                None if self.global_base_rate is None else round(self.global_base_rate, 4)
            ),
            "globalCount": self.global_count,
            "minGlobalSamples": MIN_GLOBAL_SAMPLES,
            "minCategorySamples": MIN_CATEGORY_SAMPLES,
            "categoryBase": {
                k: {"rate": round(v[0], 4), "count": v[1]}
                for k, v in sorted(self.category_base.items())
            },
            "buckets": [b.to_dict() for b in self.buckets.values()],
            "inSample": self.in_sample,
        }


def _clamp(value: float) -> float:
    # Never 0 or 1: a categorical claim about the future is not certain, and a
    # zero would make the log loss on a surprise infinite.
    return float(max(0.02, min(0.97, value)))


def fit_calibrator(
    outcomes: Sequence[EventOutcomeRecord],
    *,
    fitted_at: Optional[str] = None,
) -> Calibrator:
    """Fit the calibration map from resolved event outcomes."""
    resolved = [
        r for r in outcomes
        if r.status == RESOLVED and r.occurred is not None
    ]
    if not resolved:
        return Calibrator(global_base_rate=None, global_count=0, fitted_at=fitted_at)

    global_hits = sum(1 for r in resolved if r.occurred)
    global_rate = global_hits / len(resolved)

    by_category: Dict[str, List[EventOutcomeRecord]] = {}
    for row in resolved:
        by_category.setdefault(row.category, []).append(row)

    category_base: Dict[str, Tuple[float, int]] = {}
    for category, rows in by_category.items():
        hits = sum(1 for r in rows if r.occurred)
        # Smooth the category rate toward the global rate so a category with
        # three outcomes does not claim a 100% base rate.
        smoothed = (hits + PRIOR_STRENGTH * global_rate) / (len(rows) + PRIOR_STRENGTH)
        category_base[category] = (smoothed, len(rows))

    buckets: Dict[Tuple[str, int], BucketFit] = {}
    for category, rows in by_category.items():
        prior_rate = category_base[category][0]
        grouped: Dict[int, List[EventOutcomeRecord]] = {}
        for row in rows:
            # The raw score is reconstructed from what was stored at claim time.
            # ``predicted_probability`` is that score when the claim was made
            # before calibration existed, which is exactly the bootstrap case.
            score = raw_score(row.predicted_probability, row.confidence or 1.0)
            grouped.setdefault(score_bucket(score), []).append(row)

        for bucket, subset in grouped.items():
            hits = sum(1 for r in subset if r.occurred)
            observed = hits / len(subset)
            probability = (hits + PRIOR_STRENGTH * prior_rate) / (len(subset) + PRIOR_STRENGTH)
            scores = [
                raw_score(r.predicted_probability, r.confidence or 1.0) for r in subset
            ]
            buckets[(category, bucket)] = BucketFit(
                category=category,
                bucket=bucket,
                label=SCORE_LABELS[bucket],
                count=len(subset),
                occurrences=hits,
                observed_rate=observed,
                probability=probability,
                prior=prior_rate,
                mean_raw_score=sum(scores) / len(scores),
            )

    _enforce_monotone(buckets)

    calibrator = Calibrator(
        global_base_rate=global_rate,
        global_count=len(resolved),
        category_base=category_base,
        buckets=buckets,
        fitted_at=fitted_at,
    )

    pairs = [(r.predicted_probability, bool(r.occurred)) for r in resolved]
    leads = [r.lead_time_hours for r in resolved]
    before = binary_report(pairs, lead_times=leads)
    after_pairs = []
    for row in resolved:
        probability, _ = calibrator.probability(
            row.category, row.predicted_probability, row.confidence or 1.0
        )
        after_pairs.append((probability if probability is not None else row.predicted_probability,
                            bool(row.occurred)))
    after = binary_report(after_pairs, lead_times=leads)
    calibrator.in_sample = {
        "note": (
            "Both figures are in-sample: the calibrator was fitted on these rows. "
            "They show the map is doing something, not that it generalises. The "
            "out-of-sample score is produced by the outcome agent on later claims."
        ),
        "before": before.to_dict(),
        "after": after.to_dict(),
    }
    return calibrator


def _enforce_monotone(buckets: Dict[Tuple[str, int], BucketFit]) -> None:
    """A higher raw score must never map to a lower probability.

    Small samples routinely produce a dip in the middle band. Left alone that
    would let a more severe, better corroborated event be shown as less likely
    than a milder one -- which no operator would ever accept, and rightly. The
    fix is a running maximum across the bands within each category, which is the
    simplest projection onto the monotone constraint.
    """
    categories = {category for category, _ in buckets}
    for category in categories:
        running: Optional[float] = None
        for bucket in range(len(SCORE_LABELS)):
            fit = buckets.get((category, bucket))
            if fit is None:
                continue
            if running is not None and fit.probability < running:
                fit.probability = running
            running = fit.probability


def apply_calibration(
    events: Iterable[Any],
    calibrator: Calibrator,
) -> int:
    """Stamp calibrated probabilities onto events in place. Returns how many.

    Events whose category has no usable history keep ``probability = None`` and
    gain a note saying so, which is what the UI renders instead of a percentage.
    """
    stamped = 0
    for event in events:
        probability, reason = calibrator.probability(
            event.category, event.severity, event.confidence
        )
        event.probability = probability
        event.calibration_note = reason
        if probability is not None:
            stamped += 1
    return stamped


def claims_for(
    events: Iterable[Any],
    *,
    issued_at: str,
    resolve_by_hours: Optional[float] = None,
) -> List[EventOutcomeRecord]:
    """Write one falsifiable outcome claim per event, ready for the ledger.

    This is what makes Global Eye scorable at all: the claim is committed with a
    horizon before the world answers it. Without this call the calibration above
    would have nothing to fit on, forever.
    """
    from src.portwatch_os.ledger.store import shift_iso

    out: List[EventOutcomeRecord] = []
    for event in events:
        horizon = resolve_by_hours if resolve_by_hours is not None else event.horizon_hours
        # Before calibration exists the raw score is the stated probability, and
        # the calibration note on the event says exactly that.
        probability = (
            event.probability
            if event.probability is not None
            else raw_score(event.severity, event.confidence)
        )
        out.append(
            EventOutcomeRecord(
                outcome_id=EventOutcomeRecord.make_id(
                    event.event_id, event.claim or "impact", horizon
                ),
                event_id=event.event_id,
                category=event.category,
                region=event.region,
                claim=event.claim or "measurable operational impact",
                horizon_hours=horizon,
                predicted_probability=probability,
                confidence=event.confidence,
                source_count=event.source_count,
                sources=sorted({s.outlet for s in event.sources if s.outlet}),
                issued_at=issued_at,
                resolve_by=shift_iso(issued_at, horizon),
                predicted_impact={},
            )
        )
    return out


__all__ = [
    "MIN_CATEGORY_SAMPLES",
    "MIN_GLOBAL_SAMPLES",
    "PRIOR_STRENGTH",
    "SCORE_EDGES",
    "SCORE_LABELS",
    "BucketFit",
    "Calibrator",
    "apply_calibration",
    "claims_for",
    "fit_calibrator",
    "raw_score",
    "score_bucket",
]
