"""Evidence-qualified daily weather errors and chronological shadow corrections.

This is read-only research.  A successful replay never enables consumption by an
hourly approach calculation or promotes a correction into a shipping decision.
Error is consistently ``forecast - outcome``; the fitted adjustment has the
opposite sign and reuses the existing median-residual baseline.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime, timedelta
import hashlib
import json
import math
from pathlib import Path
import re
from statistics import median
from typing import Any

from src.portwatch_os.learning.weather_feedback import (
    MIN_SAMPLES, MIN_VALIDATION, MODEL_VERSION, STATISTICS, VARIABLES, instant, season,
)
from src.portwatch_os.learning.weather_reconciliation import sampling_window
from src.portwatch_os.ledger.schema import DOMAIN_WEATHER, RESOLVED
from src.utils import port_registry

VERSION = "weather-shadow-v1"
SELECTION_POLICY_ID = "latest-prospective-exact-context-v1"
CRITERIA_ID = "daily-residual-chronological-4block-strict-2pct-v1"
PUBLIC_PROVIDERS = ("Open-Meteo surface", "Open-Meteo marine")
FIELDS = {"wind_speed": ("wind_speed_10m", "kn"), "wind_gust": ("wind_gusts_10m", "kn"),
          "rainfall": ("precipitation", "mm"), "wave_height": ("wave_height", "m"),
          "visibility": ("visibility", "m")}
ADOPTION_CRITERIA = {
    "minimumIndependentTargets": MIN_SAMPLES,
    "minimumPerPartitionAfterAvailabilityPurging": MIN_VALIDATION,
    "validationMinimumRelativeMaeImprovement": 0.02,
    "subsequentEvaluationMinimumRelativeMaeImprovement": 0.02,
    "improvementComparison": "strictly_greater_than_2_percent; equality_is_rejected",
    "nominalCalibrationCoverage": 0.8,
    "samePortVariableProviderHorizonSeasonSourceUnitStatisticAndLocation": True,
    "intactCompleteOriginalAndOutcomeEvidenceRequired": True,
    "outcomesMustPrecedeNextPartitionForecastReceipt": True,
    "explicitAdoptionReviewRequired": True,
    "prospectiveShadowResultsRequired": True,
    "minimumProspectiveIndependentTargets": 8,
    "prospectiveMinimumRelativeMaeImprovement": 0.02,
    "candidateVersionMustBeFrozenBeforeProspectiveForecastReceiptAndTarget": True,
    "explicitScopedAdoptionRecordRequired": True,
    "dailyOnly": True,
    "hourlyApproachCalculationsRemainRaw": True,
}
ADOPTION_CRITERIA_TEXT = [
    "At least 32 independent matched daily targets in the same port, variable, provider, horizon, season, outcome source, unit, statistic and location.",
    "At least eight targets remain in each fitting, validation, calibration and subsequent evaluation block after outcome-availability purging; 32 targets alone may be insufficient.",
    "Fit only the median outcome-minus-raw residual on fitting targets; validation and subsequent evaluation MAE must each improve by strictly more than 2% against their raw forecasts.",
    "Use the independent calibration block for the nominal 80% residual interval; inspect held-out coverage without treating it as a future guarantee.",
    "Require at least eight genuinely prospective independent shadow targets with the same candidate version frozen before their forecast receipts and targets, and before any outcome is available; prospective MAE must improve by strictly more than 2% against raw forecasts.",
    "Review prospective interval coverage and limitations, then record an explicit adoption decision scoped to this daily context and correction version. This report cannot adopt a candidate.",
    "Any future adoption applies to daily research values only. Hourly gust, visibility and approach calculations retain their original inputs.",
]


class QualificationError(ValueError):
    pass


def _number(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def _same(a, b):
    return _number(a) and _number(b) and math.isclose(float(a), float(b), rel_tol=1e-8, abs_tol=1e-8)


def _location(value):
    if not isinstance(value, dict) or not all(_number(value.get(k)) for k in ("lat", "lon")):
        raise QualificationError("missing_or_invalid_location")
    if not -90 <= value["lat"] <= 90 or not -180 <= value["lon"] <= 180:
        raise QualificationError("missing_or_invalid_location")
    return {k: float(value[k]) for k in ("lat", "lon")}


def _near(a, b, maximum_km=50):
    lat1, lat2 = math.radians(a["lat"]), math.radians(b["lat"])
    dlat = lat2-lat1
    dlon = math.radians(b["lon"]-a["lon"])
    h = math.sin(dlat/2)**2 + math.cos(lat1)*math.cos(lat2)*math.sin(dlon/2)**2
    return 6371*2*math.asin(min(1, math.sqrt(h))) <= maximum_km


def _digest_id(prefix, value):
    return prefix+"-"+hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()[:24]


def _metrics(rows, adjustment=0.0, radius=None):
    errors = [max(0.0, r["raw"]+adjustment)-r["outcome"] for r in rows]
    count = len(errors)
    if not count:
        return {"count": 0, "bias": None, "mae": None, "rmse": None,
                "underpredictions": 0, "overpredictions": 0, "exact": 0}
    out = {"count": count, "bias": sum(errors)/count,
           "mae": sum(abs(e) for e in errors)/count,
           "rmse": math.sqrt(sum(e*e for e in errors)/count),
           "underpredictions": sum(e < -1e-8 for e in errors),
           "overpredictions": sum(e > 1e-8 for e in errors),
           "exact": sum(abs(e) <= 1e-8 for e in errors)}
    if radius is not None:
        out["intervalCoverage"] = sum(abs(e) <= radius+1e-8 for e in errors)/count
        out["nominalCoverage"] = 0.8
    return out


def chronological_partitions(rows):
    """Four ordered blocks, with unavailable labels purged at each next origin.

    Boundaries are frozen from all rows of the next nominal block before
    purging. Purged rows are never moved to another block to fill a shortfall.
    This is the existing residual baseline's availability-aware split.
    """
    rows = sorted(rows, key=lambda r: (instant(r["validAt"]), r["predictionId"]))
    block = len(rows)//4
    proposed = {"fitting": rows[:block], "validation": rows[block:2*block],
                "calibration": rows[2*block:3*block], "evaluation": rows[3*block:]}
    boundaries = {
        "fitting": min((instant(r["issuedAt"]) for r in proposed["validation"]), default=None),
        "validation": min((instant(r["issuedAt"]) for r in rows[2*block:]), default=None),
        "calibration": min((instant(r["issuedAt"]) for r in proposed["evaluation"]), default=None),
    }
    partitions, purged = {}, []
    for name, candidates in proposed.items():
        boundary = boundaries.get(name)
        partitions[name] = []
        for row in candidates:
            if boundary is not None and instant(row["availableAt"]) >= boundary:
                purged.append({"predictionId": row["predictionId"], "targetId": row["targetId"],
                               "partition": name, "availableAt": row["availableAt"],
                               "nextPartitionOrigin": boundary.isoformat(),
                               "reason": "outcome_not_available_before_next_partition_forecast"})
            else:
                partitions[name].append(row)
    return partitions, purged, {name: value.isoformat() if value else None for name, value in boundaries.items()}


def evaluate_shadow(rows, *, context=None, as_of=None):
    """Use fitting for bias, validation for selection, calibration for radius.

    Subsequent evaluation is never reused to refit or select an alternative.
    A later evaluation failure rejects this frozen candidate.
    """
    partitions, purged, boundaries = chronological_partitions(rows)
    counts = {name: len(values) for name, values in partitions.items()}
    shortfalls = {name: max(0, MIN_VALIDATION-count) for name, count in counts.items()}
    ready = len(rows) >= MIN_SAMPLES and not any(shortfalls.values())
    reasons = []
    if len(rows) < MIN_SAMPLES:
        reasons.append(f"Need {MIN_SAMPLES} independent targets in this exact context; {len(rows)} retained.")
    if any(shortfalls.values()):
        reasons.append("Need eight independent targets in each chronological block after outcome-availability purging.")
    readiness = {"status": "READY_FOR_CHRONOLOGICAL_SHADOW" if ready else "COLLECTING",
                 "minimumIndependentTargets": MIN_SAMPLES, "minimumPerPartition": MIN_VALIDATION,
                 "independentTargetShortfall": max(0, MIN_SAMPLES-len(rows)),
                 "partitions": counts, "purged": len(purged), "purgedTargets": purged,
                 "partitionBoundaries": boundaries, "partitionShortfalls": shortfalls,
                 "shortfalls": shortfalls,
                 "targetIds": {name: [r["targetId"] for r in values] for name, values in partitions.items()},
                 "predictionIds": {name: [r["predictionId"] for r in values] for name, values in partitions.items()},
                 "reasons": reasons}
    result = {"status": "COLLECTING", "mode": "SHADOW_ONLY", "decisionEligible": False,
              "baselineVersion": MODEL_VERSION, "analysisVersion": VERSION,
              "biasAdjustment": None, "correctionId": None,
              "validation": None, "calibration": None, "evaluation": None,
              "adoptionCriteria": dict(ADOPTION_CRITERIA),
              "adoptionCriteriaText": list(ADOPTION_CRITERIA_TEXT),
              "reason": " ".join(reasons) if reasons else "Chronological replay pending."}
    if not ready:
        return readiness, result
    train, validation, calibration, evaluation = (partitions[k] for k in ("fitting", "validation", "calibration", "evaluation"))
    adjustment = float(median(r["outcome"]-r["raw"] for r in train))
    val_raw, val_corrected = _metrics(validation), _metrics(validation, adjustment)
    # Strict less-than matches the baseline: zero raw error cannot be improved.
    validation_pass = val_corrected["mae"] < val_raw["mae"]*0.98
    residuals = sorted(abs(max(0.0, r["raw"]+adjustment)-r["outcome"]) for r in calibration)
    rank = min(len(residuals), math.ceil((len(residuals)+1)*0.8))
    radius = residuals[rank-1]
    eval_raw, eval_corrected = _metrics(evaluation), _metrics(evaluation, adjustment, radius)
    evaluation_pass = eval_corrected["mae"] < eval_raw["mae"]*0.98
    identity = {"version": VERSION, "baselineVersion": MODEL_VERSION, "criteriaId": CRITERIA_ID,
                "selectionPolicyId": SELECTION_POLICY_ID, "context": context,
                "targets": {name: [{k: r[k] for k in ("targetId", "predictionId", "forecastResponseSha256", "outcomeResponseSha256")}
                                   for r in values] for name, values in partitions.items()}}
    result.update(status="SHADOW_VALIDATED" if validation_pass and evaluation_pass else "REJECTED",
                  biasAdjustment=adjustment, correctionId=_digest_id("wx-shadow", identity),
                  effectiveFrom=as_of, targetIds=readiness["targetIds"], predictionIds=readiness["predictionIds"],
                  evidence=identity["targets"],
                  validation={"raw": val_raw, "corrected": val_corrected, "passes": validation_pass},
                  calibration={"count": len(calibration), "residualRadius": radius, "nominalCoverage": 0.8,
                               "method": "finite-sample conformal absolute residual rank; no bias refit"},
                  evaluation={"raw": eval_raw, "corrected": eval_corrected, "passes": evaluation_pass,
                              "role": "subsequent held-out chronological replay; never used for fitting"},
                  reason=("Daily correction passed the fixed chronological replay thresholds. Explicit adoption review and further prospective evidence remain required; this result is shadow only."
                          if validation_pass and evaluation_pass else
                          "The fixed correction failed the 2% validation improvement threshold." if not validation_pass else
                          "The selected correction failed the 2% subsequent evaluation improvement threshold."))
    return readiness, result


class WeatherShadowAnalysis:
    def __init__(self, ledger, evidence, root):
        self.ledger, self.evidence, self.root = ledger, evidence, Path(root)
        self._responses = {}

    def _response(self, folder, digest):
        key = (folder, digest)
        if key in self._responses:
            return self._responses[key]
        if not isinstance(digest, str) or not re.fullmatch("[a-f0-9]{64}", digest):
            raise QualificationError("missing_original_response_hash")
        path = self.root/folder/(digest+".response")
        if not path.is_file():
            raise QualificationError("original_response_unavailable")
        raw = path.read_bytes()
        if hashlib.sha256(raw).hexdigest() != digest:
            raise QualificationError("original_response_hash_mismatch")
        try:
            body = json.loads(raw)
        except (ValueError, UnicodeDecodeError):
            raise QualificationError("unsupported_original_response_shape") from None
        if not isinstance(body, dict):
            raise QualificationError("unsupported_original_response_shape")
        self._responses[key] = body
        return body

    def _aggregate(self, body, day, variable):
        if not isinstance(body, dict) or body.get("utc_offset_seconds") != 0:
            raise QualificationError("unsupported_original_response_shape_or_timezone")
        field, unit = FIELDS[variable]
        units = body.get("hourly_units")
        if not isinstance(units, dict) or units.get(field) != unit:
            raise QualificationError("original_response_units_mismatch")
        hourly = body.get("hourly", {})
        if not isinstance(hourly, dict):
            raise QualificationError("unsupported_original_hourly_shape")
        times, values = hourly.get("time", []), hourly.get(field, [])
        if not isinstance(times, list) or not isinstance(values, list) or len(times) != len(values):
            raise QualificationError("incomplete_original_daily_aggregate")
        samples = []
        for at, value in zip(times, values):
            if not isinstance(at, str) or at[:10] != day:
                continue
            try:
                moment = instant(at+"+00:00" if len(at) == 16 else at)
            except (ValueError, TypeError):
                raise QualificationError("invalid_original_hour_time") from None
            samples.append((moment, value))
        start = instant(day+"T00:00:00+00:00")
        expected = {start+timedelta(hours=h) for h in range(24)}
        if len(samples) != 24 or {at for at, value in samples} != expected or any(not _number(value) or value < 0 for at, value in samples):
            raise QualificationError("incomplete_original_daily_aggregate")
        data = [float(value) for at, value in samples]
        return sum(data) if variable == "rainfall" else sum(data)/24/1000 if variable == "visibility" else max(data)

    def _forecast_receipt(self, annotation, row):
        products = {"Open-Meteo surface": ("surface", "https://api.open-meteo.com/v1/forecast",
                                          {"wind_speed", "wind_gust", "rainfall", "visibility"}),
                    "Open-Meteo marine": ("marine", "https://marine-api.open-meteo.com/v1/marine", {"wave_height"})}
        kind, source, variables = products[row.model]
        if row.target not in variables:
            raise QualificationError("forecast_provider_product_variable_mismatch")
        snapshot_id = annotation.get("snapshotId")
        if not isinstance(snapshot_id, str) or not re.fullmatch("[a-f0-9]{64}", snapshot_id):
            raise QualificationError("retained_forecast_receipt_unavailable")
        key = ("receipt", snapshot_id)
        if key not in self._responses:
            path = self.root/"archive"/(snapshot_id+".json")
            if not path.is_file():
                raise QualificationError("retained_forecast_receipt_unavailable")
            try:
                self._responses[key] = json.loads(path.read_text(encoding="utf-8"))
            except (ValueError, UnicodeDecodeError):
                raise QualificationError("invalid_forecast_receipt") from None
        receipt = self._responses[key]
        if not isinstance(receipt, dict):
            raise QualificationError("invalid_forecast_receipt")
        receipt_hash = hashlib.sha256(json.dumps({k: v for k, v in receipt.items() if k != "snapshotId"}, sort_keys=True).encode()).hexdigest()
        if receipt_hash != snapshot_id:
            raise QualificationError("forecast_receipt_hash_mismatch")
        if receipt.get("kind") != kind or ("source" in receipt and receipt["source"] != source):
            raise QualificationError("forecast_provider_product_source_mismatch")
        if (receipt.get("snapshotId") != snapshot_id or receipt.get("availableAt") != row.issued_at
                or receipt.get("portCode") != row.subject
                or receipt.get("responseSha256") != annotation.get("responseSha256")):
            raise QualificationError("forecast_receipt_identity_or_origin_mismatch")
        if row.provenance.get("snapshotId") not in (None, snapshot_id):
            raise QualificationError("forecast_receipt_identity_or_origin_mismatch")

    def _qualify(self, row, outcome, now):
        extra = row.context.extra
        annotation = self.evidence.get("weather_forecast_annotations", row.prediction_id) or {}
        if not isinstance(annotation, dict):
            raise QualificationError("complete_forecast_annotation_unavailable")
        if not annotation.get("complete") or annotation.get("completeHours") != 24:
            raise QualificationError("complete_forecast_annotation_unavailable")
        statistic = extra.get("statistic", STATISTICS.get(row.target))
        if row.target not in VARIABLES or extra.get("unit") != VARIABLES[row.target] or statistic != STATISTICS[row.target]:
            raise QualificationError("forecast_unit_or_statistic_mismatch")
        day = extra.get("targetDate")
        try:
            start, end = instant(day+"T00:00:00+00:00"), instant(row.valid_at)
            issued, available = instant(row.issued_at), instant(row.observed_at)
        except (TypeError, ValueError):
            raise QualificationError("invalid_target_or_availability_time") from None
        if end != start+timedelta(days=1) or issued >= start or available < end or issued > now or available > now:
            raise QualificationError("invalid_or_unavailable_forecast_outcome_chronology")
        if issued >= instant(sampling_window(day, row.target)["from"]):
            raise QualificationError("forecast_not_prospective_for_measurement_window")
        horizon = extra.get("horizonDays")
        if isinstance(horizon, bool) or not isinstance(horizon, int) or horizon < 1 or horizon != (start.date()-issued.date()).days:
            raise QualificationError("forecast_horizon_mismatch")
        if row.context.season != season(issued):
            raise QualificationError("forecast_season_mismatch")
        if extra.get("aggregation") != "daily" or annotation.get("aggregation") != "daily UTC":
            raise QualificationError("forecast_aggregation_mismatch")
        if (annotation.get("targetStart") != start.isoformat() or annotation.get("targetEnd") != end.isoformat()
                or annotation.get("statistic") != STATISTICS[row.target]
                or annotation.get("measurementWindow", sampling_window(day, row.target)) != sampling_window(day, row.target)):
            raise QualificationError("forecast_target_window_mismatch")
        if not outcome:
            raise QualificationError("retained_outcome_evidence_unavailable")
        if (outcome.get("portCode") != row.subject or outcome.get("variable") != row.target
                or outcome.get("unit") != extra["unit"] or outcome.get("statistic") != statistic
                or outcome.get("aggregation") != "daily UTC" or outcome.get("completeHours") != 24
                or outcome.get("targetStart") != start.isoformat() or outcome.get("validAt") != end.isoformat()
                or outcome.get("measurementWindow") != sampling_window(day, row.target)):
            raise QualificationError("outcome_target_unit_or_window_mismatch")
        if (outcome.get("kind") not in ("station", "operator_measurement", "reanalysis")
                or row.observation_source != outcome.get("kind", "")+": "+outcome.get("source", "")
                or outcome.get("availableAt") != available.isoformat()
                or not _same(outcome.get("value"), row.observed_value)):
            raise QualificationError("outcome_source_or_availability_mismatch")
        if outcome.get("kind") != "reanalysis" or outcome.get("source") != "Open-Meteo ERA5 archive":
            raise QualificationError("outcome_adapter_not_qualified_for_shadow")
        request = outcome.get("request")
        if (outcome.get("url") != "https://archive-api.open-meteo.com/v1/archive"
                or outcome.get("model") != "era5" or not isinstance(request, dict) or request.get("models") != "era5"):
            raise QualificationError("reanalysis_source_model_provenance_mismatch")
        forecast_location = _location(annotation.get("requestLocation"))
        requested = _location(outcome.get("requestedLocation"))
        location = _location(outcome.get("location"))
        port = port_registry.resolve(row.subject)
        if (not port or not _near(forecast_location, {"lat": port.lat, "lon": port.lon})
                or not all(_same(forecast_location[k], requested[k]) for k in ("lat", "lon"))
                or not _near(requested, location)):
            raise QualificationError("outcome_location_mismatch")
        forecast_hash, outcome_hash = annotation.get("responseSha256"), outcome.get("responseSha256")
        self._forecast_receipt(annotation, row)
        if row.provenance.get("responseSha256") not in (None, forecast_hash):
            raise QualificationError("forecast_provenance_hash_mismatch")
        forecast_body = self._response("archive", forecast_hash)
        outcome_body = self._response("outcomes", outcome_hash)
        forecast_grid = _location({"lat": forecast_body.get("latitude"), "lon": forecast_body.get("longitude")})
        outcome_grid = _location({"lat": outcome_body.get("latitude"), "lon": outcome_body.get("longitude")})
        if (not _near(forecast_location, forecast_grid)
                or not all(_same(outcome_grid[k], location[k]) for k in ("lat", "lon"))):
            raise QualificationError("original_response_location_mismatch")
        # This currently supports the retained Open-Meteo hourly response shape.
        # A new station adapter must supply its own explicit shape validation.
        if not _same(self._aggregate(forecast_body, day, row.target), row.predicted_value):
            raise QualificationError("original_forecast_value_mismatch")
        if not _same(self._aggregate(outcome_body, day, row.target), row.observed_value):
            raise QualificationError("original_outcome_value_mismatch")
        context = {"portCode": row.subject, "variable": row.target, "provider": row.model,
                   "horizonDays": horizon, "outcomeSource": row.observation_source,
                   "outcomeKind": outcome["kind"], "season": row.context.season,
                   "unit": extra["unit"], "statistic": statistic, "aggregation": "daily UTC",
                   "requestedLocation": requested, "forecastLocation": forecast_grid, "outcomeLocation": location}
        target_identity = {k: context[k] for k in context if k not in ("provider", "horizonDays", "season", "forecastLocation")}
        target_identity["validAt"] = end.isoformat()
        return context, {"targetId": _digest_id("wx-target", target_identity), "predictionId": row.prediction_id,
                         "issuedAt": issued.isoformat(), "validAt": end.isoformat(), "targetDate": day,
                         "leadTimeHours": (start-issued).total_seconds()/3600,
                         "availableAt": available.isoformat(), "raw": float(row.predicted_value),
                         "outcome": float(row.observed_value), "error": row.predicted_value-row.observed_value,
                         "forecastResponseSha256": forecast_hash, "outcomeResponseSha256": outcome_hash,
                         "forecastSnapshotId": annotation.get("snapshotId"), "outcomeEvidenceId": outcome.get("id"),
                         "measurementWindow": sampling_window(day, row.target),
                         "statisticBasis": "frozen prediction context" if extra.get("statistic") else "derived from immutable variable and retained annotation; aggregate recomputed from retained response",
                         "forecastWindowBasis": "retained annotation" if annotation.get("measurementWindow") else "derived from immutable target date and variable; aggregate recomputed from retained response"}

    def report(self, *, now, port_code=None, variable=None, provider=None, horizon=None):
        now = instant(now)
        # Reusing an analysis object must still detect a source removed or
        # corrupted since its previous report. Cache only within this report.
        self._responses = {}
        # A report can be replayed as-of an earlier time without exposing labels
        # received later. First receipt and immutable retained outcome are used.
        outcomes = defaultdict(list)
        for outcome in self.evidence.outcomes():
            if not isinstance(outcome, dict):
                continue
            outcomes[(outcome.get("portCode"), outcome.get("variable"), outcome.get("validAt"))].append(outcome)
        visible, selected, exclusions = [], [], []
        unreadable_issue_times = 0
        for row in self.ledger.predictions(domain=DOMAIN_WEATHER, subject=port_code):
            if (row.model not in PUBLIC_PROVIDERS or (variable and row.target != variable)
                    or (provider and row.model != provider)
                    or (horizon is not None and row.context.extra.get("horizonDays") != horizon)):
                continue
            try:
                issued = instant(row.issued_at)
            except (ValueError, TypeError, AttributeError, OverflowError):
                # Visibility cannot be established. Keep row identity/values out
                # of an as-of public report, but expose a data-quality count.
                unreadable_issue_times += 1
                continue
            if issued > now:
                continue
            visible.append(row)
            if row.status != RESOLVED:
                continue
            try:
                if not row.observed_at:
                    raise ValueError("missing outcome availability")
                available = instant(row.observed_at)
            except (ValueError, TypeError, AttributeError, OverflowError):
                exclusions.append({"predictionId": row.prediction_id, "reason": "invalid_outcome_availability_timestamp"})
                continue
            if available <= now:
                selected.append(row)
        cells = {}
        for row in selected:
            try:
                matching = [o for o in outcomes.get((row.subject, row.target, row.valid_at), [])
                            if row.observation_source == o.get("kind", "")+": "+o.get("source", "")
                            and o.get("availableAt") == row.observed_at]
                if len(matching) > 1:
                    raise QualificationError("ambiguous_outcome_evidence")
                context, target = self._qualify(row, matching[0] if matching else None, now)
                key = json.dumps(context, sort_keys=True)
                cell = cells.setdefault(key, {"context": context, "snapshots": []})
                cell["snapshots"].append(target)
            except (QualificationError, ValueError, TypeError, KeyError, AttributeError, OverflowError) as exc:
                exclusions.append({"predictionId": row.prediction_id, "reason": str(exc)})
            except OSError:
                exclusions.append({"predictionId": row.prediction_id, "reason": "retained_source_temporarily_unavailable"})
        contexts = []
        all_target_ids = set()
        qualified = 0
        for key, cell in sorted(cells.items()):
            context, snapshots = cell["context"], cell["snapshots"]
            unique = {}
            # A fixed deterministic rule, unrelated to error size: take the last
            # prospective receipt in the declared calendar-day horizon. IDs break
            # ties. Other receipts remain frozen and do not add independent N.
            for target in sorted(snapshots, key=lambda r: (instant(r["issuedAt"]), r["predictionId"])):
                unique[target["targetId"]] = target
            targets = sorted(unique.values(), key=lambda r: (instant(r["validAt"]), r["predictionId"]))
            metrics = _metrics(targets)
            under, over = metrics["underpredictions"], metrics["overpredictions"]
            majority = max(under, over)
            direction = "UNDERPREDICTION" if under > over else "OVERPREDICTION" if over > under else "BALANCED_OR_EXACT"
            readiness, shadow = evaluate_shadow(targets, context=context, as_of=now.isoformat())
            contexts.append({**context, "id": _digest_id("wx-context", context),
                             "independentTargets": len(targets), "forecastSnapshots": len(snapshots),
                             "duplicateSnapshots": len(snapshots)-len(targets), "metrics": metrics,
                             "systematicMiss": {"direction": direction, "directionCount": majority,
                                                "share": majority/len(targets), "descriptiveOnly": True,
                                                "interpretation": "Observed sample direction only; no statistical significance or future-skill claim."},
                             "targetSpan": {"from": targets[0]["targetDate"], "through": targets[-1]["targetDate"],
                                            "distinctDates": len({r["targetDate"] for r in targets})},
                             "leadTimeHoursRange": {"minimum": min(r["leadTimeHours"] for r in targets),
                                                    "maximum": max(r["leadTimeHours"] for r in targets)},
                             "readiness": readiness, "shadow": shadow, "targets": targets})
            all_target_ids.update(unique)
            qualified += len(snapshots)
        exclusion_counts = Counter(r["reason"] for r in exclusions)
        report_id = _digest_id("wx-shadow-report", {"version": VERSION, "criteriaId": CRITERIA_ID,
            "selectionPolicyId": SELECTION_POLICY_ID, "asOf": now.isoformat(),
            "filters": [port_code, variable, provider, horizon],
            "contexts": [{"id": c["id"], "targets": c["targets"], "shadow": c["shadow"]} for c in contexts],
            "exclusions": sorted(exclusions, key=lambda r: r["predictionId"])})
        return {"asOf": now.isoformat(), "version": VERSION, "analysisVersion": VERSION,
                "reportId": report_id, "criteriaId": CRITERIA_ID, "selectionPolicyId": SELECTION_POLICY_ID,
                "mode": "SHADOW_ONLY", "decisionEligible": False,
                "errorConvention": "forecast_minus_outcome; negative = underprediction, positive = overprediction",
                "horizonDefinition": "Target calendar date minus original forecast response receipt date in UTC. Provider model-run time is unknown; exact receipt-to-target lead hours remain attached to each target.",
                "selectionPolicy": "Latest original prospective receipt within each exact context and target; prediction ID breaks equal-receipt ties. Selection never uses outcome error. Repeated refreshes do not increase independent targets.",
                "independenceMeaning": "A distinct port, variable, target window, outcome source/kind, unit/statistic and requested/observed location. Provider and horizon comparisons may share the same outcome and are not independent of each other.",
                "summary": {"resolvedSnapshots": len(selected), "qualifiedSnapshots": qualified,
                            "pendingSnapshots": len(visible)-len(selected),
                            "unreadableIssueTimestampSnapshots": unreadable_issue_times,
                            "independentTargets": len(all_target_ids), "excludedSnapshots": len(exclusions),
                            "cohortMemberships": sum(c["independentTargets"] for c in contexts),
                            "duplicateSnapshots": qualified-sum(c["independentTargets"] for c in contexts),
                            "targetDates": len({r["targetDate"] for c in contexts for r in c["targets"]}),
                            "contexts": len(contexts), "collectingContexts": sum(c["shadow"]["status"] == "COLLECTING" for c in contexts),
                            "shadowValidatedContexts": sum(c["shadow"]["status"] == "SHADOW_VALIDATED" for c in contexts),
                            "rejectedContexts": sum(c["shadow"]["status"] == "REJECTED" for c in contexts),
                            "exclusionReasons": dict(sorted(exclusion_counts.items()))},
                "contexts": contexts, "exclusions": exclusions, "adoptionCriteria": dict(ADOPTION_CRITERIA),
                "adoptionCriteriaText": list(ADOPTION_CRITERIA_TEXT),
                "scope": "Retained complete daily aggregates only. ERA5 is reanalysis, not a station observation. No hourly gust/visibility correction or model promotion occurs."}
