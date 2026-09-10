"""The Outcome Agent: compare what we said with what happened.

This is the pass that turns the ledger from a log into a feedback loop. It runs
after observations land and does four things, in this order:

1.  **Resolve.** Every open claim whose ``valid_at`` has passed is matched
    against an observation and scored with the proper rule for its kind.
2.  **Score.** Resolved rows are aggregated into calibration and error reports,
    sliced by domain, model, horizon and context.
3.  **Attribute.** The worst misses are decomposed across their contributors.
4.  **Recalibrate.** Reliability weights are refitted from resolved rows only,
    behind a leakage barrier, and written back.

The agent computes nothing operational itself. It reads observations that other
parts of the system measured, applies the scoring rules in
:mod:`~src.portwatch_os.learning.scoring`, and writes numbers back. That is the
whole contract, and it is why an LLM is nowhere near this file.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Dict, Iterable, List, Optional, Sequence, Tuple

from src.portwatch_os.ledger.schema import (
    BINARY,
    CONTINUOUS,
    DecisionRecord,
    EventOutcomeRecord,
    OPEN,
    PredictionRecord,
    RESOLVED,
    ReliabilityRecord,
    horizon_bucket,
    utc_now,
)
from src.portwatch_os.ledger.store import LedgerStore
from src.portwatch_os.learning.attribution import MissReport, rank_misses
from src.portwatch_os.learning.reliability import (
    ReliabilityTable,
    fit_reliability,
)
from src.portwatch_os.learning.scoring import (
    BinaryScoreReport,
    ErrorReport,
    Residual,
    binary_report,
    brier_score,
    error_report,
    log_loss,
)
from src.utils.logging_utils import get_logger

log = get_logger(__name__)

#: A function that answers "what was actually observed for this claim?".
#: Returning ``None`` means the observation is not available yet, which is a
#: normal state and must not be confused with an observation of zero.
Observer = Callable[[PredictionRecord], Optional[Tuple[float, str, str]]]

#: Same idea for events: did the claimed thing happen, when, and per what source.
EventObserver = Callable[[EventOutcomeRecord], Optional[Tuple[bool, str, str, Dict[str, float]]]]


def _parse(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


# --------------------------------------------------------------------------
# scoring one row
# --------------------------------------------------------------------------


def score_prediction(record: PredictionRecord, observed: float) -> Dict[str, Any]:
    """Metrics for one claim against one observation, by claim kind."""
    metrics: Dict[str, Any] = {}
    if record.kind == BINARY:
        occurred = bool(observed)
        probability = float(record.predicted_value or 0.0)
        metrics["brier"] = round(brier_score(probability, occurred), 6)
        metrics["log_loss"] = round(log_loss(probability, occurred), 6)
        metrics["error"] = round((1.0 if occurred else 0.0) - probability, 6)
        metrics["absolute_error"] = abs(metrics["error"])
    else:
        predicted = record.predicted_value
        if predicted is not None:
            metrics["error"] = round(observed - float(predicted), 6)
            metrics["absolute_error"] = abs(metrics["error"])
        if record.predicted_low is not None and record.predicted_high is not None:
            metrics["within_interval"] = bool(
                record.predicted_low <= observed <= record.predicted_high
            )
    return metrics


def score_event_outcome(record: EventOutcomeRecord, occurred: bool,
                        observed_impact: Dict[str, float]) -> Dict[str, Any]:
    metrics: Dict[str, Any] = {
        "brier": round(brier_score(record.predicted_probability, occurred), 6),
        "log_loss": round(log_loss(record.predicted_probability, occurred), 6),
    }
    if occurred and record.predicted_impact and observed_impact:
        shared = set(record.predicted_impact) & set(observed_impact)
        if shared:
            metrics["impact_error"] = round(
                sum(
                    abs(float(observed_impact[k]) - float(record.predicted_impact[k]))
                    for k in shared
                ) / len(shared),
                6,
            )
    return metrics


# --------------------------------------------------------------------------
# reports
# --------------------------------------------------------------------------


@dataclass
class SliceReport:
    """One slice of resolved history, with the report its claim kind deserves."""

    key: str
    label: str
    count: int
    continuous: Optional[ErrorReport] = None
    binary: Optional[BinaryScoreReport] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "key": self.key,
            "label": self.label,
            "count": self.count,
            "continuous": self.continuous.to_dict() if self.continuous else None,
            "binary": self.binary.to_dict() if self.binary else None,
        }


def _slice_report(key: str, label: str, records: Sequence[PredictionRecord]) -> SliceReport:
    residuals = [
        Residual(
            predicted=float(r.predicted_value),
            observed=float(r.observed_value),
            low=r.predicted_low,
            high=r.predicted_high,
            nominal=r.interval_nominal,
        )
        for r in records
        if r.kind != BINARY and r.predicted_value is not None and r.observed_value is not None
    ]
    binary_pairs = [
        (float(r.predicted_value), bool(r.observed_value))
        for r in records
        if r.kind == BINARY and r.predicted_value is not None and r.observed_value is not None
    ]
    leads = [r.lead_time_hours for r in records if r.kind == BINARY]
    return SliceReport(
        key=key,
        label=label,
        count=len(records),
        continuous=error_report(residuals) if residuals else None,
        binary=binary_report(binary_pairs, lead_times=leads) if binary_pairs else None,
    )


@dataclass
class OutcomeRun:
    """Everything one pass of the Outcome Agent produced."""

    ran_at: str
    resolved_predictions: int = 0
    resolved_events: int = 0
    resolved_decisions: int = 0
    pending_predictions: int = 0
    pending_events: int = 0
    overall: Optional[SliceReport] = None
    by_domain: List[SliceReport] = field(default_factory=list)
    by_model: List[SliceReport] = field(default_factory=list)
    by_horizon: List[SliceReport] = field(default_factory=list)
    by_port: List[SliceReport] = field(default_factory=list)
    event_scores: Dict[str, Any] = field(default_factory=dict)
    reliability_updates: List[Dict[str, Any]] = field(default_factory=list)
    misses: List[MissReport] = field(default_factory=list)
    notes: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "ranAt": self.ran_at,
            "resolved": {
                "predictions": self.resolved_predictions,
                "events": self.resolved_events,
                "decisions": self.resolved_decisions,
            },
            "pending": {
                "predictions": self.pending_predictions,
                "events": self.pending_events,
            },
            "overall": self.overall.to_dict() if self.overall else None,
            "byDomain": [s.to_dict() for s in self.by_domain],
            "byModel": [s.to_dict() for s in self.by_model],
            "byHorizon": [s.to_dict() for s in self.by_horizon],
            "byPort": [s.to_dict() for s in self.by_port],
            "eventScores": self.event_scores,
            "reliabilityUpdates": self.reliability_updates,
            "misses": [m.to_dict() for m in self.misses],
            "notes": self.notes,
        }


# --------------------------------------------------------------------------
# the agent
# --------------------------------------------------------------------------


class OutcomeAgent:
    """Resolves, scores, attributes and recalibrates. Nothing else.

    The two observer callables are injected rather than imported so the agent
    never decides for itself what "actually happened" means. In the pipeline they
    read the observed panel and the event feed; in tests they are deterministic
    stubs; in a deployment they could read a port authority's own record.
    """

    def __init__(
        self,
        store: LedgerStore,
        *,
        observer: Optional[Observer] = None,
        event_observer: Optional[EventObserver] = None,
    ) -> None:
        self.store = store
        self.observer = observer
        self.event_observer = event_observer

    # -- resolution --------------------------------------------------------
    def resolve_due(self, now: Optional[str] = None) -> Tuple[int, int]:
        """Score every open claim whose observation is available.

        Returns ``(resolved, still_pending)``. Pending is not a failure: a claim
        about tomorrow simply has no observation today, and reporting it as an
        error would train operators to ignore the count.
        """
        now = now or utc_now()
        barrier = _parse(now)
        resolved = 0
        pending = 0

        if self.observer is not None:
            for record in self.store.predictions(status=OPEN):
                valid_at = _parse(record.valid_at)
                if barrier is not None and valid_at is not None and valid_at > barrier:
                    pending += 1
                    continue
                observation = self.observer(record)
                if observation is None:
                    pending += 1
                    continue
                value, observed_at, source = observation
                self.store.resolve_prediction(
                    record.prediction_id, float(value), observed_at, source,
                    score_prediction(record, float(value)),
                )
                resolved += 1

        return resolved, pending

    def resolve_events(self, now: Optional[str] = None) -> Tuple[int, int]:
        now = now or utc_now()
        barrier = _parse(now)
        resolved = 0
        pending = 0
        if self.event_observer is None:
            return 0, len(self.store.event_outcomes(status=OPEN))

        for record in self.store.event_outcomes(status=OPEN):
            resolve_by = _parse(record.resolve_by)
            observation = self.event_observer(record)
            if observation is None:
                # An unresolved claim past its horizon did not happen. That is a
                # measurement, and refusing to make it would quietly drop every
                # false alarm from the calibration -- the exact rows that matter.
                if barrier is not None and resolve_by is not None and resolve_by <= barrier:
                    metrics = score_event_outcome(record, False, {})
                    self.store.resolve_event_outcome(
                        record.outcome_id, False, now,
                        "horizon elapsed with no confirming observation", {}, metrics,
                    )
                    resolved += 1
                else:
                    pending += 1
                continue
            occurred, observed_at, source, impact = observation
            metrics = score_event_outcome(record, occurred, impact)
            self.store.resolve_event_outcome(
                record.outcome_id, occurred, observed_at, source, impact, metrics,
            )
            resolved += 1
        return resolved, pending

    # -- scoring -----------------------------------------------------------
    def score_history(self, records: Optional[Sequence[PredictionRecord]] = None) -> Dict[str, Any]:
        rows = list(records if records is not None else self.store.predictions(status=RESOLVED))
        overall = _slice_report("overall", "All resolved claims", rows)

        by_domain = _group(rows, lambda r: r.domain, "Domain")
        by_model = _group(rows, lambda r: r.model, "Model")
        by_horizon = _group(
            rows,
            lambda r: (
                horizon_bucket(float(r.context.horizon_hours))
                if r.context.horizon_hours is not None else "unspecified"
            ),
            "Horizon",
        )
        by_port = _group(
            rows, lambda r: r.context.port_code or r.subject or "unspecified", "Port"
        )
        return {
            "overall": overall,
            "byDomain": by_domain,
            "byModel": by_model,
            "byHorizon": by_horizon,
            "byPort": by_port,
        }

    def score_events(self) -> Dict[str, Any]:
        """Event calibration overall and per category, region, source and horizon."""
        rows = [r for r in self.store.event_outcomes(status=RESOLVED) if r.occurred is not None]
        if not rows:
            return {
                "available": False,
                "note": (
                    "No event claim has reached its horizon yet, so Global Eye "
                    "calibration is unavailable rather than perfect."
                ),
                "count": 0,
            }

        def report(subset: Sequence[EventOutcomeRecord]) -> Dict[str, Any]:
            pairs = [(r.predicted_probability, bool(r.occurred)) for r in subset]
            leads = [r.lead_time_hours for r in subset]
            return binary_report(pairs, lead_times=leads).to_dict()

        by_category: Dict[str, List[EventOutcomeRecord]] = {}
        by_region: Dict[str, List[EventOutcomeRecord]] = {}
        by_horizon: Dict[str, List[EventOutcomeRecord]] = {}
        by_confidence: Dict[str, List[EventOutcomeRecord]] = {}
        by_source: Dict[str, List[EventOutcomeRecord]] = {}

        for row in rows:
            by_category.setdefault(row.category, []).append(row)
            by_region.setdefault(row.region or "unspecified", []).append(row)
            by_horizon.setdefault(horizon_bucket(row.horizon_hours), []).append(row)
            bucket = (
                "high" if (row.confidence or 0) >= 0.7
                else "medium" if (row.confidence or 0) >= 0.4
                else "low"
            )
            by_confidence.setdefault(bucket, []).append(row)
            for source in row.sources or ["unattributed"]:
                by_source.setdefault(source, []).append(row)

        return {
            "available": True,
            "count": len(rows),
            "overall": report(rows),
            "byCategory": {k: report(v) for k, v in sorted(by_category.items())},
            "byRegion": {k: report(v) for k, v in sorted(by_region.items())},
            "byHorizon": {k: report(v) for k, v in sorted(by_horizon.items())},
            "byConfidence": {k: report(v) for k, v in sorted(by_confidence.items())},
            "bySource": {
                k: report(v)
                for k, v in sorted(by_source.items(), key=lambda kv: -len(kv[1]))[:12]
            },
        }

    # -- recalibration -----------------------------------------------------
    def recalibrate(self, *, as_of: Optional[str] = None) -> List[Dict[str, Any]]:
        """Refit reliability from resolved rows behind a leakage barrier."""
        as_of = as_of or utc_now()
        # Only rows already observed before the barrier may inform the fit.
        rows = [
            r for r in self.store.predictions(status=RESOLVED)
            if r.observed_at is None or r.observed_at < as_of
        ]
        previous = self.store.reliability()
        fitted = fit_reliability(rows, as_of=as_of, previous=previous)

        changes: List[Dict[str, Any]] = []
        for record in fitted:
            self.store.upsert_reliability(record)
            if record.previous_weight is None:
                continue
            delta = record.weight - record.previous_weight
            if abs(delta) < 1e-4:
                continue
            changes.append(
                {
                    "contributor": record.contributor,
                    "context": record.context_key,
                    "from": round(record.previous_weight, 4),
                    "to": round(record.weight, 4),
                    "delta": round(delta, 4),
                    "samples": record.sample_count,
                    "meanAbsoluteError": record.mean_absolute_error,
                    "bias": record.bias,
                }
            )
        changes.sort(key=lambda c: abs(c["delta"]), reverse=True)
        return changes

    def reliability_table(self) -> ReliabilityTable:
        return ReliabilityTable.from_records(self.store.reliability())

    # -- the full pass -----------------------------------------------------
    def run(self, *, now: Optional[str] = None, miss_limit: int = 10) -> OutcomeRun:
        now = now or utc_now()
        run = OutcomeRun(ran_at=now)

        run.resolved_predictions, run.pending_predictions = self.resolve_due(now)
        run.resolved_events, run.pending_events = self.resolve_events(now)

        resolved = self.store.predictions(status=RESOLVED)
        scored = self.score_history(resolved)
        run.overall = scored["overall"]
        run.by_domain = scored["byDomain"]
        run.by_model = scored["byModel"]
        run.by_horizon = scored["byHorizon"]
        run.by_port = scored["byPort"]
        run.event_scores = self.score_events()

        run.reliability_updates = self.recalibrate(as_of=now)
        by_contributor: Dict[str, List[Dict[str, Any]]] = {}
        for change in run.reliability_updates:
            by_contributor.setdefault(change["contributor"], []).append(change)
        run.misses = rank_misses(resolved, limit=miss_limit,
                                 reliability_changes=by_contributor)

        if not resolved:
            run.notes.append(
                "The ledger holds no resolved claims yet. Calibration, reliability and "
                "attribution are unavailable until observations arrive."
            )
        if run.pending_predictions:
            run.notes.append(
                f"{run.pending_predictions} claims are still open because the instant "
                "they describe has not arrived or no observation has landed."
            )
        log.info(
            "Outcome pass: resolved %d predictions, %d events; %d reliability weights moved.",
            run.resolved_predictions, run.resolved_events, len(run.reliability_updates),
        )
        return run

    # -- decisions ---------------------------------------------------------
    def score_decisions(self) -> Dict[str, Any]:
        """How recommendations fared, and whether operators took them.

        The take-up rate is reported alongside the reward because a policy that
        is never accepted has no operational value regardless of how good its
        simulated reward looks.
        """
        rows = self.store.decisions()
        if not rows:
            return {"available": False, "count": 0}
        resolved = [r for r in rows if r.status == RESOLVED]
        taken = [r for r in resolved if r.action_state in ("taken", "modified")]
        rewards = [r.operational_reward for r in resolved if r.operational_reward is not None]
        errors = [r.impact_error for r in resolved if r.impact_error is not None]
        by_kind: Dict[str, Dict[str, Any]] = {}
        for row in resolved:
            bucket = by_kind.setdefault(row.kind, {"count": 0, "rewards": [], "taken": 0})
            bucket["count"] += 1
            if row.operational_reward is not None:
                bucket["rewards"].append(row.operational_reward)
            if row.action_state in ("taken", "modified"):
                bucket["taken"] += 1
        return {
            "available": True,
            "count": len(rows),
            "resolved": len(resolved),
            "takeUpRate": round(len(taken) / len(resolved), 4) if resolved else None,
            "meanReward": round(sum(rewards) / len(rewards), 4) if rewards else None,
            "meanImpactError": round(sum(errors) / len(errors), 4) if errors else None,
            "byKind": {
                kind: {
                    "count": v["count"],
                    "takeUpRate": round(v["taken"] / v["count"], 4) if v["count"] else None,
                    "meanReward": (
                        round(sum(v["rewards"]) / len(v["rewards"]), 4) if v["rewards"] else None
                    ),
                }
                for kind, v in sorted(by_kind.items())
            },
        }


def _group(
    rows: Sequence[PredictionRecord],
    key: Callable[[PredictionRecord], str],
    label_prefix: str,
) -> List[SliceReport]:
    buckets: Dict[str, List[PredictionRecord]] = {}
    for row in rows:
        buckets.setdefault(key(row), []).append(row)
    return [
        _slice_report(name, f"{label_prefix} · {name}", subset)
        for name, subset in sorted(buckets.items(), key=lambda kv: -len(kv[1]))
    ]


__all__ = [
    "EventObserver",
    "Observer",
    "OutcomeAgent",
    "OutcomeRun",
    "SliceReport",
    "score_event_outcome",
    "score_prediction",
]
