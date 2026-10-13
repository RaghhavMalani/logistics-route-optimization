"""Measured arrival waiting, with a fixed later holdout and separate calibration.

The congestion proxy and generated twin calls are deliberately not labels here.
Feature names and GBM settings are fixed before inspecting the final fold.
"""
from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path

import numpy as np
import sklearn
from sklearn.ensemble import GradientBoostingRegressor

FEATURES = ("baselineWaitHours", "wind_speed", "wind_gust", "rainfall", "wave_height", "visibility",
            "sogKnots", "trackAgeHours", "trackCount", "observedAnchoredVessels")
VERSION = "arrival-wait-gbm-v2"
MIN_ROWS = 60
WEATHER = ("wind_speed", "wind_gust", "rainfall", "wave_height", "visibility")
AIS = ("sogKnots", "trackAgeHours", "trackCount", "observedAnchoredVessels")
VARIANTS = {"scheduler_only_gbm": ("baselineWaitHours",),
            "scheduler_weather_gbm": ("baselineWaitHours",) + WEATHER,
            "scheduler_ais_gbm": ("baselineWaitHours",) + AIS,
            "gbm": FEATURES}


def hash_code():
    return hashlib.sha256(Path(__file__).read_bytes()).hexdigest()


def dependencies():
    return {"numpy": np.__version__, "scikit-learn": sklearn.__version__}


def digest(value) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def vector(features: dict, names=FEATURES) -> list[float]:
    # Missingness is consumed by the model, never disguised as a measured zero.
    return [float(features.get(k) or 0) for k in names] + [float(features.get(k) is None) for k in names]


def fit(rows: list[dict], names=FEATURES):
    model = GradientBoostingRegressor(n_estimators=40, max_depth=2, learning_rate=0.05,
                                     loss="absolute_error", random_state=168)
    model.fit([vector(r["features"], names) for r in rows], [r["waitHours"] for r in rows])
    return model


def radius(model, rows: list[dict]) -> float:
    errors = sorted(abs(r["waitHours"] - max(0, float(model.predict([vector(r["features"])])[0]))) for r in rows)
    index = min(len(errors) - 1, math.ceil((len(errors) + 1) * 0.8) - 1)
    return float(errors[index])


def calibrated_radius(points: list[float], rows: list[dict]) -> float:
    errors = sorted(abs(r["waitHours"] - p) for r, p in zip(rows, points))
    return float(errors[min(len(errors)-1, math.ceil((len(errors)+1)*0.8)-1)])


def partition(rows: list[dict]) -> tuple[list[dict], list[dict], list[dict]]:
    rows = sorted(rows, key=lambda r: (r["issuedAt"], r["operationId"]))
    a, b = int(len(rows) * 0.6), int(len(rows) * 0.8)
    if len(rows) < MIN_ROWS:
        raise ValueError(f"Need {MIN_ROWS} complete measured arrivals; have {len(rows)}")
    # Keep equal issue instants in the same partition.
    while a > 0 and rows[a-1]["issuedAt"] == rows[a]["issuedAt"]:
        a -= 1
    while b > a and rows[b-1]["issuedAt"] == rows[b]["issuedAt"]:
        b -= 1
    if a == 0 or b == a:
        raise ValueError("Need distinct chronological issue periods")
    cal_at, test_at = rows[a]["issuedAt"], rows[b]["issuedAt"]
    train = [r for r in rows[:a] if r["availableAt"] < cal_at and r["recordedAt"] < cal_at]
    calibration = [r for r in rows[a:b] if r["availableAt"] < test_at and r["recordedAt"] < test_at]
    test = rows[b:]
    if len(train) < 24 or len(calibration) < 10 or len(test) < 10:
        raise ValueError("After purging late/crossing outcomes, need 24 fit, 10 calibration and 10 holdout arrivals")
    return train, calibration, test


