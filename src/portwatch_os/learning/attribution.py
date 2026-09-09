"""Why was PortWatch wrong?

When a forecast misses, "the model was wrong" is not an answer an operator can
use. This module decomposes a resolved prediction into per-contributor
contributions to the error, using only what the ledger recorded at issue time.

The decomposition is exact, not a narrative. For a weighted blend

    predicted = sum_i w_i * s_i

with observation ``y``, the error is

    y - predicted = sum_i w_i * (y - s_i)

so contributor ``i`` accounts for ``w_i * (y - s_i)`` of the miss. That
identity is what :func:`attribute` computes, and :func:`verify_decomposition`
asserts it closes. There is no room in it for an invented percentage.

Two consequences worth stating plainly, because they are the reason this is
honest rather than decorative:

*   If a prediction's ``features`` and ``contributions`` were not recorded, no
    attribution is produced. :func:`attribute` returns ``available=False`` and
    the UI must say the attribution is unavailable rather than show a plausible
    bar chart.
*   Weights that do not sum to one leave a residual. It is reported as its own
    term rather than smeared across the contributors, because a blend that does
    not close is itself a finding.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence

from src.portwatch_os.ledger.schema import BINARY, PredictionRecord, RESOLVED

#: Feature keys reserved for bookkeeping rather than contributors.
RESERVED_PREFIX = "__"


@dataclass
class ContributionShare:
    """One contributor's share of a single prediction's error."""

    contributor: str
    signal: float
    weight: float
    #: ``weight * (observed - signal)``: this contributor's signed share.
    contribution: float
    #: Share of the total absolute error, in [0, 1], or ``None`` when the
    #: prediction was exactly right and there is no error to apportion.
    share: Optional[float]
    #: Signed error of this contributor's own signal, ignoring its weight.
    own_error: float

    def to_dict(self) -> Dict[str, Any]:
        return {
            "contributor": self.contributor,
            "signal": round(self.signal, 4),
            "weight": round(self.weight, 4),
            "contribution": round(self.contribution, 4),
            "share": None if self.share is None else round(self.share, 4),
            "ownError": round(self.own_error, 4),
        }


@dataclass
class Attribution:
    """The decomposition of one resolved prediction."""

    prediction_id: str
    available: bool
    reason: Optional[str] = None
    predicted: Optional[float] = None
    observed: Optional[float] = None
    error: Optional[float] = None
    shares: List[ContributionShare] = field(default_factory=list)
    #: Error not explained by the contributors, e.g. because the weights did not
    #: sum to one or a post-blend calibration step moved the number.
    residual: Optional[float] = None
    #: The single largest signed contribution, which is what the UI leads with.
    dominant: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "predictionId": self.prediction_id,
            "available": self.available,
            "reason": self.reason,
            "predicted": None if self.predicted is None else round(self.predicted, 4),
            "observed": None if self.observed is None else round(self.observed, 4),
            "error": None if self.error is None else round(self.error, 4),
            "residual": None if self.residual is None else round(self.residual, 4),
            "dominant": self.dominant,
            "shares": [s.to_dict() for s in self.shares],
        }


def attribute(record: PredictionRecord) -> Attribution:
    """Decompose one resolved prediction's error across its contributors."""
    if record.status != RESOLVED or record.observed_value is None:
        return Attribution(
            record.prediction_id, False,
            reason="The prediction has no observation yet, so no error exists to attribute.",
        )

    signals = {
        name: float(value)
        for name, value in (record.features or {}).items()
        if not name.startswith(RESERVED_PREFIX)
    }
    if not signals:
        return Attribution(
            record.prediction_id, False,
            reason=(
                "No per-contributor signals were recorded with this prediction, so its "
                "error cannot be decomposed. Attribution is unavailable, not zero."
            ),
            predicted=record.predicted_value,
            observed=record.observed_value,
            error=(
                None if record.predicted_value is None
                else record.observed_value - record.predicted_value
            ),
        )

    weights = {
        name: float(value)
        for name, value in (record.contributions or {}).items()
        if not name.startswith(RESERVED_PREFIX)
    }
    if not weights:
        # An unweighted record means the blend was uniform. Saying so is better
        # than refusing: a uniform blend is a real, stated weighting.
        uniform = 1.0 / len(signals)
        weights = {name: uniform for name in signals}

    observed = float(record.observed_value)
    predicted = (
        float(record.predicted_value)
        if record.predicted_value is not None
        else sum(weights.get(n, 0.0) * s for n, s in signals.items())
    )
    total_error = observed - predicted

    raw_shares: List[ContributionShare] = []
    for name, signal in signals.items():
        weight = weights.get(name, 0.0)
        own_error = observed - signal
        raw_shares.append(
            ContributionShare(
                contributor=name,
                signal=signal,
                weight=weight,
                contribution=weight * own_error,
                share=None,
                own_error=own_error,
            )
        )

    explained = sum(s.contribution for s in raw_shares)
    residual = total_error - explained

    denominator = sum(abs(s.contribution) for s in raw_shares) + abs(residual)
    for share in raw_shares:
        share.share = (abs(share.contribution) / denominator) if denominator > 0 else None

    raw_shares.sort(key=lambda s: abs(s.contribution), reverse=True)
    dominant = raw_shares[0].contributor if raw_shares and denominator > 0 else None

    return Attribution(
        prediction_id=record.prediction_id,
        available=True,
        predicted=predicted,
        observed=observed,
        error=total_error,
        shares=raw_shares,
        residual=residual,
        dominant=dominant,
    )


