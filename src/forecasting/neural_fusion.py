"""Small masked specialist gate; a shadow candidate, never automatic promotion.

Fits expanding-window OOF specialist predictions, not in-sample predictions.
Train/validation/calibration/test are disjoint in origin AND target time.
Unarchived weather, source ages and full-history regimes are not invented.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from datetime import datetime, timezone

import numpy as np
import pandas as pd

MEMBERS = ["Naive persistence", "GBM quantile", "Ridge quantile"]
KEYS = ["port_id", "forecast_origin_date", "target_date", "horizon_day"]


def align(rows):
    base = rows[KEYS + ["y_congestion_index"]].drop_duplicates(KEYS).sort_values(KEYS)
    values = []
    for name in MEMBERS:
        part = rows[rows.model == name][KEYS + ["q10", "q50", "q90"]]
        values.append(base[KEYS].merge(part, on=KEYS, how="left")[["q10", "q50", "q90"]].to_numpy(float))
    return base.reset_index(drop=True), np.stack(values, axis=1)


def features(base, values, ports):
    mask = np.isfinite(values[:, :, 1])
    if not mask.any(axis=1).all():
        raise ValueError("at least one specialist is required for each forecast")
    med = np.nan_to_num(values[:, :, 1]) / 100
    widths = np.nan_to_num(values[:, :, 2] - values[:, :, 0]) / 100
    onehot = np.column_stack([(base.port_id == p).to_numpy(float) for p in ports])
    x = np.column_stack([base.horizon_day.to_numpy(float)/10, med, widths, mask.astype(float), onehot])
    return hide_source_inputs(x, mask), mask


def weights(x, mask, model):
    hidden = np.tanh(x @ np.array(model["w1"]) + np.array(model["b1"])) if model["hidden"] else x
    logits = hidden @ np.array(model["w2"]) + np.array(model["b2"])
    logits = np.where(mask, logits, -1e9)
    exp = np.exp(logits - logits.max(axis=1, keepdims=True)) * mask
    return exp / exp.sum(axis=1, keepdims=True)


def hide_source_inputs(x, mask):
    """Use the inference missing-source condition for train-only outages too.

    Features are horizon, medians, widths, availability, then port indicators.
    A hidden specialist contributes neither values nor an availability flag.
    The input array is copied so one training epoch cannot change the next.
    """
    result = x.copy()
    members = mask.shape[1]
    result[:, 1:1+members] *= mask
    result[:, 1+members:1+2*members] *= mask
    result[:, 1+2*members:1+3*members] = mask.astype(float)
    return result


def fit(x, mask, med, y, hidden=8, epochs=220, seed=168):
    rng = np.random.default_rng(seed)
    width = hidden or x.shape[1]
    w1 = rng.normal(0, .15, (x.shape[1], width)) if hidden else np.empty((0, 0))
    b1 = np.zeros(width) if hidden else np.empty(0)
    w2, b2 = rng.normal(0, .05, (width, 3)), np.zeros(3)
    med = np.nan_to_num(med) / 100
    y = y / 100
    for _ in range(epochs):
        # Train-only source dropout, retaining a usable specialist.
        m = mask & (rng.random(mask.shape) > .1)
        empty = ~m.any(axis=1)
        m[empty] = mask[empty]
        epoch_x = hide_source_inputs(x, m)
        h = np.tanh(epoch_x @ w1 + b1) if hidden else epoch_x
        z = np.where(m, h @ w2 + b2, -1e9)
        p = np.exp(z-z.max(axis=1, keepdims=True)) * m
        p /= p.sum(axis=1, keepdims=True)
        predicted = (p*med).sum(axis=1)
        dz = (2*(predicted-y)/len(y))[:, None]*p*(med-predicted[:, None])
        dw2 = h.T @ dz + .0001*w2
        if hidden:
            dh = (dz @ w2.T)*(1-h*h)
            w1 -= .8*(epoch_x.T @ dh + .0001*w1)
            b1 -= .8*dh.sum(axis=0)
        w2 -= .8*dw2
        b2 -= .8*dz.sum(axis=0)
    return {"hidden": hidden, "w1": w1.tolist(), "b1": b1.tolist(), "w2": w2.tolist(), "b2": b2.tolist()}


def predict(base, values, artifact, model_key="network"):
    x, mask = features(base, values, artifact["ports"])
    w = weights(x, mask, artifact[model_key])
    result = (w[:, :, None]*np.nan_to_num(values)).sum(axis=1)
    return np.sort(result, axis=1), w


def experiment(directory: Path):
    if (directory / "neural_fusion.json").exists() or (directory / "neural_fusion_report.json").exists():
        raise ValueError("Preserve the evaluated experiment; use a separate directory and a new chronological reporting period")
    source = directory / "walk_forward_predictions.csv"
    rows = pd.read_csv(source, parse_dates=["forecast_origin_date", "target_date"])
    manifest = json.loads((directory / "benchmark_summary.json").read_text())
    split = manifest["evaluationSplit"]
    fit_end = pd.Timestamp(split["calibrationFrom"])
    test_start = pd.Timestamp(split["holdoutFrom"])
    calibration_start = fit_end + (test_start-fit_end)/2
    base, values = align(rows)
    train = (base.forecast_origin_date < fit_end) & (base.target_date < fit_end)
    valid = (base.forecast_origin_date >= fit_end) & (base.target_date < calibration_start)
    calibrate = (base.forecast_origin_date >= calibration_start) & (base.target_date < test_start)
    test = base.forecast_origin_date >= test_start
    if min(train.sum(), valid.sum(), calibrate.sum(), test.sum()) < 30:
        raise ValueError("insufficient disjoint chronological data")
    artifact = {"ports": sorted(base.loc[train, "port_id"].unique()), "members": MEMBERS,
                "fitThrough": str(base.loc[train, "target_date"].max()), "version": "masked-gate-v2-input-dropout"}
    x, mask = features(base, values, artifact["ports"])
    y = base.y_congestion_index.to_numpy(float)
    for key, hidden in (("network", 8), ("linear", 0)):
        artifact[key] = fit(x[train], mask[train], values[train, :, 1], y[train], hidden)
    predictions = {}
    for key in ("network", "linear"):
        predictions[key] = predict(base, values, artifact, key)[0]
    predictions["equal weighting"] = np.nanmean(values, axis=1)
    predictions["persistence"] = values[:, 0]
    predictions["GBM"] = values[:, 1]
    predictions["Ridge"] = values[:, 2]
    # The original adaptive policy was fitted on its earlier OOF partition.
    adaptive = rows[rows.model == "Adaptive ensemble"]
    if len(adaptive):
        predictions["adaptive ensemble"] = base[KEYS].merge(adaptive[KEYS+["q10", "q50", "q90"]], on=KEYS, how="left")[["q10", "q50", "q90"]].to_numpy(float)
    if not len(adaptive):
        from src.forecasting.ensemble import EnsemblePolicy
        incumbent_policy = EnsemblePolicy.from_dict(manifest["ensembleWeights"])
        w = np.array([[incumbent_policy.weights_for(int(r.horizon_day),port_id=str(r.port_id)).get(m,0) for m in ("persistence","gbm","second")] for r in base.itertuples()])
        w *= np.isfinite(values[:,:,1]); w /= w.sum(axis=1,keepdims=True)
        predictions["adaptive ensemble"] = (w[:,:,None]*np.nan_to_num(values)).sum(axis=1)
    scores = []
    for name, pred in predictions.items():
        available = np.isfinite(pred[:, 1])
        v = valid.to_numpy() & available
        t = test.to_numpy() & available
        c = calibrate.to_numpy() & available
        residual = np.maximum(pred[c, 0]-y[c], y[c]-pred[c, 2])
        radius = max(0., float(np.quantile(residual, min(1., np.ceil((len(residual)+1)*.8)/len(residual)), method="higher")))
        low, high = pred[t, 0]-radius, pred[t, 2]+radius
        scores.append({"model": name, "validationMae": round(float(np.abs(pred[v,1]-y[v]).mean()),4),
            "testMae": round(float(np.abs(pred[t,1]-y[t]).mean()),4), "testRows": int(t.sum()),
            "coverage80": round(float(((y[t]>=low)&(y[t]<=high)).mean()),4), "intervalWidth": round(float((high-low).mean()),4), "calibrationRadius": round(radius,4)})
        if name == "network":
            artifact["calibrationRadius"] = radius
    candidate = next(s for s in scores if s["model"] == "network")
    strongest = min((s for s in scores if s["model"] != "network"), key=lambda s:s["validationMae"])
    # Selection is determined on validation, before reporting test scores.
    artifact["status"] = "CANDIDATE" if candidate["validationMae"] < .98*strongest["validationMae"] else "REJECTED"
    dropout = []
    for index, name in enumerate(MEMBERS):
        degraded = values[test].copy(); degraded[:,index,:] = np.nan
        pred, _ = predict(base[test], degraded, artifact)
        dropout.append({"missing": name, "testMae": round(float(np.abs(pred[:,1]-y[test]).mean()),4)})
    report = {"generatedAt": datetime.now(timezone.utc).isoformat(), "status": artifact["status"],
        "target": "IMF daily congestion-index proxy; not observed vessel waiting or savings", "scores": scores,
        "split": {"train":int(train.sum()),"validation":int(valid.sum()),"calibration":int(calibrate.sum()),"test":int(test.sum()),
                  "fitEnd":str(fit_end),"calibrationStart":str(calibration_start),"testStart":str(test_start)},
        "sourceDropout": dropout, "dataSha256": hashlib.sha256(source.read_bytes()).hexdigest(),
        "codeSha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(), "seed":168,
        "features": "horizon, port, specialist quantiles, interval width, availability masks and disagreement implicit in specialist medians",
        "unavailableFeatures": ["issue-time source ages", "historical future weather", "causal regime vintages"],
        "incumbent": "adaptive ensemble", "promotion": "Shadow inference only; no deployment or operational adoption",
        "tftAudit": "Existing TFTForecaster uses pytorch-forecasting and expanding-window fit; benchmark excludes it unless --include-tft. This gate does not duplicate it."}
    (directory / "neural_fusion.json").write_text(json.dumps(artifact, indent=2))
    (directory / "neural_fusion_report.json").write_text(json.dumps(report, indent=2))
    return report


def shadow_inference(frames, incumbent, directory: Path):
    path = directory / "neural_fusion.json"
    if not path.exists():
        return
    artifact = json.loads(path.read_text())
    keys = ["port_id", "horizon_day"]
    values = []
    for member in ("persistence", "gbm", "second"):
        frame = frames.get(member)
        values.append(incumbent[keys].merge(frame[keys+["q10","q50","q90"]], on=keys, how="left")[["q10","q50","q90"]].to_numpy(float)
                      if frame is not None else np.full((len(incumbent),3), np.nan))
    if pd.to_datetime(incumbent.forecast_origin_date).min() <= pd.Timestamp(artifact["fitThrough"]):
        raise ValueError("neural candidate was trained after this forecast origin")
    pred, w = predict(incumbent, np.stack(values,axis=1), artifact)
    out = incumbent[[c for c in KEYS if c in incumbent]].copy()
    out[["q10","q50","q90"]] = pred
    out["q10"] = np.maximum(0,out.q10-artifact["calibrationRadius"])
    out["q90"] += artifact["calibrationRadius"]
    for i, name in enumerate(MEMBERS): out["weight_"+name] = w[:,i]
    out["status"] = artifact["status"]; out["use"] = "shadow candidate"
    out.to_csv(directory / "neural_fusion_live.csv", index=False)


if __name__ == "__main__":
    from src.utils.config import FORECASTS_DIR
    print(json.dumps(experiment(FORECASTS_DIR), indent=2))
