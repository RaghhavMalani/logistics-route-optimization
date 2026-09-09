"""Decision Room endpoints.

Scenarios are simulated against the artefacts the pipeline produced, not against
a table of constants. The catalogue describes the shock; every number in the
result is the difference between the live forecast and the same forecast after
the shock has been propagated through the lane-exposure graph.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import pandas as pd
from fastapi import APIRouter, HTTPException

from src.decision.scenario_catalog import catalogue, resolve
from src.decision.scenario_service import simulate_scenario

router = APIRouter()

ROOT = Path(__file__).resolve().parents[3]
FORECAST_PATH = ROOT / "outputs" / "forecasts" / "forecast_table.csv"
PANEL_PATH = ROOT / "outputs" / "expert_features" / "merged_panel.csv"
REGIME_PATH = ROOT / "outputs" / "regimes" / "regimes.csv"
WEATHER_PATH = ROOT / "outputs" / "expert_features" / "weather_features.csv"

REBUILD_HINT = ("Run `python run_award_demo.py --source portwatch` to produce "
                "the forecast artefacts the Decision Room simulates against.")


def _mtime(path: Path) -> float:
    return path.stat().st_mtime if path.exists() else 0.0


@lru_cache(maxsize=4)
def _load(signature: tuple) -> tuple:
    """Load the artefacts, keyed by their modification times so a pipeline
    re-run invalidates the cache automatically."""
    del signature
    if not FORECAST_PATH.exists():
        raise FileNotFoundError(REBUILD_HINT)

    forecast = pd.read_csv(FORECAST_PATH)

    panel = None
    if PANEL_PATH.exists():
        panel = pd.read_csv(PANEL_PATH)
        panel["date"] = pd.to_datetime(panel["date"], errors="coerce")
        if REGIME_PATH.exists():
            regimes = pd.read_csv(REGIME_PATH)
            regimes["date"] = pd.to_datetime(regimes["date"], errors="coerce")
            keep = [c for c in ("regime_label", "p_normal", "p_congested",
                                "p_severe", "transition_risk", "regime_confidence")
                    if c in regimes.columns and c not in panel.columns]
            if keep:
                panel = panel.merge(
                    regimes[["port_id", "date"] + keep]
                    .drop_duplicates(["port_id", "date"]),
                    on=["port_id", "date"], how="left")

    weather = None
    if WEATHER_PATH.exists():
        weather = pd.read_csv(WEATHER_PATH)
        weather["date"] = pd.to_datetime(weather["date"], errors="coerce")

    return forecast, panel, weather


def _artefacts() -> tuple:
    signature = (_mtime(FORECAST_PATH), _mtime(PANEL_PATH), _mtime(WEATHER_PATH))
    try:
        return _load(signature)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=503, detail=str(exc))


@router.get("/scenarios")
def list_scenarios() -> list[dict]:
    return catalogue()


@router.post("/scenarios/simulate")
def simulate(payload: dict) -> dict:
    scenario_key = (payload.get("scenarioKey") or payload.get("scenarioId")
                    or payload.get("scenario") or payload.get("id") or "HORMUZ")
    try:
        intensity = float(payload.get("intensity")
                          or payload.get("scenarioIntensity")
                          or payload.get("multiplier") or 1.0)
    except (TypeError, ValueError):
        intensity = 1.0
    try:
        run_id = int(payload.get("runId") or 0)
    except (TypeError, ValueError):
        run_id = 0

    forecast, panel, weather = _artefacts()
    try:
        result = simulate_scenario(str(scenario_key), intensity, forecast,
                                   panel=panel, weather_now=weather,
                                   run_id=run_id)
    except ValueError as exc:
        raise HTTPException(status_code=503, detail=f"{exc}. {REBUILD_HINT}")

    # Aliases the terminal has historically read.
    result["id"] = result["scenarioKey"]
    result["name"] = result["scenarioName"]
    result["summary"] = (f"{result['scenarioName']} at {intensity:.1f}x moves "
                         f"network congestion by {result['congestionDelta']:+.1f} "
                         f"points and expected berth wait by "
                         f"{result['delayDeltaHours']:+.1f}h.")
    return result


@router.get("/scenarios/{scenario_key}")
def scenario_detail(scenario_key: str) -> dict:
    return resolve(scenario_key).as_dict()
