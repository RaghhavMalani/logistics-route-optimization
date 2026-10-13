"""Build a versioned, hash-checked historical research release; never deploys.

Predeclared GBM feature ablations use the existing chronological protocol.
This reuses a previously reported historical holdout; it is not a new untouched
operational trial. Forecast weather without issue-time archives stays excluded.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import zipfile
from pathlib import Path

import pandas as pd

from src.evaluation.model_benchmark import load_panel_with_regimes, run_benchmark
from src.utils.config import EXPERT_FEATURES_DIR

ROOT = Path(__file__).resolve().parents[1]


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def build(panel_path, output):
    panel = load_panel_with_regimes(panel_path)
    # The unique work directory prevents concurrent pipeline outputs from
    # changing an in-flight research export.
    import tempfile
    with tempfile.TemporaryDirectory(prefix="research-", dir=ROOT / "work") as temporary:
        folder = Path(temporary)
        summary = run_benchmark(panel, include_tft=False, output_dir=folder, include_ablations=True)
        if not summary.get("summary"):
            raise ValueError(summary.get("reason", "Historical evaluation unavailable"))
        panel.sort_values(["port_id", "date"]).to_csv(folder / "dataset.csv", index=False)
        metrics = pd.read_csv(folder / "model_benchmark.csv")
        horizon = pd.read_csv(folder / "horizon_benchmark.csv")
        predictions = pd.read_csv(folder / "holdout_predictions.csv")
        ycol = "y_" + summary["target"]
        paired = predictions.copy()
        paired["error"] = paired[ycol] - paired["predicted_congestion"]
        points = paired.groupby(["model", "target_date", "horizon_day"], as_index=False).agg(
            observed=(ycol, "mean"), predicted=("predicted_congestion", "mean"),
            low=("q10", "mean"), high=("q90", "mean"), samples=(ycol, "count"))
        points.to_csv(folder / "prediction_series.csv", index=False)
        reference = float(metrics.loc[metrics.model == "GBM quantile", "mae"].iloc[0])
        ablations = metrics[metrics.model.isin(["GBM quantile", "GBM history + calendar", "GBM history only"])].copy()
        ablations["mae_change_vs_full_gbm"] = ablations.mae - reference
        ablations.to_csv(folder / "ablations.csv", index=False)
        versions = summary["reproducibility"]["dependencies"]
        (folder / "requirements_evaluation.txt").write_text("\n".join(f"{k}=={v}" for k,v in versions.items() if v and k != "pytorch-forecasting") + "\n", encoding="utf-8")
        (folder / "reproduce.txt").write_text(
            "Historical congestion-proxy research. No operational accuracy or savings claim.\n"
            "This reporting holdout was previously examined; no new untouched trial is claimed.\n"
            "Check out the base repository revision, then overlay evaluation_source.zip.\n"
            "The source archive preserves local evaluation changes identified by forecastCodeSha256.\n"
            "Install requirements_evaluation.txt in Python 3.12 (runtime used for this release).\n"
            "python -m scripts.build_public_research --panel dataset.csv --output data/research_release\n"
            "Issue-time weather archives are absent and future weather is excluded.\n"
            "Feature-removal ablations do not establish causal contributions.\n", encoding="utf-8")
        code_files = [ROOT/"src/__init__.py", ROOT/"scripts/__init__.py", Path(__file__)]
        for directory in ("evaluation", "forecasting", "utils"):
            code_files += sorted((ROOT/"src"/directory).rglob("*.py"))
        with zipfile.ZipFile(folder/"evaluation_source.zip", "w", zipfile.ZIP_DEFLATED) as archive:
            for source in code_files:
                if source.is_file():
                    archive.write(source, source.relative_to(ROOT).as_posix())
        names = ["model_benchmark.csv", "horizon_benchmark.csv", "port_benchmark.csv", "calibration.json",
                 "benchmark_summary.json", "holdout_predictions.csv", "prediction_series.csv", "ablations.csv",
                 "dataset.csv", "requirements_evaluation.txt", "reproduce.txt", "evaluation_source.zip"]
        downloads = [{"name": n, "sha256": digest(folder/n), "bytes": (folder/n).stat().st_size} for n in names]
        release_id = "research-" + hashlib.sha256(json.dumps(downloads, sort_keys=True).encode()).hexdigest()[:16]
        with zipfile.ZipFile(folder / "results.zip", "w", zipfile.ZIP_DEFLATED) as archive:
            for n in names:
                archive.write(folder/n, n)
        downloads.append({"name": "results.zip", "sha256": digest(folder/"results.zip"), "bytes": (folder/"results.zip").stat().st_size})
        def records(frame):
            return json.loads(frame.to_json(orient="records"))
        report = {"available": True, "releaseId": release_id, "generatedAt": summary["generatedAt"],
            "version": "public-research-v1", "evaluationProtocol": summary["version"],
            "target": summary["target"], "unit": "congestion-index points", "models": records(metrics),
            "horizons": records(horizon), "ablations": records(ablations),
            "series": records(points), "calibration": json.loads((folder/"calibration.json").read_text()),
            "partitions": summary["evaluationSplit"], "reproducibility": summary["reproducibility"],
            "downloads": downloads, "limits": [
                "Historical congestion-proxy benchmark; it does not measure realized vessel waiting or savings.",
                "This previously reported historical holdout is reused for research reporting and predeclared ablations; it is not a new untouched trial.",
                "Current live weather and full-history regime features are excluded; historical forecast issue-time archives are absent.",
                "Model ranking does not automatically change the operational production member set.",
                "Nominal 80% intervals and empirical historical coverage do not guarantee future coverage.",
                "Ablations remove feature groups on common rows; this does not establish causal effects."],
            "datasetMeaning": "Existing IMF PortWatch call-pressure congestion proxy with origin-time panel features. Reanalysis is distinct from archived provider forecasts. Same-day availability is an offline assumption; publication vintages are not verified. This does not measure vessel waiting."}
        (folder/"report.json").write_text(json.dumps(report, indent=2, allow_nan=False), encoding="utf-8")
        destination = Path(output)/release_id
        destination.parent.mkdir(parents=True, exist_ok=True)
        if destination.exists():
            raise ValueError("A release identity already exists; never overwrite immutable results")
        destination.mkdir()
        for n in names+["results.zip", "report.json"]:
            shutil.copy2(folder/n, destination/n)
        pointer = destination.parent/"current.json"
        pending = pointer.with_suffix(".tmp")
        pending.write_text(json.dumps({"releaseId": release_id, "reportSha256": digest(destination/"report.json")}, indent=2), encoding="utf-8")
        pending.replace(pointer)
        print(json.dumps({"releaseId": release_id, "models": records(metrics), "output": str(destination)}))
        return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--panel", default=str(EXPERT_FEATURES_DIR / "merged_panel.csv"))
    parser.add_argument("--output", default=str(ROOT / "data/research_release"))
    args = parser.parse_args()
    (ROOT/"work").mkdir(exist_ok=True)
    build(args.panel, args.output)
