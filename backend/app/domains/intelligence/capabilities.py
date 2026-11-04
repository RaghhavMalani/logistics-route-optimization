"""Bounded intelligence adapters and measured candidate results in the terminal."""
from __future__ import annotations
from src.utils.settings import get_settings

import json
from pathlib import Path
from typing import Literal
from fastapi import APIRouter, Query, HTTPException
from backend.app.services import cache_service as cache
from src.portwatch_os.clock import get_clock, LIVE
from src.portwatch_os.intelligence import capability_layers
from src.utils import port_registry
from src.utils.config import FORECASTS_DIR

router = APIRouter()


@router.get("/learning/experiments")
def experiments():
    results = {}
    for key in ("neural_fusion", "constrained_rl"):
        path = Path(get_settings().PORTWATCH_EXPERIMENT_DIR or FORECASTS_DIR) / (key+"_report.json")
        results[key] = json.loads(path.read_text()) if path.exists() else {"status":"UNTRAINED"}
    inference = FORECASTS_DIR / "neural_fusion_live.csv"
    results["neural_fusion"]["shadowInferenceAvailable"] = inference.exists()
    results["freshness"] = cache.get_live_status()
    return results


@router.get("/intelligence/layer/{layer}")
def layer(layer: Literal["aircraft", "satellites", "cyclones", "infrastructure"],
          portCode: str = Query("INNSA")):
    port = port_registry.resolve(portCode)
    if port is None:
        raise HTTPException(404,"Port is not registered")
    if get_clock().state.mode != LIVE:
        return {"status":"HISTORICAL_UNAVAILABLE","features":[],"records":[],
                "source":"", "coverage":"Current provider data is withheld during replay.",
                "layer":layer,"portCode":port.locode,"fetchedAt":None,
                "reason":"No issue-time archive for this layer"}
    return capability_layers.retained(layer, port)