def evaluate(rows: list[dict], used_for_fitting: set[str]) -> dict:
    train, cal, test = partition(rows)
    if used_for_fitting.intersection(r["operationId"] for r in test):
        raise ValueError("Later holdout outcomes have already been used for fitting; collect a new untouched period")
    median = float(np.median([r["waitHours"] for r in train]))
    models = {key: fit(train, names) for key, names in VARIANTS.items()}
    def points(key, fold):
        if key == "scheduler":
            return [float(r["features"]["baselineWaitHours"]) for r in fold]
        if key == "historical_median":
            return [median] * len(fold)
        return [max(0, float(p)) for p in models[key].predict([vector(r["features"], VARIANTS[key]) for r in fold])]
    keys = [*VARIANTS, "scheduler", "historical_median"]
    cal_points = {key: points(key, cal) for key in keys}
    test_points = {key: points(key, test) for key in keys}
    widths = {key: calibrated_radius(cal_points[key], cal) for key in keys}
    metrics = {}
    for key in keys:
        errors = [r["waitHours"] - p for r, p in zip(test, test_points[key])]
        metrics[key] = {"maeHours": float(np.mean(np.abs(errors))),
                        "signedBiasHours": float(np.mean(errors)),
                        "intervalCoverage": float(np.mean([max(0, p-widths[key]) <= r["waitHours"] <= p+widths[key]
                                                           for r, p in zip(test, test_points[key])])),
                        "calibrationRadiusHours": widths[key], "intervalNominal": 0.8}
    width = widths["gbm"]
    predictions = []
    for index, row in enumerate(test):
        point = test_points["gbm"][index]
        low, high = max(0, point-width), point+width
        predictions.append({"operationId": row["operationId"], "issuedAt": row["issuedAt"],
                            "observed": row["waitHours"], "predicted": point, "low": low, "high": high,
                            "baseline": row["features"]["baselineWaitHours"], "historicalMedian": median,
                            "comparisons": {key: {"point": test_points[key][index],
                                "low": max(0, test_points[key][index]-widths[key]),
                                "high": test_points[key][index]+widths[key]} for key in keys}})
    mae = lambda key: float(np.mean([abs(r["observed"]-r[key]) for r in predictions]))
    gbm_mae, baseline_mae = mae("predicted"), mae("baseline")
    calibration_gbm_mae = float(np.mean([abs(r["waitHours"]-p) for r, p in zip(cal, cal_points["gbm"])]))
    calibration_baseline_mae = float(np.mean([abs(r["waitHours"]-r["features"]["baselineWaitHours"]) for r in cal]))
    return {"status": "EVALUATED", "modelVersion": VERSION, "target": "anchorage_wait_hours",
            "unit": "hours", "featureNames": list(FEATURES), "datasetHash": digest(rows),
            "codeHash": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            "dependencies": {"numpy": np.__version__, "scikit-learn": sklearn.__version__},
            "fitIds": [r["operationId"] for r in train], "calibrationIds": [r["operationId"] for r in cal],
            "holdoutIds": [r["operationId"] for r in test], "fitCount": len(train),
            "calibrationCount": len(cal), "holdoutCount": len(test),
            "fitThrough": train[-1]["issuedAt"], "calibrationFrom": cal[0]["issuedAt"],
            "calibrationThrough": cal[-1]["issuedAt"], "holdoutFrom": test[0]["issuedAt"],
            "holdoutThrough": test[-1]["issuedAt"], "gbmMaeHours": gbm_mae,
            "baselineMaeHours": baseline_mae, "historicalMedianMaeHours": mae("historicalMedian"),
            "intervalNominal": 0.8, "intervalCoverage": float(np.mean([r["low"] <= r["observed"] <= r["high"] for r in predictions])),
            "calibrationRadiusHours": width, "holdoutPredictions": predictions,
            "metrics": metrics, "biasDefinition": "observed minus predicted; positive means underprediction",
            "incrementalValue": {"weatherAndAisMaeReductionHours": metrics["scheduler_only_gbm"]["maeHours"]-gbm_mae,
                "weatherGivenAisMaeReductionHours": metrics["scheduler_ais_gbm"]["maeHours"]-gbm_mae,
                "aisGivenWeatherMaeReductionHours": metrics["scheduler_weather_gbm"]["maeHours"]-gbm_mae,
                "interpretation": "Paired descriptive holdout comparisons, not a significance test or operational savings"},
            "calibrationGbmMaeHours": calibration_gbm_mae, "calibrationBaselineMaeHours": calibration_baseline_mae,
            # Promotion is decided on calibration only; the holdout is reporting-only.
            "promotion": "GBM" if calibration_gbm_mae < 0.98*calibration_baseline_mae else "BASELINE",
            "config": {"trees": 40, "depth": 2, "learningRate": 0.05, "seed": 168,
                       "ablationFeatures": {k: list(v) for k, v in VARIANTS.items()},
                       "split": "60/20/20 by issue time; availability and recording purge"}}


def predict(features: dict, rows: list[dict], report: dict | None) -> dict:
    missing = []
    if features.get("wind_speed") is None:
        missing.append("An issue-time maximum-wind forecast covering planned arrival")
    if features.get("trackCount", 0) < 2 or features.get("trackAgeHours", 99) > 1:
        missing.append("Two archived AIS positions, with the latest within one hour")
    if not report:
        missing.append("A sealed chronological benchmark with measured arrival outcomes")
    elif report["codeHash"] != hashlib.sha256(Path(__file__).read_bytes()).hexdigest() or report["dependencies"] != {"numpy": np.__version__, "scikit-learn": sklearn.__version__}:
        missing.append("The sealed benchmark's code/dependency versions differ; evaluate the current model on a new later period")
    if missing:
        return {"status": "INSUFFICIENT_DATA", "value": None, "low": None, "high": None,
                "modelVersion": VERSION, "intervalNominal": None, "missing": missing, "fitIds": [], "calibrationIds": []}
    by_id = {r["operationId"]: r for r in rows}
    train = [by_id[k] for k in report["fitIds"] if k in by_id]
    cal = [by_id[k] for k in report["calibrationIds"] if k in by_id]
    if len(train) != report["fitCount"] or len(cal) != report["calibrationCount"]:
        raise ValueError("The sealed model's training evidence is unavailable at this clock")
    model = fit(train)
    if report["promotion"] == "GBM":
        point, width = max(0, float(model.predict([vector(features)])[0])), radius(model, cal)
    else:
        point = features["baselineWaitHours"]
        errors = sorted(abs(r["waitHours"]-r["features"]["baselineWaitHours"]) for r in cal)
        width = errors[min(len(errors)-1, math.ceil((len(errors)+1)*0.8)-1)]
    return {"status": "AVAILABLE", "value": point, "low": max(0, point-width), "high": point+width,
            "modelVersion": VERSION, "model": report["promotion"], "intervalNominal": 0.8,
            "missing": [], "benchmarkHash": digest(report), "fitIds": report["fitIds"], "calibrationIds": report["calibrationIds"]}
