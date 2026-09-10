"""The prediction and decision ledger: what we said, and what happened.

Nothing in this system may learn from an outcome it did not record at the time
it made the claim. That is the whole point of the ledger, and it drives three
design rules that the dataclasses below enforce:

1.  **A claim is written before its outcome exists.** ``PredictionRecord`` and
    ``DecisionRecord`` carry ``issued_at`` and, separately, the horizon the
    claim is about. An outcome that arrives later is a *different* row keyed by
    the claim's id, so a resolved claim can never be silently rewritten into a
    better one.

2.  **Context is stored, not re-derived.** Reliability is learned per context
    (port, horizon, regime, season, source freshness). If the context were
    recomputed at scoring time from today's data, the weights would be fitted on
    information the model did not have. Every record therefore carries the
    context that was true when it was issued.

3.  **Everything is auditable.** Each record names the model and version, the
    features that drove it, and the provenance state of the inputs. A
    calibration that cannot be traced to the evidence behind it is not a
    calibration; it is a fudge factor.

Records serialise to plain JSON dicts, so the storage layer can be SQLite today
and a real database later without any of the callers changing.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

# --------------------------------------------------------------------------
# kinds
# --------------------------------------------------------------------------

#: What kind of claim a prediction row carries. Each is scored differently:
#: continuous claims by error and interval coverage, binary claims by Brier
#: score and log loss.
CONTINUOUS = "continuous"
BINARY = "binary"
CATEGORICAL = "categorical"

PREDICTION_KINDS = (CONTINUOUS, BINARY, CATEGORICAL)

#: Where a claim came from. Used to slice reliability without string matching
#: on model names.
DOMAIN_PORT_FORECAST = "port_forecast"
DOMAIN_WEATHER = "weather"
DOMAIN_EVENT = "event"
DOMAIN_PORT_OPS = "port_ops"
DOMAIN_ROUTE = "route"
DOMAIN_CARGO = "cargo"

DOMAINS = (
    DOMAIN_PORT_FORECAST,
    DOMAIN_WEATHER,
    DOMAIN_EVENT,
    DOMAIN_PORT_OPS,
    DOMAIN_ROUTE,
    DOMAIN_CARGO,
)

#: Lifecycle of a claim.
OPEN = "open"
RESOLVED = "resolved"
EXPIRED = "expired"
SUPERSEDED = "superseded"

STATUSES = (OPEN, RESOLVED, EXPIRED, SUPERSEDED)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _stable_id(prefix: str, *parts: Any) -> str:
    """A deterministic id, so re-running a pipeline updates rather than duplicates."""
    digest = hashlib.sha1("|".join(str(p) for p in parts).encode("utf-8")).hexdigest()
    return f"{prefix}-{digest[:16]}"


# --------------------------------------------------------------------------
# context
# --------------------------------------------------------------------------


@dataclass
class PredictionContext:
    """The situation a claim was made in.

    Reliability is not a scalar property of a model; it is a property of a model
    *in a context*. A weather expert that is well calibrated on the west coast in
    the pre-monsoon can be badly biased on the south-east coast at +24 h during
    an active monsoon, and blending those into one number hides both.

    Every field here is knowable at issue time. Nothing is filled in later.
    """

    port_code: Optional[str] = None
    region: Optional[str] = None
    #: Forecast lead in hours. Reliability degrades with horizon, so it is a
    #: first-class slice rather than a free-text tag.
    horizon_hours: Optional[float] = None
    #: HSMM regime label at issue time.
    regime: Optional[str] = None
    #: Coarse weather regime, e.g. "monsoon_active".
    weather_regime: Optional[str] = None
    #: Global Eye event regime, e.g. "chokepoint_disruption".
    event_regime: Optional[str] = None
    #: Provenance state of the worst input, from src.utils.provenance.
    source_state: Optional[str] = None
    #: Age of the freshest driving input, hours.
    source_age_hours: Optional[float] = None
    season: Optional[str] = None
    extra: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, payload: Dict[str, Any] | None) -> "PredictionContext":
        payload = dict(payload or {})
        known = {f for f in cls.__dataclass_fields__}  # type: ignore[attr-defined]
        extra = payload.pop("extra", {}) or {}
        unknown = {k: v for k, v in payload.items() if k not in known}
        kept = {k: v for k, v in payload.items() if k in known}
        kept["extra"] = {**extra, **unknown}
        return cls(**kept)

    def bucket_key(self, *dimensions: str) -> str:
        """A stable key over chosen context dimensions, for reliability tables."""
        values = []
        for dim in dimensions:
            value = getattr(self, dim, None)
            if dim == "horizon_hours" and value is not None:
                value = horizon_bucket(float(value))
            values.append(f"{dim}={value if value is not None else 'any'}")
        return "|".join(values)


#: Horizon buckets. Coarse on purpose: a per-hour reliability table over a few
#: hundred resolved claims is noise dressed up as precision.
HORIZON_BUCKETS: List[tuple[float, str]] = [
    (6.0, "0-6h"),
    (12.0, "6-12h"),
    (24.0, "12-24h"),
    (48.0, "24-48h"),
    (72.0, "48-72h"),
    (168.0, "72h-7d"),
]


def horizon_bucket(hours: float) -> str:
    for upper, label in HORIZON_BUCKETS:
        if hours <= upper:
            return label
    return "7d+"


# --------------------------------------------------------------------------
# predictions
# --------------------------------------------------------------------------


@dataclass
class PredictionRecord:
    """One numerical or probabilistic claim, and its eventual outcome."""

    prediction_id: str
    domain: str
    kind: str
    #: What is being claimed, e.g. "congestion_index" or "closure_within_72h".
    target: str
    #: The entity the claim is about: port code, event id, vessel id, lane id.
    subject: str
    model: str
    model_version: str
    issued_at: str
    #: The instant the claim is about. Scoring may not run before this.
    valid_at: str
    context: PredictionContext

    #: Continuous claims: the point estimate. Binary: the probability in [0, 1].
    predicted_value: Optional[float] = None
    #: Quantile band where the model produced one.
    predicted_low: Optional[float] = None
    predicted_high: Optional[float] = None
    #: Nominal coverage of the band, e.g. 0.8 for a q10-q90 interval.
    interval_nominal: Optional[float] = None
    #: Self-reported confidence, distinct from a probability of an event.
    confidence: Optional[float] = None
    #: Per-contributor signals, e.g. {"weather_expert": 0.31}. Used by the
    #: attribution pass to answer "why was PortWatch wrong?".
    features: Dict[str, float] = field(default_factory=dict)
    #: Per-contributor weights at issue time, so a weight change is auditable.
    contributions: Dict[str, float] = field(default_factory=dict)
    provenance: Dict[str, Any] = field(default_factory=dict)

    status: str = OPEN
    observed_value: Optional[float] = None
    observed_at: Optional[str] = None
    observation_source: Optional[str] = None
    #: Signed error, observed minus predicted, for continuous claims.
    error: Optional[float] = None
    absolute_error: Optional[float] = None
    #: Brier score for binary claims.
    brier: Optional[float] = None
    log_loss: Optional[float] = None
    #: True when the observation fell inside the predicted band.
    within_interval: Optional[bool] = None
    #: Hours between issue and the observation becoming available.
    lead_time_hours: Optional[float] = None
    notes: Optional[str] = None

    @staticmethod
    def make_id(domain: str, target: str, subject: str, valid_at: str, model: str) -> str:
        return _stable_id("pred", domain, target, subject, valid_at, model)

    def to_row(self) -> Dict[str, Any]:
        row = asdict(self)
        row["context"] = json.dumps(self.context.to_dict(), sort_keys=True)
        row["features"] = json.dumps(self.features, sort_keys=True)
        row["contributions"] = json.dumps(self.contributions, sort_keys=True)
        row["provenance"] = json.dumps(self.provenance, sort_keys=True, default=str)
        return row

    @classmethod
    def from_row(cls, row: Dict[str, Any]) -> "PredictionRecord":
        data = dict(row)
        data["context"] = PredictionContext.from_dict(_loads(data.get("context")))
        data["features"] = _loads(data.get("features")) or {}
        data["contributions"] = _loads(data.get("contributions")) or {}
        data["provenance"] = _loads(data.get("provenance")) or {}
        if data.get("within_interval") is not None:
            data["within_interval"] = bool(data["within_interval"])
        known = set(cls.__dataclass_fields__)  # type: ignore[attr-defined]
        return cls(**{k: v for k, v in data.items() if k in known})


# --------------------------------------------------------------------------
# decisions
# --------------------------------------------------------------------------

#: What actually happened to a recommendation. ``NOT_TAKEN`` is as valuable as
#: ``TAKEN``: it is the only way to see whether operators trust the system.
ACTION_TAKEN = "taken"
ACTION_MODIFIED = "modified"
ACTION_NOT_TAKEN = "not_taken"
ACTION_PENDING = "pending"

ACTION_STATES = (ACTION_TAKEN, ACTION_MODIFIED, ACTION_NOT_TAKEN, ACTION_PENDING)


@dataclass
class DecisionRecord:
    """One recommendation, whether it was acted on, and what it was worth."""

    decision_id: str
    #: e.g. "berth_reassignment", "arrival_advisory", "reroute", "cargo_transfer".
    kind: str
    subject: str
    issued_at: str
    issuer: str
    recommendation: Dict[str, Any]
    reason: str
    #: Predictions this recommendation rests on. The learning pass uses these to
    #: separate "the forecast was wrong" from "the policy was wrong".
    prediction_ids: List[str] = field(default_factory=list)
    model: Optional[str] = None
    model_version: Optional[str] = None
    policy_id: Optional[str] = None
    confidence: Optional[float] = None
    #: What the recommendation claimed it would achieve, e.g.
    #: {"wait_hours_saved": 3.4}. Scored against the observed outcome.
    expected_impact: Dict[str, float] = field(default_factory=dict)
    critic_verdict: Optional[str] = None
    critic_reasons: List[str] = field(default_factory=list)
    approval_state: Optional[str] = None
    approver: Optional[str] = None

    status: str = OPEN
    action_state: str = ACTION_PENDING
    observed_outcome: Dict[str, float] = field(default_factory=dict)
    observed_at: Optional[str] = None
    #: Scalar reward, defined per kind by the learning layer.
    operational_reward: Optional[float] = None
    impact_error: Optional[float] = None
    notes: Optional[str] = None

    @staticmethod
    def make_id(kind: str, subject: str, issued_at: str, issuer: str) -> str:
        return _stable_id("dec", kind, subject, issued_at, issuer)

    def to_row(self) -> Dict[str, Any]:
        row = asdict(self)
        for key in ("recommendation", "prediction_ids", "expected_impact",
                    "critic_reasons", "observed_outcome"):
            row[key] = json.dumps(getattr(self, key), sort_keys=True, default=str)
        return row

    @classmethod
    def from_row(cls, row: Dict[str, Any]) -> "DecisionRecord":
        data = dict(row)
        for key, default in (
            ("recommendation", {}),
            ("prediction_ids", []),
            ("expected_impact", {}),
            ("critic_reasons", []),
            ("observed_outcome", {}),
        ):
            data[key] = _loads(data.get(key)) or default
        known = set(cls.__dataclass_fields__)  # type: ignore[attr-defined]
        return cls(**{k: v for k, v in data.items() if k in known})


# --------------------------------------------------------------------------
# event outcomes
# --------------------------------------------------------------------------


@dataclass
class EventOutcomeRecord:
    """What a Global Eye event claim turned into.

    Deliberately richer than a boolean. "We said 72% closure and it did not
    close" is not automatically a failure: a 72% claim should be wrong 28% of the
    time, and the lead time and the observed partial impact both matter. Storing
    the components separately is what lets the calibration pass ask the right
    question of the record instead of a yes/no one.
    """

    outcome_id: str
    event_id: str
    category: str
    region: Optional[str]
    #: The claim, e.g. "chokepoint_closure_within_72h".
    claim: str
    horizon_hours: float
    predicted_probability: float
    confidence: Optional[float]
    source_count: int
    sources: List[str] = field(default_factory=list)
    issued_at: str = ""
    resolve_by: str = ""

    status: str = OPEN
    occurred: Optional[bool] = None
    observed_at: Optional[str] = None
    observation_source: Optional[str] = None
    #: Measured impact where the event did occur, e.g. {"delay_hours": 8.1}.
    observed_impact: Dict[str, float] = field(default_factory=dict)
    predicted_impact: Dict[str, float] = field(default_factory=dict)
    #: A confident claim that did not happen. Tracked separately because the
    #: operational cost of a false alarm is not the same as of a miss.
    false_alarm: Optional[bool] = None
    #: Hours between the claim and the event, where it occurred. Positive lead
    #: time is the entire operational value of the prediction.
    lead_time_hours: Optional[float] = None
    brier: Optional[float] = None
    log_loss: Optional[float] = None
    impact_error: Optional[float] = None
    notes: Optional[str] = None

    @staticmethod
    def make_id(event_id: str, claim: str, horizon_hours: float) -> str:
        return _stable_id("evo", event_id, claim, horizon_hours)

    def to_row(self) -> Dict[str, Any]:
        row = asdict(self)
        for key in ("sources", "observed_impact", "predicted_impact"):
            row[key] = json.dumps(getattr(self, key), sort_keys=True, default=str)
        if row.get("occurred") is not None:
            row["occurred"] = int(bool(row["occurred"]))
        if row.get("false_alarm") is not None:
            row["false_alarm"] = int(bool(row["false_alarm"]))
        return row

    @classmethod
    def from_row(cls, row: Dict[str, Any]) -> "EventOutcomeRecord":
        data = dict(row)
        data["sources"] = _loads(data.get("sources")) or []
        data["observed_impact"] = _loads(data.get("observed_impact")) or {}
        data["predicted_impact"] = _loads(data.get("predicted_impact")) or {}
        for key in ("occurred", "false_alarm"):
            if data.get(key) is not None:
                data[key] = bool(data[key])
        known = set(cls.__dataclass_fields__)  # type: ignore[attr-defined]
        return cls(**{k: v for k, v in data.items() if k in known})


# --------------------------------------------------------------------------
# reliability
# --------------------------------------------------------------------------


@dataclass
class ReliabilityRecord:
    """A learned reliability weight for one contributor in one context.

    ``sample_count`` is not decoration. A weight fitted on eleven observations is
    reported with the eleven attached so a reader -- and the ensemble that
    consumes it -- can discount it. The shrinkage in
    :mod:`src.portwatch_os.learning.reliability` uses exactly this field.
    """

    contributor: str
    context_key: str
    #: Which dimensions the context key was built from, in order.
    dimensions: List[str]
    weight: float
    #: Weight before this update, so a change is always visible.
    previous_weight: Optional[float]
    sample_count: int
    mean_absolute_error: Optional[float] = None
    bias: Optional[float] = None
    calibration_error: Optional[float] = None
    updated_at: str = ""
    #: The window the fit used, so a reader can check for leakage.
    fitted_from: Optional[str] = None
    fitted_to: Optional[str] = None
    notes: Optional[str] = None

    def to_row(self) -> Dict[str, Any]:
        row = asdict(self)
        row["dimensions"] = json.dumps(self.dimensions)
        return row

    @classmethod
    def from_row(cls, row: Dict[str, Any]) -> "ReliabilityRecord":
        data = dict(row)
        data["dimensions"] = _loads(data.get("dimensions")) or []
        known = set(cls.__dataclass_fields__)  # type: ignore[attr-defined]
        return cls(**{k: v for k, v in data.items() if k in known})


# --------------------------------------------------------------------------
# policies
# --------------------------------------------------------------------------

CANDIDATE = "candidate"
EVALUATING = "evaluating"
APPROVED = "approved"
REJECTED = "rejected"
RETIRED = "retired"

POLICY_STATES = (CANDIDATE, EVALUATING, APPROVED, REJECTED, RETIRED)

#: The only legal transitions. A candidate cannot become approved without an
#: evaluation, and nothing returns from rejected -- a revised policy is a new
#: candidate with its own evidence.
POLICY_TRANSITIONS: Dict[str, tuple[str, ...]] = {
    CANDIDATE: (EVALUATING, REJECTED),
    EVALUATING: (APPROVED, REJECTED),
    APPROVED: (RETIRED,),
    REJECTED: (),
    RETIRED: (),
}


@dataclass
class PolicyRecord:
    """A learned or hand-written operating policy and its promotion state."""

    policy_id: str
    name: str
    family: str
    version: str
    state: str = CANDIDATE
    created_at: str = ""
    updated_at: str = ""
    #: Environment the policy was trained and evaluated in.
    environment: Optional[str] = None
    training: Dict[str, Any] = field(default_factory=dict)
    #: Measured evaluation against the baselines. Populated by the evaluator, not
    #: by the trainer, so a policy cannot grade its own homework.
    evaluation: Dict[str, Any] = field(default_factory=dict)
    baseline_policy_id: Optional[str] = None
    #: Hard constraints the evaluation checked, and whether each held.
    safety_checks: Dict[str, bool] = field(default_factory=dict)
    approved_by: Optional[str] = None
    approved_at: Optional[str] = None
    rejection_reason: Optional[str] = None
    notes: Optional[str] = None

    def to_row(self) -> Dict[str, Any]:
        row = asdict(self)
        for key in ("training", "evaluation", "safety_checks"):
            row[key] = json.dumps(getattr(self, key), sort_keys=True, default=str)
        return row

    @classmethod
    def from_row(cls, row: Dict[str, Any]) -> "PolicyRecord":
        data = dict(row)
        for key in ("training", "evaluation", "safety_checks"):
            data[key] = _loads(data.get(key)) or {}
        known = set(cls.__dataclass_fields__)  # type: ignore[attr-defined]
        return cls(**{k: v for k, v in data.items() if k in known})


def can_transition(current: str, target: str) -> bool:
    return target in POLICY_TRANSITIONS.get(current, ())


# --------------------------------------------------------------------------
# helpers
# --------------------------------------------------------------------------


def _loads(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, (dict, list)):
        return value
    try:
        return json.loads(value)
    except (TypeError, ValueError):
        return None


__all__ = [
    "ACTION_MODIFIED",
    "ACTION_NOT_TAKEN",
    "ACTION_PENDING",
    "ACTION_STATES",
    "ACTION_TAKEN",
    "APPROVED",
    "BINARY",
    "CANDIDATE",
    "CATEGORICAL",
    "CONTINUOUS",
    "DOMAINS",
    "DOMAIN_CARGO",
    "DOMAIN_EVENT",
    "DOMAIN_PORT_FORECAST",
    "DOMAIN_PORT_OPS",
    "DOMAIN_ROUTE",
    "DOMAIN_WEATHER",
    "EVALUATING",
    "EXPIRED",
    "HORIZON_BUCKETS",
    "OPEN",
    "POLICY_STATES",
    "POLICY_TRANSITIONS",
    "PREDICTION_KINDS",
    "REJECTED",
    "RESOLVED",
    "RETIRED",
    "STATUSES",
    "SUPERSEDED",
    "DecisionRecord",
    "EventOutcomeRecord",
    "PolicyRecord",
    "PredictionContext",
    "PredictionRecord",
    "ReliabilityRecord",
    "can_transition",
    "horizon_bucket",
    "utc_now",
]
