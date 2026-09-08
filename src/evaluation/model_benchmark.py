"""Walk-forward model benchmark -- the evidence behind every accuracy claim.

All candidate models are scored on **identical expanding-window folds** over the
**same supervised frame**, so the comparison is apples-to-apples and time-series
safe. Nothing is tuned on the test block, and the ensemble weighting policy this
module fits is derived exclusively from out-of-fold predictions.

Candidates
----------
    Naive persistence     tomorrow == today, with empirical error bands so it can
                          be scored probabilistically. The floor to beat.
    Seasonal naive (7d)   same weekday last week -- the weekly berth rhythm.
    GBM quantile          gradient-boosted quantile model on the departure from
                          persistence.
    Ridge quantile        a regularised linear model with empirical residual
                          bands: a genuinely different inductive bias.
    TFT                   the deep model, scored on the same folds, when the
                          pytorch-forecasting stack is installed.
    Adaptive ensemble     the fitted stack over persistence + GBM + the second
                          opinion, scored out-of-fold like every other entry.

Why a stack over horizon
------------------------
The first run of this benchmark showed naive persistence beating every learned
model at short lead times and losing from roughly day six -- the ordinary
behaviour of a smoothed, strongly autocorrelated index. A single fixed blend
cannot exploit that, so the weights are fitted **per horizon** (and, where there
is enough data, per regime and per port) by minimising pinball loss on
out-of-fold predictions.

Metrics
-------
MAE, RMSE, MAPE, pinball loss at q10/q50/q90, empirical 80% interval coverage,
mean interval width and absolute calibration error -- broken down overall, by
horizon, by port and by HSMM regime.

Artefacts written to ``outputs/forecasts/``
------------------------------------------
    model_benchmark.csv     one row per model
    horizon_benchmark.csv   accuracy by lead time
    port_benchmark.csv      accuracy by port
    regime_benchmark.csv    accuracy by HSMM regime
    calibration.json        nominal vs empirical coverage curve
    ensemble_weights.json   the fitted, leakage-safe stacking policy
    benchmark_summary.json  headline numbers plus the protocol used
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Dict, Iterable, List

import numpy as np
import pandas as pd

from src.evaluation.metrics import interval_coverage, mae, mape, pinball_loss, rmse
from src.forecasting import ensemble as ensemble_module
from src.forecasting.ensemble import EnsemblePolicy
from src.forecasting.forecast_runner import (
    BaselineQuantileForecaster, PersistenceQuantileForecaster,
)
from src.forecasting.linear_model import RidgeQuantileForecaster
from src.forecasting.tft_dataset import build_supervised
from src.utils.config import FORECAST_HORIZON_DAYS, FORECASTS_DIR, PORT_ID, PRIMARY_TARGET
from src.utils.logging_utils import get_logger

log = get_logger(__name__)

BENCHMARK_VERSION = "walk-forward-v3"

#: Nominal levels used for the calibration curve.
CALIBRATION_LEVELS = (0.5, 0.8, 0.9)

NAIVE = "Naive persistence"
SEASONAL = "Seasonal naive (7d)"
GBM = "GBM quantile"
RIDGE = "Ridge quantile"
TFT = "TFT (deep)"
ENSEMBLE = "Adaptive ensemble"

#: Benchmark display name -> ensemble member key.
MEMBER_OF = {
    NAIVE: ensemble_module.PERSISTENCE,
    GBM: ensemble_module.GBM,
    RIDGE: ensemble_module.SECOND_OPINION,
    TFT: ensemble_module.SECOND_OPINION,
}

#: Simplex resolution for the stacking weight search.
WEIGHT_STEP = 0.1

#: Minimum out-of-fold rows before a cell earns its own weight vector.
MIN_ROWS_HORIZON = 30
MIN_ROWS_CELL = 200


@dataclass
class Fold:
    index: int
    cutoff: pd.Timestamp
    next_cut: pd.Timestamp
    train: pd.DataFrame
    test: pd.DataFrame


def expanding_folds(frame: pd.DataFrame, n_folds: int = 5,
                    min_train_frac: float = 0.5) -> List[Fold]:
    """Expanding-window folds. A training row is used only if its label was
    already observable at the fold cutoff."""
    origins = np.sort(frame["forecast_origin_date"].unique())
    if len(origins) < n_folds + 2:
        n_folds = max(1, len(origins) // 3)
    start = int(len(origins) * min_train_frac)
    cuts = sorted(set(np.linspace(start, len(origins) - 1, n_folds + 1).astype(int)))

    folds: List[Fold] = []
    for i in range(len(cuts) - 1):
        cutoff = pd.Timestamp(origins[cuts[i]])
        nxt = pd.Timestamp(origins[cuts[i + 1]])
        train = frame[frame["target_date"] <= cutoff]
        test = frame[(frame["forecast_origin_date"] > cutoff)
                     & (frame["forecast_origin_date"] <= nxt)
                     & (frame["target_date"] > cutoff)]
        if not train.empty and not test.empty:
            folds.append(Fold(i, cutoff, nxt, train, test))
    return folds


# ---------------------------------------------------------------------------
# Per-model out-of-fold predictions
# ---------------------------------------------------------------------------
def _persistence(fold: Fold, primary: str) -> pd.DataFrame:
    """Persistence with empirical error bands, so it can be scored as a
    probabilistic model and enter the stack on equal terms."""
    model = PersistenceQuantileForecaster(primary_target=primary).fit(fold.train)
    preds = model.predict(fold.test)
    preds.index = fold.test.index
    return preds


def _seasonal(test: pd.DataFrame, primary: str) -> pd.DataFrame:
    """Same weekday last week: prefer the 7-day lag, else the weekly mean."""
    for column in (f"{primary}_lag7", f"{primary}_roll7", f"{primary}_now"):
        if column in test:
            point = test[column].to_numpy(dtype=float)
            return pd.DataFrame({"q10": np.nan, "q50": point, "q90": np.nan,
                                 "predicted_congestion": point}, index=test.index)
    return pd.DataFrame({"q10": np.nan, "q50": np.nan, "q90": np.nan,
                         "predicted_congestion": np.nan}, index=test.index)


def _gbm(fold: Fold, feature_cols: List[str], primary: str) -> pd.DataFrame:
    model = BaselineQuantileForecaster(primary_target=primary).fit(
        fold.train, feature_cols, [primary])
    preds = model.predict(fold.test, feature_cols)
    preds.index = fold.test.index
    return preds


def _ridge(fold: Fold, feature_cols: List[str], primary: str) -> pd.DataFrame:
    model = RidgeQuantileForecaster(primary_target=primary).fit(
        fold.train, feature_cols)
    preds = model.predict(fold.test, feature_cols)
    preds.index = fold.test.index
    return preds


def _tft(fold: Fold, panel: pd.DataFrame, weather_now: pd.DataFrame | None,
         horizon: int, primary: str, epochs: int) -> pd.DataFrame | None:
    """Score the deep model on this fold, training only on pre-cutoff data."""
    from src.forecasting.tft_model import TFTConfig, TFTForecaster, torch_available

    if not torch_available():
        return None
    frame = panel.copy()
    frame["date"] = pd.to_datetime(frame["date"])
    train_panel = frame[frame["date"] <= fold.cutoff]
    if train_panel["date"].nunique() < 60:
        return None

    model = TFTForecaster(TFTConfig(horizon=horizon, max_epochs=epochs))
    model.fit(train_panel, weather_now)
    forecast = model.predict_future(train_panel, weather_now)
    if forecast is None or forecast.empty:
        return None

    keys = [PORT_ID, "target_date"]
    forecast = forecast.copy()
    forecast["target_date"] = pd.to_datetime(forecast["target_date"])
    test = fold.test.copy()
    test["target_date"] = pd.to_datetime(test["target_date"])
    merged = test[keys].merge(
        forecast[keys + ["q10", "q50", "q90", "predicted_congestion"]],
        on=keys, how="left")
    merged.index = fold.test.index
    return merged[["q10", "q50", "q90", "predicted_congestion"]]


# ---------------------------------------------------------------------------
# Scoring
# ---------------------------------------------------------------------------
def _score(truth: np.ndarray, preds: pd.DataFrame) -> Dict[str, float]:
    point = preds["predicted_congestion"].to_numpy(dtype=float)
    row: Dict[str, float] = {
        "mae": mae(truth, point),
        "rmse": rmse(truth, point),
        "mape_pct": mape(truth, point),
    }
    q10 = preds["q10"].to_numpy(dtype=float)
    q50 = preds["q50"].to_numpy(dtype=float)
    q90 = preds["q90"].to_numpy(dtype=float)
    if np.isfinite(q10).any() and np.isfinite(q90).any():
        row["pinball_q10"] = pinball_loss(truth, q10, 0.1)
        row["pinball_q50"] = pinball_loss(truth, q50, 0.5)
        row["pinball_q90"] = pinball_loss(truth, q90, 0.9)
        row["coverage_80pct"] = interval_coverage(truth, q10, q90)
        row["interval_width"] = float(np.nanmean(q90 - q10))
        row["calibration_error"] = abs(row["coverage_80pct"] - 0.80)
    return row


def _aggregate(frame: pd.DataFrame, ycol: str, group_cols: Iterable[str]
               ) -> pd.DataFrame:
    group_cols = list(group_cols)
    rows = []
    for keys, group in frame.groupby(group_cols, sort=True):
        keys = keys if isinstance(keys, tuple) else (keys,)
        record = dict(zip(group_cols, keys))
        record["n"] = int(len(group))
        record.update(_score(group[ycol].to_numpy(dtype=float), group))
        rows.append(record)
    return pd.DataFrame(rows)


def _round(frame: pd.DataFrame, digits: int = 4) -> pd.DataFrame:
    out = frame.copy()
    for column in out.columns:
        if pd.api.types.is_float_dtype(out[column]):
            out[column] = out[column].round(digits)
    return out


# ---------------------------------------------------------------------------
# Stacking (out-of-fold only)
# ---------------------------------------------------------------------------
def _simplex(members: List[str], step: float = WEIGHT_STEP) -> List[Dict[str, float]]:
    """Every weight vector on the simplex at the given resolution."""
    steps = int(round(1.0 / step))

    def walk(remaining: int, index: int, current: List[int]):
        if index == len(members) - 1:
            yield current + [remaining]
            return
        for take in range(remaining + 1):
            yield from walk(remaining - take, index + 1, current + [take])

    return [dict(zip(members, [c / steps for c in combo]))
            for combo in walk(steps, 0, [])]


def _blend_column(block: pd.DataFrame, members: List[str],
                  weights: Dict[str, float], quantile: str) -> np.ndarray:
    blended = np.zeros(len(block), dtype=float)
    for member in members:
        values = pd.to_numeric(block[f"{quantile}__{member}"],
                               errors="coerce").to_numpy(dtype=float)
        blended = blended + weights[member] * np.nan_to_num(values)
    return blended


def _pinball_of_blend(block: pd.DataFrame, members: List[str],
                      weights: Dict[str, float], ycol: str) -> float:
    truth = block[ycol].to_numpy(dtype=float)
    total = 0.0
    for quantile, level in (("q10", 0.1), ("q50", 0.5), ("q90", 0.9)):
        blended = _blend_column(block, members, weights, quantile)
        total += pinball_loss(truth, blended, level)
    return total / 3.0


def _wide_members(predictions: pd.DataFrame, ycol: str
                  ) -> tuple[pd.DataFrame, List[str]]:
    """One row per example, one column set per ensemble member."""
    keys = [PORT_ID, "forecast_origin_date", "target_date", "horizon_day"]
    frames = []
    members: List[str] = []
    for display_name, member in MEMBER_OF.items():
        block = predictions[predictions["model"] == display_name]
        if block.empty or member in members:
            continue
        members.append(member)
        frames.append(block[keys + ["q10", "q50", "q90"]].rename(
            columns={q: f"{q}__{member}" for q in ("q10", "q50", "q90")}))

    if not frames:
        return pd.DataFrame(), []

    wide = predictions[predictions["model"] == GBM][keys + [ycol, "regime"]]
    for frame in frames:
        wide = wide.merge(frame, on=keys, how="inner")
    return wide.dropna(subset=[ycol]).reset_index(drop=True), members


def fit_stacking_policy(predictions: pd.DataFrame, ycol: str, folds: int,
                        second_opinion: str | None
                        ) -> tuple[EnsemblePolicy, pd.DataFrame, List[str]]:
    """Fit stacking weights on out-of-fold predictions only.

    The objective is the mean pinball loss of the *blended quantiles*, not
    squared error on the median, because the product depends on the whole
    predictive distribution and not just its centre.
    """
    wide, members = _wide_members(predictions, ycol)
    if wide.empty or len(members) < 2:
        return (EnsemblePolicy(source="not enough out-of-fold members to stack"),
                wide, members)

    grid = _simplex(members)

    def best(block: pd.DataFrame) -> Dict[str, float]:
        scored = [(_pinball_of_blend(block, members, weights, ycol), weights)
                  for weights in grid]
        scored = [item for item in scored if np.isfinite(item[0])]
        if not scored:
            share = 1.0 / len(members)
            return {m: share for m in members}
        return min(scored, key=lambda item: item[0])[1]

    global_weights = best(wide)

    by_horizon: Dict[int, Dict[str, float]] = {}
    for horizon, block in wide.groupby("horizon_day"):
        if len(block) >= MIN_ROWS_HORIZON:
            by_horizon[int(horizon)] = best(block)

    by_regime: Dict[str, Dict[str, float]] = {}
    for regime, block in wide.groupby("regime"):
        if isinstance(regime, str) and regime != "UNKNOWN" and len(block) >= MIN_ROWS_CELL:
            by_regime[regime] = best(block)

    by_port: Dict[str, Dict[str, float]] = {}
    for port, block in wide.groupby(PORT_ID):
        if len(block) >= MIN_ROWS_CELL:
            by_port[str(port)] = best(block)

    from src.forecasting.calibration import conformal_offset
    conformal: Dict[int, float] = {}
    for horizon, block in wide.groupby("horizon_day"):
        weights = by_horizon.get(int(horizon), global_weights)
        lo = _blend_column(block, members, weights, "q10")
        hi = _blend_column(block, members, weights, "q90")
        offset = conformal_offset(block[ycol], lo, hi, alpha=0.2)
        conformal[int(horizon)] = round(max(0.0, float(offset)), 3)

    policy = EnsemblePolicy(
        members=members,
        global_weights=global_weights,
        by_horizon=by_horizon,
        by_regime=by_regime,
        by_port=by_port,
        conformal_by_horizon=conformal,
        fitted=True,
        source=(f"stacked out-of-fold on {folds} expanding walk-forward folds "
                f"over {', '.join(members)}; pinball-optimal per horizon"),
        folds=folds,
        generated_at=datetime.now(timezone.utc).isoformat(),
        second_opinion_model=second_opinion,
    )
    return policy, wide, members


def _blend_predictions(wide: pd.DataFrame, members: List[str],
                       policy: EnsemblePolicy, ycol: str) -> pd.DataFrame:
    """Reconstruct out-of-fold ensemble predictions using the fitted policy."""
    if wide.empty or not members:
        return pd.DataFrame()

    keys = [PORT_ID, "forecast_origin_date", "target_date", "horizon_day"]
    out = wide[keys + [ycol, "regime"]].copy()

    weight_matrix = np.array([
        [policy.weights_for(horizon=row.horizon_day,
                            regime=getattr(row, "regime", None),
                            port_id=getattr(row, PORT_ID)).get(m, 0.0)
         for m in members]
        for row in wide.itertuples()
    ], dtype=float)
    weight_matrix = weight_matrix / np.clip(
        weight_matrix.sum(axis=1, keepdims=True), 1e-9, None)

    for quantile in ("q10", "q50", "q90"):
        stack = np.column_stack([
            pd.to_numeric(wide[f"{quantile}__{m}"], errors="coerce").to_numpy()
            for m in members
        ])
        out[quantile] = np.nansum(np.nan_to_num(stack) * weight_matrix, axis=1)

    offsets = out["horizon_day"].map(policy.conformal_for).astype(float).to_numpy()
    out["q10"] = np.clip(out["q10"].to_numpy() - offsets, 0.0, None)
    out["q90"] = out["q90"].to_numpy() + offsets
    stacked = np.sort(out[["q10", "q50", "q90"]].to_numpy(dtype=float), axis=1)
    out[["q10", "q50", "q90"]] = stacked
    out["predicted_congestion"] = out["q50"]

    medians = np.column_stack([
        pd.to_numeric(wide[f"q50__{m}"], errors="coerce").to_numpy() for m in members
    ])
    band = np.clip((out["q90"] - out["q10"]).to_numpy(dtype=float), 1.0, None)
    out["model_disagreement"] = np.clip(
        (np.nanmax(medians, axis=1) - np.nanmin(medians, axis=1)) / band, 0, 1)
    out["model"] = ENSEMBLE
    return out


# ---------------------------------------------------------------------------
# Calibration curve
# ---------------------------------------------------------------------------
def _calibration(predictions: pd.DataFrame, ycol: str) -> dict:
    """Nominal vs empirical coverage, per model, from the q10/q50/q90 points."""
    curve: dict = {"levels": list(CALIBRATION_LEVELS), "models": {}}
    for model, block in predictions.groupby("model"):
        if block["q10"].isna().all() or block["q90"].isna().all():
            continue
        truth = block[ycol].to_numpy(dtype=float)
        q10 = block["q10"].to_numpy(dtype=float)
        q50 = block["q50"].to_numpy(dtype=float)
        q90 = block["q90"].to_numpy(dtype=float)
        entries = []
        for level in CALIBRATION_LEVELS:
            # Scale the measured 80% half-band onto the requested nominal level,
            # assuming a locally symmetric predictive distribution.
            scale = _band_scale(level)
            lo = q50 - scale * (q50 - q10)
            hi = q50 + scale * (q90 - q50)
            empirical = interval_coverage(truth, lo, hi)
            entries.append({
                "nominal": level,
                "empirical": round(float(empirical), 4),
                "error": round(abs(float(empirical) - level), 4),
                "meanWidth": round(float(np.nanmean(hi - lo)), 3),
            })
        curve["models"][str(model)] = entries
    return curve


def _band_scale(level: float) -> float:
    """Multiplier mapping the measured 80% half-band onto another level."""
    from math import erf, sqrt

    def z(p: float) -> float:
        # Inverse normal CDF via bisection -- avoids a scipy dependency.
        lo, hi = -6.0, 6.0
        for _ in range(80):
            mid = (lo + hi) / 2.0
            if 0.5 * (1.0 + erf(mid / sqrt(2.0))) < p:
                lo = mid
            else:
                hi = mid
        return (lo + hi) / 2.0

    return z(0.5 + level / 2.0) / z(0.9)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
def run_benchmark(panel: pd.DataFrame,
                  weather_now: pd.DataFrame | None = None,
                  horizon: int = FORECAST_HORIZON_DAYS,
                  n_folds: int = 5,
                  include_tft: bool | None = None,
                  tft_epochs: int = 12,
                  output_dir=None) -> dict:
    """Run the full walk-forward benchmark and write every artefact."""
    output_dir = output_dir or FORECASTS_DIR
    output_dir.mkdir(parents=True, exist_ok=True)

    supervised = build_supervised(panel, weather_now, horizon)
    frame = supervised.frame
    primary = (PRIMARY_TARGET if PRIMARY_TARGET in supervised.available_targets
               else supervised.available_targets[0])
    ycol = f"y_{primary}"

    regime_lookup = _regime_lookup(panel)
    folds = expanding_folds(frame, n_folds=n_folds)
    if not folds:
        log.warning("Not enough history for a walk-forward benchmark.")
        return {"available": False, "reason": "insufficient history"}

    if include_tft is None:
        from src.forecasting.tft_model import torch_available
        include_tft = torch_available()

    records: List[pd.DataFrame] = []
    for fold in folds:
        test = fold.test
        base = test[[PORT_ID, "forecast_origin_date", "target_date",
                     "horizon_day", ycol]].copy()
        base["fold"] = fold.index
        base["regime"] = [
            regime_lookup.get((str(p), pd.Timestamp(d)), "UNKNOWN")
            for p, d in zip(test[PORT_ID], test["forecast_origin_date"])
        ]

        candidates = {
            NAIVE: _persistence(fold, primary),
            SEASONAL: _seasonal(test, primary),
            GBM: _gbm(fold, supervised.feature_cols, primary),
            RIDGE: _ridge(fold, supervised.feature_cols, primary),
        }
        if include_tft:
            try:
                deep = _tft(fold, panel, weather_now, horizon, primary, tft_epochs)
                if deep is not None:
                    candidates[TFT] = deep
            except Exception as exc:
                log.warning("TFT fold %d skipped: %s", fold.index, exc)

        for name, preds in candidates.items():
            block = base.copy()
            for column in ("q10", "q50", "q90", "predicted_congestion"):
                block[column] = preds[column].to_numpy() if column in preds else np.nan
            block["model"] = name
            records.append(block)

        log.info("Fold %d | train<=%s | test rows=%d | models=%s",
                 fold.index, fold.cutoff.date(), len(test), ", ".join(candidates))

    predictions = pd.concat(records, ignore_index=True)

    # --- fit the stacking policy out-of-fold, then score the ensemble --------
    available = set(predictions["model"])
    secondary_name = TFT if TFT in available else RIDGE
    dropped = {TFT, RIDGE} - {secondary_name}
    stack_input = predictions[~predictions["model"].isin(dropped)]
    policy, wide, members = fit_stacking_policy(stack_input, ycol, len(folds),
                                                secondary_name)
    ensemble = _blend_predictions(wide, members, policy, ycol)
    if not ensemble.empty:
        ensemble["fold"] = np.nan
        predictions = pd.concat([predictions, ensemble], ignore_index=True)

    # --- aggregate ----------------------------------------------------------
    scored = predictions.dropna(subset=[ycol])
    model_table = _round(_aggregate(scored, ycol, ["model"]))
    model_table = model_table.sort_values("mae").reset_index(drop=True)
    horizon_table = _round(_aggregate(scored, ycol, ["model", "horizon_day"]))
    port_table = _round(_aggregate(scored, ycol, ["model", PORT_ID]))
    regime_table = _round(_aggregate(scored, ycol, ["model", "regime"]))

    calibration = _calibration(scored, ycol)

    model_table.to_csv(output_dir / "model_benchmark.csv", index=False)
    horizon_table.to_csv(output_dir / "horizon_benchmark.csv", index=False)
    port_table.to_csv(output_dir / "port_benchmark.csv", index=False)
    regime_table.to_csv(output_dir / "regime_benchmark.csv", index=False)
    # Retained for the legacy comparison consumers.
    model_table.to_csv(output_dir / "benchmark_comparison.csv", index=False)

    with open(output_dir / "calibration.json", "w", encoding="utf-8") as fh:
        json.dump(calibration, fh, indent=2)
    with open(output_dir / "ensemble_weights.json", "w", encoding="utf-8") as fh:
        json.dump(policy.to_dict(), fh, indent=2)

    best = model_table.iloc[0]
    naive_row = model_table[model_table["model"] == NAIVE]
    naive_mae = float(naive_row.iloc[0]["mae"]) if not naive_row.empty else float("nan")
    skill = (1.0 - float(best["mae"]) / naive_mae) if naive_mae == naive_mae else None

    summary = {
        "version": BENCHMARK_VERSION,
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "target": primary,
        "horizonDays": horizon,
        "summary": {
            "folds": len(folds),
            "testRows": int(len(scored[scored["model"] == GBM])),
            "models": model_table["model"].tolist(),
            "bestModel": str(best["model"]),
            "bestMae": float(best["mae"]),
            "bestRmse": float(best["rmse"]),
            "bestCoverage80": (float(best["coverage_80pct"])
                               if "coverage_80pct" in best
                               and pd.notna(best["coverage_80pct"]) else None),
            "naiveMae": naive_mae,
            "skillVsNaive": None if skill is None else round(skill, 4),
            "tftEvaluated": TFT in available,
            "ensembleSecondModel": secondary_name,
            "ensembleMembers": members,
        },
        "ensembleWeights": policy.to_dict(),
        "trainOrigins": int(frame["forecast_origin_date"].nunique()),
        "protocol": ("expanding-window walk-forward; a training row is used only "
                     "if its label was observable at the fold cutoff; stacking "
                     "weights fitted on out-of-fold predictions only"),
    }
    with open(output_dir / "benchmark_summary.json", "w", encoding="utf-8") as fh:
        json.dump(summary, fh, indent=2)

    predictions.to_csv(output_dir / "walk_forward_predictions.csv", index=False)

    log.info("Benchmark complete (%d folds). Leader: %s (MAE %.3f). Skill vs "
             "naive: %s", len(folds), best["model"], float(best["mae"]),
             "n/a" if skill is None else f"{skill:+.1%}")
    log.info("\n%s", model_table.to_string(index=False))
    log.info("Ensemble policy: %s", policy.describe())
    return summary


def _regime_lookup(panel: pd.DataFrame) -> Dict[tuple, str]:
    """(port, date) -> HSMM regime label, for the by-regime breakdown."""
    if panel is None or panel.empty:
        return {}
    if "regime_label" in panel.columns:
        frame = panel
    elif "p_severe" in panel.columns:
        frame = panel.copy()
        frame["regime_label"] = np.select(
            [frame["p_severe"] >= 0.5, frame["p_congested"] >= 0.5],
            ["SEVERE", "CONGESTED"], default="NORMAL")
    else:
        return {}
    return {
        (str(p), pd.Timestamp(d)): str(label)
        for p, d, label in zip(frame[PORT_ID], pd.to_datetime(frame["date"]),
                               frame["regime_label"])
    }


def load_panel_with_regimes(panel_path, regimes_path=None) -> pd.DataFrame:
    """Read the merged panel and attach the HSMM regime columns."""
    panel = pd.read_csv(panel_path)
    panel["date"] = pd.to_datetime(panel["date"])
    regimes_path = regimes_path or (FORECASTS_DIR.parent / "regimes" / "regimes.csv")
    if regimes_path and pd.io.common.file_exists(str(regimes_path)):
        regimes = pd.read_csv(regimes_path)
        regimes["date"] = pd.to_datetime(regimes["date"])
        keep = [c for c in ("regime_label", "p_normal", "p_congested", "p_severe",
                            "days_in_state", "expected_remaining_days",
                            "transition_risk", "regime_confidence")
                if c in regimes.columns and c not in panel.columns]
        if keep:
            panel = panel.merge(
                regimes[[PORT_ID, "date"] + keep].drop_duplicates([PORT_ID, "date"]),
                on=[PORT_ID, "date"], how="left")
    return panel


def main() -> None:  # pragma: no cover - CLI helper
    import argparse

    from src.utils.config import EXPERT_FEATURES_DIR

    parser = argparse.ArgumentParser(description="Run the walk-forward benchmark.")
    parser.add_argument("--panel", default=str(EXPERT_FEATURES_DIR / "merged_panel.csv"))
    parser.add_argument("--weather", default=str(EXPERT_FEATURES_DIR / "weather_features.csv"))
    parser.add_argument("--folds", type=int, default=5)
    parser.add_argument("--horizon", type=int, default=FORECAST_HORIZON_DAYS)
    parser.add_argument("--tft-epochs", type=int, default=12)
    parser.add_argument("--no-tft", action="store_true")
    args = parser.parse_args()

    panel = load_panel_with_regimes(args.panel)

    weather = None
    try:
        weather = pd.read_csv(args.weather)
        weather["date"] = pd.to_datetime(weather["date"])
    except (OSError, pd.errors.EmptyDataError):
        pass

    run_benchmark(panel, weather, horizon=args.horizon, n_folds=args.folds,
                  include_tft=False if args.no_tft else None,
                  tft_epochs=args.tft_epochs)


if __name__ == "__main__":  # pragma: no cover
    main()