def verify_decomposition(attribution: Attribution, tolerance: float = 1e-6) -> bool:
    """True when the shares plus the residual reproduce the error exactly."""
    if not attribution.available or attribution.error is None:
        return False
    total = sum(s.contribution for s in attribution.shares) + (attribution.residual or 0.0)
    return abs(total - attribution.error) <= tolerance


@dataclass
class MissReport:
    """A single notable miss, formatted for the 'why were we wrong' screen."""

    prediction_id: str
    subject: str
    target: str
    valid_at: str
    predicted: Optional[float]
    observed: Optional[float]
    error: Optional[float]
    kind: str
    context: Dict[str, Any]
    attribution: Attribution
    #: Reliability weights that changed as a consequence of this class of miss.
    reliability_changes: List[Dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "predictionId": self.prediction_id,
            "subject": self.subject,
            "target": self.target,
            "validAt": self.valid_at,
            "kind": self.kind,
            "predicted": None if self.predicted is None else round(self.predicted, 3),
            "observed": None if self.observed is None else round(self.observed, 3),
            "error": None if self.error is None else round(self.error, 3),
            "context": self.context,
            "attribution": self.attribution.to_dict(),
            "reliabilityChanges": self.reliability_changes,
        }


def rank_misses(
    records: Sequence[PredictionRecord],
    *,
    limit: int = 10,
    reliability_changes: Optional[Dict[str, List[Dict[str, Any]]]] = None,
) -> List[MissReport]:
    """The largest resolved errors, worst first, each with its decomposition.

    Binary claims are ranked by Brier score rather than by raw error, because a
    0.9 claim that failed and a 0.55 claim that failed are not equally wrong.
    """
    scored: List[tuple[float, PredictionRecord]] = []
    for record in records:
        if record.status != RESOLVED or record.observed_value is None:
            continue
        if record.kind == BINARY:
            magnitude = record.brier if record.brier is not None else 0.0
        elif record.absolute_error is not None:
            magnitude = record.absolute_error
        elif record.predicted_value is not None:
            magnitude = abs(record.observed_value - record.predicted_value)
        else:
            continue
        scored.append((float(magnitude), record))

    scored.sort(key=lambda pair: pair[0], reverse=True)
    changes = reliability_changes or {}

    out: List[MissReport] = []
    for _, record in scored[:limit]:
        decomposition = attribute(record)
        relevant: List[Dict[str, Any]] = []
        for share in decomposition.shares:
            relevant.extend(changes.get(share.contributor, []))
        out.append(
            MissReport(
                prediction_id=record.prediction_id,
                subject=record.subject,
                target=record.target,
                valid_at=record.valid_at,
                predicted=record.predicted_value,
                observed=record.observed_value,
                error=(
                    None if record.predicted_value is None
                    else record.observed_value - record.predicted_value
                ),
                kind=record.kind,
                context=record.context.to_dict(),
                attribution=decomposition,
                reliability_changes=relevant[:4],
            )
        )
    return out


__all__ = [
    "Attribution",
    "ContributionShare",
    "MissReport",
    "attribute",
    "rank_misses",
    "verify_decomposition",
]
