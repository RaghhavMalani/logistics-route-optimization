"""Proper scoring rules and calibration diagnostics.

Everything here is a pure function over numbers so it can be tested exactly, and
every rule is *proper*: a forecaster minimises it only by reporting its true
belief. That matters more than it sounds. If Global Eye were scored on accuracy
alone, the way to win would be to claim 0% or 100% on everything; under Brier
score and log loss the way to win is to be honest about uncertainty, which is
precisely the behaviour the product needs.

Nothing in this module reads the ledger or the clock. The pass that does that
lives in :mod:`src.portwatch_os.learning.outcome_agent`.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

#: Probabilities are clipped before the logarithm so a confident miss costs a
#: large but finite amount. Without this one wrong 0.0 makes the mean log loss
#: infinite and the whole diagnostic useless.
_EPS = 1e-6


def clip_probability(p: float) -> float:
    return min(1.0 - _EPS, max(_EPS, float(p)))


# --------------------------------------------------------------------------
# binary claims
# --------------------------------------------------------------------------


def brier_score(probability: float, occurred: bool) -> float:
    """Squared error of a probabilistic claim. Lower is better; 0.25 is a coin."""
    return float((float(probability) - (1.0 if occurred else 0.0)) ** 2)


def log_loss(probability: float, occurred: bool) -> float:
    p = clip_probability(probability)
    return float(-math.log(p) if occurred else -math.log(1.0 - p))


@dataclass
class ConfusionCounts:
    true_positive: int = 0
    false_positive: int = 0
    true_negative: int = 0
    false_negative: int = 0

    @property
    def precision(self) -> Optional[float]:
        denom = self.true_positive + self.false_positive
        return self.true_positive / denom if denom else None

    @property
    def recall(self) -> Optional[float]:
        denom = self.true_positive + self.false_negative
        return self.true_positive / denom if denom else None

    @property
    def false_positive_rate(self) -> Optional[float]:
        denom = self.false_positive + self.true_negative
        return self.false_positive / denom if denom else None

    @property
    def f1(self) -> Optional[float]:
        p, r = self.precision, self.recall
        if p is None or r is None or (p + r) == 0:
            return None
        return 2 * p * r / (p + r)

    def to_dict(self) -> Dict[str, Optional[float]]:
        return {
            "truePositive": self.true_positive,
            "falsePositive": self.false_positive,
            "trueNegative": self.true_negative,
            "falseNegative": self.false_negative,
            "precision": _round(self.precision),
            "recall": _round(self.recall),
            "falsePositiveRate": _round(self.false_positive_rate),
            "f1": _round(self.f1),
        }


def confusion(
    pairs: Iterable[Tuple[float, bool]],
    threshold: float = 0.5,
) -> ConfusionCounts:
    """Confusion counts at a decision threshold.

    The threshold is explicit because it is an operational choice, not a
    statistical one: a port authority that acts on any claim above 0.3 has a
    different false-alarm budget from one that waits for 0.7.
    """
    counts = ConfusionCounts()
    for probability, occurred in pairs:
        predicted = float(probability) >= threshold
        if predicted and occurred:
            counts.true_positive += 1
        elif predicted and not occurred:
            counts.false_positive += 1
        elif not predicted and occurred:
            counts.false_negative += 1
        else:
            counts.true_negative += 1
    return counts


# --------------------------------------------------------------------------
# calibration
# --------------------------------------------------------------------------

#: Ten equal-width bins over [0, 1]. Equal width rather than equal count so a
#: bin's label ("claims we called 70%") means the same thing across runs.
DEFAULT_BINS: Tuple[float, ...] = tuple(i / 10 for i in range(11))


@dataclass
class CalibrationBin:
    lower: float
    upper: float
    count: int = 0
    mean_predicted: Optional[float] = None
    observed_rate: Optional[float] = None

    @property
    def gap(self) -> Optional[float]:
        if self.mean_predicted is None or self.observed_rate is None:
            return None
        return self.observed_rate - self.mean_predicted

    def to_dict(self) -> Dict[str, Optional[float]]:
        return {
            "lower": self.lower,
            "upper": self.upper,
            "count": self.count,
            "meanPredicted": _round(self.mean_predicted),
            "observedRate": _round(self.observed_rate),
            "gap": _round(self.gap),
        }


@dataclass
class CalibrationReport:
    bins: List[CalibrationBin]
    #: Expected calibration error: the count-weighted mean absolute gap.
    expected_calibration_error: Optional[float]
    #: The worst single bin, which is what actually burns an operator.
    max_calibration_error: Optional[float]
    sample_count: int
    #: Mean predicted probability minus observed base rate. Positive means the
    #: system cries wolf.
    over_forecast: Optional[float] = None

    def to_dict(self) -> Dict[str, object]:
        return {
            "bins": [b.to_dict() for b in self.bins],
            "expectedCalibrationError": _round(self.expected_calibration_error),
            "maxCalibrationError": _round(self.max_calibration_error),
            "overForecast": _round(self.over_forecast),
            "sampleCount": self.sample_count,
        }


def calibration(
    pairs: Sequence[Tuple[float, bool]],
    bins: Sequence[float] = DEFAULT_BINS,
) -> CalibrationReport:
    """How well stated probabilities match observed frequencies."""
    edges = list(bins)
    buckets: List[CalibrationBin] = [
        CalibrationBin(lower=edges[i], upper=edges[i + 1]) for i in range(len(edges) - 1)
    ]
    sums: List[float] = [0.0] * len(buckets)
    hits: List[int] = [0] * len(buckets)

    for probability, occurred in pairs:
        p = min(1.0, max(0.0, float(probability)))
        index = min(len(buckets) - 1, max(0, int(p * len(buckets))))
        buckets[index].count += 1
        sums[index] += p
        hits[index] += 1 if occurred else 0

    total = sum(b.count for b in buckets)
    weighted_gap = 0.0
    max_gap: Optional[float] = None
    for i, bucket in enumerate(buckets):
        if not bucket.count:
            continue
        bucket.mean_predicted = sums[i] / bucket.count
        bucket.observed_rate = hits[i] / bucket.count
        gap = abs(bucket.observed_rate - bucket.mean_predicted)
        weighted_gap += gap * bucket.count
        max_gap = gap if max_gap is None else max(max_gap, gap)

    over = None
    if total:
        mean_predicted = sum(sums) / total
        base_rate = sum(hits) / total
        over = mean_predicted - base_rate

    return CalibrationReport(
        bins=buckets,
        expected_calibration_error=(weighted_gap / total) if total else None,
        max_calibration_error=max_gap,
        sample_count=total,
        over_forecast=over,
    )


# --------------------------------------------------------------------------
# continuous claims
# --------------------------------------------------------------------------


@dataclass
class ErrorReport:
    count: int
    mean_absolute_error: Optional[float] = None
    root_mean_square_error: Optional[float] = None
    #: Signed mean error. This is the one reliability actually corrects for: a
    #: model that is 3 units high every time is fixable, one that is 3 units off
    #: in random directions is not.
    bias: Optional[float] = None
    median_absolute_error: Optional[float] = None
    #: Fraction of observations that fell inside the stated interval.
    interval_coverage: Optional[float] = None
    nominal_coverage: Optional[float] = None

    @property
    def coverage_error(self) -> Optional[float]:
        if self.interval_coverage is None or self.nominal_coverage is None:
            return None
        return self.interval_coverage - self.nominal_coverage

    def to_dict(self) -> Dict[str, Optional[float]]:
        return {
            "count": self.count,
            "meanAbsoluteError": _round(self.mean_absolute_error),
            "rootMeanSquareError": _round(self.root_mean_square_error),
            "bias": _round(self.bias),
            "medianAbsoluteError": _round(self.median_absolute_error),
            "intervalCoverage": _round(self.interval_coverage),
            "nominalCoverage": _round(self.nominal_coverage),
            "coverageError": _round(self.coverage_error),
        }


@dataclass
class Residual:
    predicted: float
    observed: float
    low: Optional[float] = None
    high: Optional[float] = None
    nominal: Optional[float] = None

    @property
    def error(self) -> float:
        return self.observed - self.predicted

    @property
    def within(self) -> Optional[bool]:
        if self.low is None or self.high is None:
            return None
        return self.low <= self.observed <= self.high


def error_report(residuals: Sequence[Residual]) -> ErrorReport:
    if not residuals:
        return ErrorReport(count=0)
    errors = [r.error for r in residuals]
    absolute = sorted(abs(e) for e in errors)
    inside = [r.within for r in residuals if r.within is not None]
    nominals = [r.nominal for r in residuals if r.nominal is not None]
    mid = len(absolute) // 2
    median = (
        absolute[mid]
        if len(absolute) % 2
        else (absolute[mid - 1] + absolute[mid]) / 2
    )
    return ErrorReport(
        count=len(residuals),
        mean_absolute_error=sum(absolute) / len(absolute),
        root_mean_square_error=math.sqrt(sum(e * e for e in errors) / len(errors)),
        bias=sum(errors) / len(errors),
        median_absolute_error=median,
        interval_coverage=(sum(1 for v in inside if v) / len(inside)) if inside else None,
        nominal_coverage=(sum(nominals) / len(nominals)) if nominals else None,
    )


def pinball_loss(predicted: float, observed: float, quantile: float) -> float:
    """Quantile loss. Proper for the quantile it names."""
    delta = observed - predicted
    return float(max(quantile * delta, (quantile - 1) * delta))


# --------------------------------------------------------------------------
# skill
# --------------------------------------------------------------------------


def skill_score(model_loss: float, reference_loss: float) -> Optional[float]:
    """Fractional improvement over a reference. 1 is perfect, 0 is no better.

    Negative means the model is worse than the reference, which is a result
    worth reporting rather than hiding: an ensemble that loses to persistence in
    a regime should have its weight cut there.
    """
    if reference_loss is None or reference_loss <= 0:
        return None
    return float(1.0 - (model_loss / reference_loss))


@dataclass
class BinaryScoreReport:
    count: int
    brier: Optional[float] = None
    log_loss: Optional[float] = None
    base_rate: Optional[float] = None
    #: Brier score of always predicting the base rate. The reference any
    #: probabilistic claim has to beat before it is worth anything.
    reference_brier: Optional[float] = None
    brier_skill: Optional[float] = None
    calibration: Optional[CalibrationReport] = None
    confusion: Optional[ConfusionCounts] = None
    mean_lead_time_hours: Optional[float] = None
    false_alarm_rate: Optional[float] = None

    def to_dict(self) -> Dict[str, object]:
        return {
            "count": self.count,
            "brier": _round(self.brier),
            "logLoss": _round(self.log_loss),
            "baseRate": _round(self.base_rate),
            "referenceBrier": _round(self.reference_brier),
            "brierSkill": _round(self.brier_skill),
            "meanLeadTimeHours": _round(self.mean_lead_time_hours),
            "falseAlarmRate": _round(self.false_alarm_rate),
            "calibration": self.calibration.to_dict() if self.calibration else None,
            "confusion": self.confusion.to_dict() if self.confusion else None,
        }


def binary_report(
    pairs: Sequence[Tuple[float, bool]],
    *,
    threshold: float = 0.5,
    lead_times: Optional[Sequence[Optional[float]]] = None,
) -> BinaryScoreReport:
    if not pairs:
        return BinaryScoreReport(count=0)
    briers = [brier_score(p, o) for p, o in pairs]
    losses = [log_loss(p, o) for p, o in pairs]
    base_rate = sum(1 for _, o in pairs if o) / len(pairs)
    reference = base_rate * (1 - base_rate)  # Brier of the climatological forecast
    counts = confusion(pairs, threshold)
    leads = [v for v in (lead_times or []) if v is not None]
    false_alarms = sum(1 for p, o in pairs if p >= threshold and not o)
    raised = sum(1 for p, _ in pairs if p >= threshold)
    mean_brier = sum(briers) / len(briers)
    return BinaryScoreReport(
        count=len(pairs),
        brier=mean_brier,
        log_loss=sum(losses) / len(losses),
        base_rate=base_rate,
        reference_brier=reference,
        brier_skill=skill_score(mean_brier, reference) if reference > 0 else None,
        calibration=calibration(pairs),
        confusion=counts,
        mean_lead_time_hours=(sum(leads) / len(leads)) if leads else None,
        false_alarm_rate=(false_alarms / raised) if raised else None,
    )


def _round(value: Optional[float], digits: int = 4) -> Optional[float]:
    return None if value is None else round(float(value), digits)


__all__ = [
    "BinaryScoreReport",
    "CalibrationBin",
    "CalibrationReport",
    "ConfusionCounts",
    "ErrorReport",
    "Residual",
    "binary_report",
    "brier_score",
    "calibration",
    "clip_probability",
    "confusion",
    "error_report",
    "log_loss",
    "pinball_loss",
    "skill_score",
]
