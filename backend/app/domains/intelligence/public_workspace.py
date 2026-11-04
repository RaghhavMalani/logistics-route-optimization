"""Anonymous public projections and bounded, isolated scenario computation."""
from datetime import datetime
from typing import Literal
from fastapi import APIRouter, HTTPException, Query
from backend.app.services import public_workspace as service

router = APIRouter(prefix="/public")

@router.get("/workspace")
def workspace(mode: Literal["current", "replay", "projection"] = "current", at: datetime | None = None):
    try:
        return service.workspace(mode, at)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from None

@router.get("/scenario")
def scenario(laneCode: str = "EUR_IND", portCode: str = "INNSA", riskChokepoint: str | None = None,
    hoursToRisk: float = Query(24, ge=-48, le=240, allow_inf_nan=False),
    speedKn: float = Query(16, ge=6, le=24, allow_inf_nan=False),
    closureHours: float = Query(72, ge=1, le=240, allow_inf_nan=False),
    severity: float = Query(1, ge=.01, le=1, allow_inf_nan=False),
    waveM: float = Query(2, ge=0, le=12, allow_inf_nan=False),
    charterUsdDay: float = Query(30000, gt=0, le=1000000, allow_inf_nan=False),
    bunkerUsdTonne: float = Query(650, gt=0, le=10000, allow_inf_nan=False),
    fuelTonnesDay: float = Query(45, gt=0, le=1000, allow_inf_nan=False), at: datetime | None = None):
    try:
        return service.simulate(lane_code=laneCode, port_code=portCode, hours_to_risk=hoursToRisk,
            speed=speedKn, closure_hours=closureHours, severity=severity, wave_m=waveM,
            charter_day=charterUsdDay, bunker_price=bunkerUsdTonne, fuel_burn=fuelTonnesDay, at=at, risk_chokepoint=riskChokepoint)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from None

@router.get("/weather-feedback")
def feedback(portCode: str, variable: Literal["wind_speed", "wind_gust", "rainfall", "wave_height", "visibility"] = "wind_speed", at: datetime | None = None):
    from src.utils import port_registry
    from src.portwatch_os.learning.weather_feedback import WeatherFeedback
    from src.portwatch_os.ledger.store import get_ledger
    from src.portwatch_os.clock import wall_now
    from src.portwatch_os.learning.weather_feedback import instant
    port = port_registry.resolve(portCode)
    if not port:
        raise HTTPException(404, "Port is not registered")
    try:
        # wall-clock: public observation availability is bounded by actual receipt time.
        moment = min(instant(at) if at else wall_now(), wall_now())
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from None
    return WeatherFeedback(get_ledger()).report(port.locode, limit=5, variable=variable, now=moment, public_only=True)
