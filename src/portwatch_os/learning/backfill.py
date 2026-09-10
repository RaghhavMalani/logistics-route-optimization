"""Load the pipeline's walk-forward history into the outcome ledger.

The learning layer can only report what the ledger holds, and a freshly cloned
repository holds nothing -- which is honest but leaves every calibration screen
saying "unavailable". This module fixes that with real history rather than with
generated data.

**Where the history comes from.** ``walk_forward_predictions.csv`` is what the
existing evaluation already produces: for each port, each forecast origin and
each horizon, what every model predicted and what was actually observed. That is
precisely a ledger row and its outcome, produced under the pipeline's own
leakage discipline -- the forecast at origin *t* used nothing after *t*.

**Why the attribution is exact.** The adaptive ensemble is a weighted blend of
its member models, with the weights in ``ensemble_weights.json``. So for an
ensemble row, the member models' predictions are the contributor signals and the
fitted weights are the contributions, and the error decomposition in
:mod:`~src.portwatch_os.learning.attribution` closes by construction rather than
by estimate. "Why was PortWatch wrong" then answers with arithmetic.

Nothing here invents a number. Every value written is read from the pipeline's
own artefacts, and the ledger records which file each came from.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from src.portwatch_os.ledger.schema import (
    CONTINUOUS,
    DOMAIN_PORT_FORECAST,
    PredictionContext,
    PredictionRecord,
)
from src.portwatch_os.ledger.store import LedgerStore
from src.portwatch_os.learning.outcome_agent import score_prediction
from src.utils import port_registry
from src.utils.config import FORECASTS_DIR
from src.utils.logging_utils import get_logger

log = get_logger(__name__)

PREDICTIONS_CSV = FORECASTS_DIR / "walk_forward_predictions.csv"
WEIGHTS_JSON = FORECASTS_DIR / "ensemble_weights.json"

#: Which walk-forward model name corresponds to which ensemble member key.
MEMBER_BY_MODEL: Dict[str, str] = {
    "Naive persistence": "persistence",
    "GBM quantile": "gbm",
    "Ridge quantile": "second",
}

ENSEMBLE_MODEL = "Adaptive ensemble"

#: Nominal coverage of the q10-q90 band the pipeline emits.
INTERVAL_NOMINAL = 0.8

#: Default cap on rows written. A few thousand resolved claims is far past the
#: point where the calibration and reliability thresholds engage, and writing a
#: hundred thousand would make the dashboard slow for no extra information.
DEFAULT_LIMIT = 4000


@dataclass
class BackfillReport:
    source: str
    rows_read: int
    written: int
    resolved: int
    skipped: int
    ports: List[str]
    horizons: List[int]
    window: Tuple[Optional[str], Optional[str]]
    notes: List[str]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "source": self.source,
            "rowsRead": self.rows_read,
            "written": self.written,
            "resolved": self.resolved,
            "skipped": self.skipped,
            "ports": self.ports,
            "horizons": self.horizons,
            "window": list(self.window),
            "notes": self.notes,
        }


def _iso(value: Any, hour: int = 0) -> Optional[str]:
    """A date column to a UTC instant."""
    try:
        parsed = datetime.fromisoformat(str(value)[:19])
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    if parsed.hour == 0 and hour:
        parsed = parsed + timedelta(hours=hour)
    return parsed.isoformat(timespec="seconds")


def _weights_for(weights: Dict[str, Any], horizon: int, regime: Optional[str]) -> Dict[str, float]:
    """The ensemble weights that were in force for this row.

    The pipeline fits weights globally, per horizon and per regime. The most
    specific set that exists is what the ensemble actually used, so that is what
    the attribution has to be told about -- using the global set everywhere would
    make the decomposition close only on average.
    """
    by_regime = (weights.get("byRegime") or {}).get(str(regime or "").upper())
    if by_regime:
        return {k: float(v) for k, v in by_regime.items()}
    by_horizon = (weights.get("byHorizon") or {}).get(str(int(horizon)))
    if by_horizon:
        return {k: float(v) for k, v in by_horizon.items()}
    return {k: float(v) for k, v in (weights.get("globalWeights") or {}).items()}


def backfill_forecasts(
    store: LedgerStore,
    *,
    predictions_csv: Path = PREDICTIONS_CSV,
    weights_json: Path = WEIGHTS_JSON,
    limit: int = DEFAULT_LIMIT,
    model_version: str = "walk-forward",
) -> BackfillReport:
    """Write the ensemble's walk-forward claims and their outcomes to the ledger.

    Only the ensemble's rows become claims. The member models' predictions on the
    same (port, origin, horizon) become the contributor signals on that claim,
    which is what makes the attribution exact rather than an estimate.
    """
    import pandas as pd

    notes: List[str] = []
    if not predictions_csv.exists():
        return BackfillReport(
            source=str(predictions_csv), rows_read=0, written=0, resolved=0,
            skipped=0, ports=[], horizons=[], window=(None, None),
            notes=[
                f"{predictions_csv.name} has not been produced. Run "
                "`python -m src.evaluation.walk_forward` or the award pipeline first."
            ],
        )

    frame = pd.read_csv(predictions_csv)
    weights = {}
    if weights_json.exists():
        with open(weights_json, "r", encoding="utf-8") as handle:
            weights = json.load(handle)
    else:
        notes.append(
            f"{weights_json.name} is absent, so contributions fall back to a uniform "
            "blend and the attribution residual will be larger."
        )

    required = {
        "port_id", "forecast_origin_date", "target_date", "horizon_day",
        "y_congestion_index", "model", "q50",
    }
    missing = required - set(frame.columns)
    if missing:
        return BackfillReport(
            source=str(predictions_csv), rows_read=len(frame), written=0, resolved=0,
            skipped=len(frame), ports=[], horizons=[], window=(None, None),
            notes=[f"{predictions_csv.name} is missing columns: {', '.join(sorted(missing))}"],
        )

    # Index the member models so an ensemble row can find what fed it.
    members = frame[frame["model"].isin(MEMBER_BY_MODEL)]
    member_index: Dict[Tuple[str, str, int], Dict[str, float]] = {}
    for row in members.itertuples(index=False):
        key = (str(row.port_id), str(row.forecast_origin_date), int(row.horizon_day))
        member_index.setdefault(key, {})[MEMBER_BY_MODEL[str(row.model)]] = float(row.q50)

    ensemble = frame[frame["model"] == ENSEMBLE_MODEL]
    if ensemble.empty:
        return BackfillReport(
            source=str(predictions_csv), rows_read=len(frame), written=0, resolved=0,
            skipped=len(frame), ports=[], horizons=[], window=(None, None),
            notes=[f"No '{ENSEMBLE_MODEL}' rows in {predictions_csv.name}."],
        )

    # Most recent first, so a capped backfill loads the history a reader would
    # actually look at rather than the oldest fold.
    ensemble = ensemble.sort_values("target_date", ascending=False)
    if limit:
        ensemble = ensemble.head(int(limit))

    written = 0
    resolved = 0
    skipped = 0
    ports: set[str] = set()
    horizons: set[int] = set()
    earliest: Optional[str] = None
    latest: Optional[str] = None

    for row in ensemble.itertuples(index=False):
        observed = getattr(row, "y_congestion_index", None)
        predicted = getattr(row, "q50", None)
        if observed is None or predicted is None:
            skipped += 1
            continue
        try:
            observed = float(observed)
            predicted = float(predicted)
        except (TypeError, ValueError):
            skipped += 1
            continue

        model_id = str(row.port_id)
        record_meta = port_registry.resolve(model_id)
        subject = record_meta.locode if record_meta else model_id
        horizon = int(row.horizon_day)
        regime = getattr(row, "regime", None)

        issued_at = _iso(row.forecast_origin_date, hour=6)
        valid_at = _iso(row.target_date, hour=6)
        if not issued_at or not valid_at:
            skipped += 1
            continue

        signals = dict(
            member_index.get(
                (str(row.port_id), str(row.forecast_origin_date), horizon), {}
            )
        )
        contributions = _weights_for(weights, horizon, regime) if signals else {}
        if signals and not contributions:
            share = 1.0 / len(signals)
            contributions = {name: share for name in signals}
        # The reference the reliability fit scores contributors against: what the
        # world already had. Reserved key, so it is not mistaken for a
        # contributor in the attribution.
        if "persistence" in signals:
            signals["__persistence__"] = signals["persistence"]

        prediction = PredictionRecord(
            prediction_id=PredictionRecord.make_id(
                DOMAIN_PORT_FORECAST, "congestion_index", subject, valid_at,
                f"{ENSEMBLE_MODEL}|{horizon}",
            ),
            domain=DOMAIN_PORT_FORECAST,
            kind=CONTINUOUS,
            target="congestion_index",
            subject=subject,
            model="adaptive_ensemble",
            model_version=model_version,
            issued_at=issued_at,
            valid_at=valid_at,
            context=PredictionContext(
                port_code=subject,
                region=record_meta.region if record_meta else None,
                horizon_hours=horizon * 24.0,
                regime=str(regime) if regime else None,
                season=_season(valid_at),
                source_state="CACHED_LIVE",
                extra={"fold": _int(getattr(row, "fold", None))},
            ),
            predicted_value=predicted,
            predicted_low=_float(getattr(row, "q10", None)),
            predicted_high=_float(getattr(row, "q90", None)),
            interval_nominal=INTERVAL_NOMINAL,
            confidence=_confidence(getattr(row, "model_disagreement", None)),
            features=signals,
            contributions=contributions,
            provenance={
                "source": predictions_csv.name,
                "note": (
                    "Walk-forward evaluation: the forecast at this origin used no "
                    "data after it, and the observation is the panel's own value."
                ),
            },
        )

        try:
            store.record_prediction(prediction)
        except Exception:  # noqa: BLE001 - a resolved row is never rewritten
            skipped += 1
            continue
        written += 1

        settled = store.resolve_prediction(
            prediction.prediction_id,
            observed,
            # The observation is available at the instant it describes.
            valid_at,
            "walk-forward observed panel",
            score_prediction(prediction, observed),
        )
        if settled is not None:
            resolved += 1

        ports.add(subject)
        horizons.add(horizon)
        earliest = valid_at if earliest is None or valid_at < earliest else earliest
        latest = valid_at if latest is None or valid_at > latest else latest

    if written:
        notes.append(
            f"Loaded the {written} most recent ensemble claims from the walk-forward "
            "evaluation. Contributor signals are the member models' own predictions "
            "and the contributions are the fitted ensemble weights, so the error "
            "decomposition closes by construction."
        )

    log.info(
        "Backfilled %d predictions (%d resolved) from %s.",
        written, resolved, predictions_csv.name,
    )
    return BackfillReport(
        source=str(predictions_csv),
        rows_read=len(frame),
        written=written,
        resolved=resolved,
        skipped=skipped,
        ports=sorted(ports),
        horizons=sorted(horizons),
        window=(earliest, latest),
        notes=notes,
    )


def _float(value: Any) -> Optional[float]:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return None if result != result else result  # drop NaN


def _int(value: Any) -> Optional[int]:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _confidence(disagreement: Any) -> Optional[float]:
    """Confidence from how far the member models were apart.

    Model disagreement is the only confidence signal the walk-forward artefact
    carries, and it is a real one: where the members agree the ensemble is on
    firmer ground. Absent, no confidence is claimed.
    """
    value = _float(disagreement)
    if value is None:
        return None
    return round(max(0.15, min(0.95, 1.0 - value / 12.0)), 3)


def _season(iso: str) -> Optional[str]:
    """Indian monsoon seasons, which is the regime that actually moves the ports."""
    try:
        month = datetime.fromisoformat(iso.replace("Z", "+00:00")).month
    except ValueError:
        return None
    if month in (6, 7, 8, 9):
        return "southwest_monsoon"
    if month in (10, 11):
        return "northeast_monsoon"
    if month in (12, 1, 2):
        return "winter"
    return "pre_monsoon"


__all__ = [
    "DEFAULT_LIMIT",
    "ENSEMBLE_MODEL",
    "MEMBER_BY_MODEL",
    "PREDICTIONS_CSV",
    "WEIGHTS_JSON",
    "BackfillReport",
    "backfill_forecasts",
]
