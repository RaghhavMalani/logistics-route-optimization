"""Verify that a pipeline run produced a coherent, honest artefact set.

This is the gate between "the pipeline exited zero" and "the terminal can be
trusted". It checks that every artefact the API serves exists, that the numbers
inside them are internally consistent (monotonic quantiles, regime probabilities
that sum to one, decisions that reference real ports), and -- most importantly --
that nothing claims to be live when its own timestamps say otherwise.

    python scripts/verify_artefacts.py

Exit code is non-zero on the first hard failure, so CI can rely on it.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
CACHE = ROOT / "data" / "cache"
OUTPUTS = ROOT / "outputs"

REQUIRED_CACHE = [
    "port_state.json",
    "forecast_by_port.json",
    "regime_by_port.json",
    "decision_by_port.json",
    "model_pipeline.json",
    "live_status.json",
    "provenance.json",
    "vessels.json",
    "fleet.json",
]

REQUIRED_OUTPUTS = [
    "expert_features/merged_panel.csv",
    "expert_features/capacity_features.csv",
    "expert_features/anomaly_features.csv",
    "expert_features/arrival_features.csv",
    "expert_features/disruption_features.csv",
    "expert_features/data_quality_features.csv",
    "regimes/regimes.csv",
    "forecasts/forecast_table.csv",
    "forecasts/decisions.csv",
    "forecasts/route_recommendations.csv",
]

#: Specialist columns that must reach the model, not merely exist as files.
REQUIRED_PANEL_COLUMNS = [
    "capacity_pressure", "queue_momentum", "berth_pressure",
    "arrival_clustering", "anomaly_score", "disruption_pressure",
    "weather_persistence", "data_quality_score", "specialist_stress",
]

PROVENANCE_STATES = {"LIVE", "CACHED_LIVE", "STALE", "SYNTHETIC", "UNAVAILABLE"}


class Report:
    def __init__(self) -> None:
        self.failures: list[str] = []
        self.warnings: list[str] = []

    def check(self, condition: bool, message: str) -> bool:
        if not condition:
            self.failures.append(message)
        return condition

    def warn(self, condition: bool, message: str) -> None:
        if not condition:
            self.warnings.append(message)


def _load_json(path: Path):
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)


def verify() -> Report:
    report = Report()

    for name in REQUIRED_CACHE:
        report.check((CACHE / name).exists(), f"missing cache artefact: {name}")
    for name in REQUIRED_OUTPUTS:
        report.check((OUTPUTS / name).exists(), f"missing output artefact: {name}")
    if report.failures:
        return report

    # --- the merged panel actually carries the specialist signals ------------
    panel = pd.read_csv(OUTPUTS / "expert_features" / "merged_panel.csv")
    for column in REQUIRED_PANEL_COLUMNS:
        report.check(column in panel.columns,
                     f"specialist column '{column}' never reached the panel")
        duplicate = f"{column}_x"
        report.check(duplicate not in panel.columns,
                     f"'{column}' was merged twice and suffixed to '{duplicate}'")

    if all(c in panel.columns for c in REQUIRED_PANEL_COLUMNS):
        latest = (panel.sort_values("date").groupby("port_id").tail(1))
        for column in ("capacity_pressure", "berth_pressure", "anomaly_score"):
            varied = latest[column].nunique() > 1
            report.warn(varied,
                        f"'{column}' is identical across every port on the "
                        "latest day, which usually means it fell back to a "
                        "neutral default")

    # --- forecasts are well formed -------------------------------------------
    forecasts = _load_json(CACHE / "forecast_by_port.json")
    report.check(bool(forecasts), "forecast cache is empty")
    for code, rows in forecasts.items():
        report.check(bool(rows), f"{code}: no forecast rows")
        for row in rows:
            ok = row["q10"] <= row["q50"] <= row["q90"]
            if not report.check(ok, f"{code} day {row['day']}: quantiles cross"):
                break
            report.check(0.0 <= row["confidence"] <= 1.0,
                         f"{code} day {row['day']}: confidence out of range")
            report.check(row["dataStatus"] in PROVENANCE_STATES,
                         f"{code}: unknown data status {row['dataStatus']}")

    # --- regimes are distributions -------------------------------------------
    regimes = _load_json(CACHE / "regime_by_port.json")
    for code, regime in regimes.items():
        total = sum(regime["probabilities"].values())
        report.check(abs(total - 1.0) < 0.05,
                     f"{code}: regime probabilities sum to {total:.3f}")

    # --- decisions reference real ports and carry their evidence --------------
    decisions = _load_json(CACHE / "decision_by_port.json")
    for code, decision in decisions.items():
        report.check(code in forecasts,
                     f"decision for {code} has no matching forecast")
        for field in ("action", "target", "rationale", "expectedImpact",
                      "alternativeAction"):
            report.check(bool(str(decision.get(field, "")).strip()),
                         f"{code}: decision field '{field}' is empty")
        if decision["action"] in {"NORMAL", "MONITOR_QUALITY",
                                  "MONITOR_DISAGREEMENT"}:
            saved = decision.get("expectedDelaySavedHours") or 0.0
            report.check(abs(saved) < 1e-9,
                         f"{code}: a passive action claims a {saved}h saving")

    # --- provenance is coherent ----------------------------------------------
    provenance = _load_json(CACHE / "provenance.json")
    sources = provenance.get("sources", {})
    report.check(bool(sources), "provenance registry is empty")
    for name, source in sources.items():
        report.check(source["status"] in PROVENANCE_STATES,
                     f"{name}: unknown provenance state {source['status']}")
        if source["status"] == "LIVE" and source.get("ageHours") is not None:
            report.check(
                source["ageHours"] <= source["freshness_budget_hours"],
                f"{name}: claims LIVE at {source['ageHours']}h against a "
                f"{source['freshness_budget_hours']}h budget")

    # --- the run summary matches the forecast it describes --------------------
    status = _load_json(CACHE / "live_status.json")
    forecast_table = pd.read_csv(OUTPUTS / "forecasts" / "forecast_table.csv")
    report.check(status["ports"] == forecast_table["port_id"].nunique(),
                 "live_status port count disagrees with the forecast table")
    report.check(str(status["model"]) == str(forecast_table["model"].iloc[0]),
                 "live_status model disagrees with the forecast table")

    # --- benchmark, when present, must be internally consistent --------------
    benchmark_path = OUTPUTS / "forecasts" / "benchmark_summary.json"
    if benchmark_path.exists():
        summary = _load_json(benchmark_path)["summary"]
        table = pd.read_csv(OUTPUTS / "forecasts" / "model_benchmark.csv")
        best = table.sort_values("mae").iloc[0]
        report.check(str(best["model"]) == summary["bestModel"],
                     "benchmark summary names a different leader than the table")
        counts = table["n"].nunique()
        report.warn(counts == 1,
                    "models were scored on different row counts; the headline "
                    "comparison is not strictly apples-to-apples")
    else:
        report.warnings.append(
            "no benchmark artefacts; accuracy claims cannot be substantiated "
            "until `python -m src.evaluation.model_benchmark` has run")

    return report


def main() -> int:
    report = verify()
    for warning in report.warnings:
        print(f"WARN  {warning}")
    for failure in report.failures:
        print(f"FAIL  {failure}")
    if report.failures:
        print(f"\n{len(report.failures)} artefact checks failed.")
        return 1
    print(f"Artefacts verified. {len(report.warnings)} warning(s).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
