"""Issue-time weather snapshots, verified outcomes, and guarded residual learning.

Forecast API backfill is never accepted as an observation. The first automatic
verification source is explicitly labelled ERA5 reanalysis, not a port station.
Every correction uses only outcomes available before the forecast was retrieved.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

import numpy as np
import pandas as pd

from src.portwatch_os.clock import world_now
from src.portwatch_os.ledger.schema import (
    CONTINUOUS, DOMAIN_WEATHER, OPEN, RESOLVED, PredictionContext, PredictionRecord,
    _stable_id,
)
from src.portwatch_os.ledger.store import LedgerError, LedgerStore
from src.utils import port_registry
from src.utils.config import DATE, PORT_ID

VARIABLES = {"wind_speed": "kn", "wind_gust": "kn", "rainfall": "mm/day",
             "wave_height": "m", "visibility": "km"}
STATISTICS = {"wind_speed": "maximum", "wind_gust": "maximum", "rainfall": "sum",
              "wave_height": "maximum", "visibility": "mean"}
OBSERVATION_KINDS = ("station", "operator_measurement", "reanalysis")
MODEL_VERSION = "weather-residual-v3"
MIN_SAMPLES = 32
MIN_VALIDATION = 8


def instant(value: str | datetime) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00")) if isinstance(value, str) else value
    if parsed.tzinfo is None:
        raise ValueError("timestamps must include a timezone")
    return parsed.astimezone(timezone.utc)


def season(moment: datetime) -> str:
    return "monsoon" if 6 <= moment.month <= 9 else "post_monsoon" if moment.month >= 10 else "pre_monsoon"


@dataclass(frozen=True)
class WeatherObservation:
    port_code: str
    variable: str
    valid_at: str
    available_at: str
    value: float
    source: str
    kind: str
    unit: str
    aggregation: str = "daily"
    statistic: str | None = None

    def validate(self, now: datetime) -> None:
        valid, available = instant(self.valid_at), instant(self.available_at)
        if self.variable not in VARIABLES or self.unit != VARIABLES[self.variable]:
            raise ValueError("weather variable and unit must match the forecast")
        if not np.isfinite(self.value) or self.value < 0:
            raise ValueError("weather observations must be finite and nonnegative")
        if self.kind not in OBSERVATION_KINDS:
            raise ValueError("only station, operator_measurement or reanalysis outcomes are accepted")
        if self.aggregation != "daily" or not self.source.strip():
            raise ValueError("a daily aggregate and a named observation source are required")
        if self.statistic is not None and self.statistic != STATISTICS[self.variable]:
            raise ValueError("observation statistic must match the forecast's daily maximum, mean or sum")
        if valid > available or available > now:
            raise ValueError("the aggregate must have ended and the observation must be available")
        if valid.time() != datetime.min.time():
            raise ValueError("daily UTC aggregates must end at midnight UTC")


class WeatherFeedback:
    def __init__(self, ledger: LedgerStore):
        self.ledger = ledger

    def correction(self, port: str, variable: str, provider: str, horizon: int,
                   issued_at: datetime) -> dict[str, Any]:
        """A median residual must improve on a later chronological validation block.

        Multiple snapshots for one target are one sample, so hourly refreshes
        cannot create the appearance of months of independent observations.
        """
        records = self.ledger.predictions(domain=DOMAIN_WEATHER, subject=port, status=RESOLVED)
        unique: dict[str, PredictionRecord] = {}
        eligible = []
        for row in records:
            if (row.target != variable or row.model != provider or row.observed_value is None
                    or row.predicted_value is None or not row.observed_at
                    or instant(row.observed_at) >= issued_at or instant(row.valid_at) >= issued_at
                    or row.context.extra.get("horizonDays") != horizon
                    or row.context.season != season(issued_at)):
                continue
            eligible.append(row)
        # Never pool station residuals with gridded reanalysis residuals.
        source = next((r.observation_source for r in reversed(sorted(eligible,key=lambda r:r.observed_at))
                       if r.observation_source == "reanalysis: Open-Meteo ERA5 archive"),None)
        source = source or (max(eligible,key=lambda r:r.observed_at).observation_source if eligible else None)
        for row in eligible:
            if row.observation_source != source: continue
            previous = unique.get(row.valid_at)
            if previous is None or instant(row.issued_at) > instant(previous.issued_at):
                unique[row.valid_at] = row
        rows = sorted(unique.values(), key=lambda row: instant(row.valid_at))
        result = {"status": "COLLECTING", "sampleCount": len(rows), "bias": 0.0,
                  "lowerResidual": None, "upperResidual": None, "validationRawMae": None,
                  "validationCorrectedMae": None, "version": MODEL_VERSION, "outcomeSource":source,
                  "decisionEligible":False, "evaluationRawMae":None,"evaluationCorrectedMae":None,
                  "reason": f"Need {MIN_SAMPLES} independent resolved targets in this port, variable, provider, horizon and season."}
        if len(rows) < MIN_SAMPLES:
            return result
        block = len(rows) // 4
        validation_start = min(instant(r.issued_at) for r in rows[block:2*block])
        calibration_start = min(instant(r.issued_at) for r in rows[2*block:])
        train = [r for r in rows[:block] if instant(r.observed_at) < validation_start]
        validation = [r for r in rows[block:2*block] if instant(r.observed_at) < calibration_start]
        evaluation_start = min(instant(r.issued_at) for r in rows[3*block:])
        calibration = [r for r in rows[2*block:3*block] if instant(r.observed_at) < evaluation_start]
        evaluation = rows[3*block:]
        result["partitions"] = {"fitting": len(train), "validation": len(validation),
            "calibration": len(calibration), "evaluation":len(evaluation),
            "purged": len(rows)-len(train)-len(validation)-len(calibration)-len(evaluation),
            "validationFrom": validation_start.isoformat(), "calibrationFrom": calibration_start.isoformat(),
            "evaluationFrom":evaluation_start.isoformat()}
        if min(len(train), len(validation), len(calibration),len(evaluation)) < MIN_VALIDATION:
            result["reason"] = "Need eight independent targets in fitting, validation, calibration and subsequent evaluation after availability purging."
            return result
        bias = float(np.median([row.observed_value - row.predicted_value for row in train]))
        raw_mae = float(np.mean([abs(row.observed_value - row.predicted_value) for row in validation]))
        corrected_mae = float(np.mean([abs(row.observed_value - max(0, row.predicted_value + bias)) for row in validation]))
        result.update(validationRawMae=raw_mae, validationCorrectedMae=corrected_mae)
        if corrected_mae >= raw_mae * 0.98:
            result.update(status="REJECTED", reason="The residual correction did not improve chronological validation MAE by at least 2%.")
            return result
        # Selection uses validation only. An independent later block calibrates
        # the fixed correction, with a finite-sample conformal residual radius.
        residuals = [abs(r.observed_value - max(0, r.predicted_value + bias)) for r in calibration]
        rank = min(len(residuals), int(np.ceil((len(residuals)+1)*0.8)))
        radius = float(sorted(residuals)[rank-1])
        evaluation_raw=float(np.mean([abs(r.observed_value-r.predicted_value) for r in evaluation]))
        evaluation_corrected=float(np.mean([abs(r.observed_value-max(0,r.predicted_value+bias)) for r in evaluation]))
        result.update(evaluationRawMae=evaluation_raw,evaluationCorrectedMae=evaluation_corrected)
        if evaluation_corrected >= evaluation_raw*0.98:
            result.update(status="REJECTED",reason="Selected correction did not improve the subsequent chronological evaluation block by at least 2%.")
            return result
        version_id=_stable_id("wx-correction",port,variable,provider,horizon,source,
            *[r.prediction_id for r in (*train,*validation,*calibration,*evaluation)])
        result.update(status="VALIDATED", bias=bias, decisionEligible=True, modelId=version_id,
                      effectiveFrom=issued_at.isoformat(), evaluationKind="chronological replay of archived raw forecasts",
                      targetIds={"fitting":[r.prediction_id for r in train],"validation":[r.prediction_id for r in validation],
                                 "calibration":[r.prediction_id for r in calibration],"evaluation":[r.prediction_id for r in evaluation]},
                      lowerResidual=-radius, upperResidual=radius,
                      reason="Availability-purged fitting, validation and calibration precede an independent subsequent evaluation. Daily aggregate correction only; hourly approach gates remain raw. Nominal 80% coverage is not a future guarantee.")
        return result

    def record_frame(self, frame: pd.DataFrame, *, issued_at: datetime, provider: str,
                     source_state: str, variables: tuple[str, ...] | None = None,
                     now: datetime | None = None, provenance: dict | None = None) -> pd.DataFrame:
        """Persist raw values before applying corrections to future daily rows."""
        issued_at = instant(issued_at)
        now = instant(now or world_now())
        if issued_at > now:
            raise ValueError("a forecast cannot be retrieved in the future")
        out = frame.copy()
        variables = variables or tuple(VARIABLES)
        for index, row in out.iterrows():
            day = pd.Timestamp(row[DATE]).to_pydatetime().replace(tzinfo=timezone.utc)
            # Today is an unfinished daily aggregate. Do not snapshot it as a
            # completed observation or train a correction against it.
            if day.date() <= max(issued_at.date(), now.date()):
                continue
            port = port_registry.resolve(str(row[PORT_ID]))
            code = port.locode if port else str(row[PORT_ID]).upper()
            horizon = (day.date() - issued_at.date()).days
            valid_at = (day + timedelta(days=1)).isoformat()
            for variable in variables:
                value = row.get(variable)
                if value is None or not pd.notna(value) or not np.isfinite(float(value)):
                    continue
                prediction_id = _stable_id("wx", code, variable, provider, issued_at.isoformat(), valid_at)
                existing = self.ledger.get_prediction(prediction_id)
                if existing is not None:
                    out.at[index, variable] = existing.context.extra.get("correctedValue", existing.predicted_value)
                    continue
                learned = self.correction(code, variable, provider, horizon, issued_at)
                if learned.get("modelId") and hasattr(self.ledger,"path"):
                    from src.portwatch_os.learning.weather_reconciliation import WeatherEvidenceStore
                    evidence=WeatherEvidenceStore(self.ledger.path)
                    try:
                        with evidence.conn:
                            import json
                            evidence.conn.execute("INSERT OR IGNORE INTO weather_correction_versions(id,cohort,body) VALUES (?,?,?)",
                                (learned["modelId"],json.dumps([code,variable,provider,horizon,learned.get("outcomeSource")]),json.dumps(learned)))
                    finally: evidence.close()
                corrected = max(0.0, float(value) + learned["bias"])
                low = max(0.0, corrected + learned["lowerResidual"]) if learned["lowerResidual"] is not None else None
                high = max(corrected, corrected + learned["upperResidual"]) if learned["upperResidual"] is not None else None
                record = PredictionRecord(
                    prediction_id=prediction_id, domain=DOMAIN_WEATHER, kind=CONTINUOUS,
                    target=variable, subject=code, model=provider, model_version=MODEL_VERSION,
                    issued_at=issued_at.isoformat(), valid_at=valid_at,
                    predicted_value=float(value), context=PredictionContext(
                        port_code=code, horizon_hours=(day-issued_at).total_seconds()/3600,
                        season=season(issued_at), source_state=source_state,
                        extra={"unit": VARIABLES[variable], "horizonDays": horizon,
                               "targetDate": day.date().isoformat(), "aggregation": "daily", "statistic":STATISTICS[variable],
                               "correctedValue": corrected, "correctedLow": low, "correctedHigh": high,
                               "correction": learned}),
                    provenance={"provider": provider, "issueTimeBasis": "response_retrieved_at",
                                "providerRunTime": None, "state": source_state, **(provenance or {})},
                )
                self.ledger.record_prediction(record)
                out.at[index, variable] = corrected
        return out

    def observe(self, observation: WeatherObservation, *, now: datetime | None = None, prediction_ids: set | None = None) -> int:
        now = instant(now or world_now())
        observation.validate(now)
        resolved = 0
        for row in self.ledger.predictions(domain=DOMAIN_WEATHER, subject=observation.port_code.upper(), status=OPEN):
            if prediction_ids is not None and row.prediction_id not in prediction_ids: continue
            if row.target != observation.variable or instant(row.valid_at) != instant(observation.valid_at):
                continue
            if row.context.extra.get("unit") != observation.unit or row.context.extra.get("aggregation") != observation.aggregation:
                continue
            if instant(row.issued_at) >= instant(observation.valid_at):
                raise LedgerError("a weather prediction was issued after its target ended")
            error = observation.value - row.predicted_value
            self.ledger.resolve_prediction(row.prediction_id, observation.value, observation.available_at,
                                           f"{observation.kind}: {observation.source}",
                                           metrics={"error": error, "absolute_error": abs(error)})
            resolved += 1
        return resolved

    def resolve_reanalysis(self, frame: pd.DataFrame, *, available_at: datetime, now: datetime | None = None) -> int:
        count = 0
        for row in frame.itertuples(index=False):
            port = port_registry.resolve(str(getattr(row, PORT_ID)))
            code = port.locode if port else str(getattr(row, PORT_ID)).upper()
            valid = pd.Timestamp(getattr(row, DATE)).to_pydatetime().replace(tzinfo=timezone.utc) + timedelta(days=1)
            if valid > available_at:
                continue
            for variable in ("wind_speed", "wind_gust", "rainfall"):
                value = getattr(row, variable, None)
                if value is None or not pd.notna(value):
                    continue
                count += self.observe(WeatherObservation(code, variable, valid.isoformat(),
                    available_at.isoformat(), float(value), "Open-Meteo ERA5 archive",
                    "reanalysis", VARIABLES[variable]), now=now)
        return count

    def report(self, port_code: str | None = None, *, limit: int = 100,
               now: datetime | None = None, variable: str | None = None,
               public_only: bool = False, prediction_id: str | None = None) -> dict[str, Any]:
        now = instant(now or world_now())
        rows = [r for r in self.ledger.predictions(domain=DOMAIN_WEATHER, subject=port_code)
                if instant(r.issued_at) <= now and (not public_only or r.model in ("Open-Meteo surface", "Open-Meteo marine"))]
        resolved = [r for r in rows if r.status == RESOLVED and r.observed_at and instant(r.observed_at) <= now
                    and (not public_only or r.observation_source == "reanalysis: Open-Meteo ERA5 archive")]
        visible_resolved = {r.prediction_id for r in resolved}
        cells: dict[tuple, list[PredictionRecord]] = {}
        for row in resolved:
            cells.setdefault((row.subject, row.target, row.model, row.context.extra.get("horizonDays"),row.observation_source), []).append(row)
        scores = []
        for (port, target, provider, horizon,source), snapshots in sorted(cells.items()):
            unique={}
            for r in sorted(snapshots,key=lambda r:r.issued_at): unique[r.valid_at]=r
            cell=list(unique.values())
            scores.append({"portCode": port, "variable": target, "provider": provider,
                           "horizonDays": horizon, "unit": VARIABLES.get(target), "samples": len(cell),
                           "independentTargets":len(cell),"forecastSnapshots":len(snapshots),"outcomeSource":source,
                           "rawMae": float(np.mean([abs(r.observed_value-r.predicted_value) for r in cell])),
                           "correctedMae": float(np.mean([abs(r.observed_value-r.context.extra.get("correctedValue", r.predicted_value)) for r in cell])),
                           "rawBias": float(np.mean([r.observed_value-r.predicted_value for r in cell])),
                           "correctedBias": float(np.mean([r.observed_value-r.context.extra.get("correctedValue", r.predicted_value) for r in cell]))})
        inspections = []
        matching = [r for r in rows if (variable is None or r.target == variable) and (prediction_id is None or r.prediction_id==prediction_id)]
        for row in sorted(matching, key=lambda r: (instant(r.issued_at), r.prediction_id), reverse=True)[:limit]:
            known = row.prediction_id in visible_resolved
            extra = row.context.extra
            inspections.append({"id": row.prediction_id, "portCode": row.subject, "variable": row.target,
                "provider": row.model, "issuedAt": row.issued_at, "validAt": row.valid_at,
                "targetDate": extra.get("targetDate"), "horizonDays": extra.get("horizonDays"),
                "unit": extra.get("unit"), "original": row.predicted_value,
                "corrected": extra.get("correctedValue", row.predicted_value),
                "low": extra.get("correctedLow"), "high": extra.get("correctedHigh"),
                "observed": row.observed_value if known else None,
                "observedAt": row.observed_at if known else None, "statistic":extra.get("statistic",STATISTICS[row.target]),
                "rawError":row.predicted_value-row.observed_value if known else None,
                "correctedError":extra.get("correctedValue",row.predicted_value)-row.observed_value if known else None,
                "observationSource": row.observation_source if known else None,
                "status": RESOLVED if known else OPEN,
                "correction": extra.get("correction", {}), "provenance": row.provenance})
        return {"asOf": now.isoformat(), "total": len(rows), "resolved": len(resolved),
                "independentTargets":len({(r.subject,r.target,r.valid_at) for r in rows}),
                "independentResolvedTargets":len({(r.subject,r.target,r.valid_at,r.observation_source) for r in resolved}),
                "pending": len(rows)-len(resolved), "scores": scores, "forecasts": inspections,
                "forecastVariable": variable, "matchingForecasts": len(matching), "limit": limit,
                "method": "supervised residual correction with chronological validation",
                "note": "API backfill is not ground truth. ERA5 is labelled reanalysis; port station and operator measurements are accepted separately. No correction is learned from a newer forecast."}
