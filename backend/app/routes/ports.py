from __future__ import annotations

from fastapi import APIRouter, HTTPException

from backend.app.services.cache_service import (
    CacheNotReadyError,
    get_forecast_by_port,
    get_regime_by_port,
)

router = APIRouter()


PORT_META = {
    "INMAA": {
        "name": "Chennai",
        "short": "Chennai",
        "authority": "Chennai Port Authority",
        "location": {"lat": 13.10, "lon": 80.30},
        "radar": {"x": 0.72, "y": 0.55},
        "schematic": {"x": 720, "y": 380},
        "coast": "east",
    },
    "INNSA": {
        "name": "JNPT / Nhava Sheva",
        "short": "JNPT",
        "authority": "Jawaharlal Nehru Port Authority",
        "location": {"lat": 18.95, "lon": 72.95},
        "radar": {"x": 0.42, "y": 0.45},
        "schematic": {"x": 420, "y": 310},
        "coast": "west",
    },
    "INMUN": {
        "name": "Mundra",
        "short": "Mundra",
        "authority": "APSEZ Mundra Port",
        "location": {"lat": 22.74, "lon": 69.70},
        "radar": {"x": 0.34, "y": 0.36},
        "schematic": {"x": 340, "y": 260},
        "coast": "west",
    },
    "INCOK": {
        "name": "Cochin",
        "short": "Cochin",
        "authority": "Cochin Port Authority",
        "location": {"lat": 9.97, "lon": 76.27},
        "radar": {"x": 0.55, "y": 0.68},
        "schematic": {"x": 550, "y": 470},
        "coast": "west",
    },
    "INHAL": {
        "name": "Haldia",
        "short": "Haldia",
        "authority": "Syama Prasad Mookerjee Port",
        "location": {"lat": 22.07, "lon": 88.10},
        "radar": {"x": 0.83, "y": 0.43},
        "schematic": {"x": 830, "y": 305},
        "coast": "east",
    },
    "INHZR": {
        "name": "Hazira",
        "short": "Hazira",
        "authority": "Hazira Port",
        "location": {"lat": 21.10, "lon": 72.62},
        "radar": {"x": 0.40, "y": 0.40},
        "schematic": {"x": 400, "y": 285},
        "coast": "west",
    },
    "INIXY": {
        "name": "Deendayal / Kandla",
        "short": "Kandla",
        "authority": "Deendayal Port Authority",
        "location": {"lat": 23.02, "lon": 70.22},
        "radar": {"x": 0.35, "y": 0.34},
        "schematic": {"x": 350, "y": 245},
        "coast": "west",
    },
    "INKAT": {
        "name": "Kattupalli",
        "short": "Kattupalli",
        "authority": "Kattupalli Port",
        "location": {"lat": 13.28, "lon": 80.33},
        "radar": {"x": 0.72, "y": 0.54},
        "schematic": {"x": 725, "y": 370},
        "coast": "east",
    },
    "INKRI": {
        "name": "Krishnapatnam",
        "short": "Krishnapatnam",
        "authority": "Krishnapatnam Port",
        "location": {"lat": 14.27, "lon": 80.12},
        "radar": {"x": 0.71, "y": 0.51},
        "schematic": {"x": 710, "y": 350},
        "coast": "east",
    },
    "INCCU": {
        "name": "Kolkata",
        "short": "Kolkata",
        "authority": "Syama Prasad Mookerjee Port",
        "location": {"lat": 22.55, "lon": 88.31},
        "radar": {"x": 0.84, "y": 0.42},
        "schematic": {"x": 840, "y": 295},
        "coast": "east",
    },
    "INNML": {
        "name": "New Mangalore",
        "short": "New Mangalore",
        "authority": "New Mangalore Port Authority",
        "location": {"lat": 12.92, "lon": 74.80},
        "radar": {"x": 0.52, "y": 0.60},
        "schematic": {"x": 520, "y": 420},
        "coast": "west",
    },
    "INTUT": {
        "name": "Tuticorin",
        "short": "Tuticorin",
        "authority": "V.O. Chidambaranar Port Authority",
        "location": {"lat": 8.75, "lon": 78.20},
        "radar": {"x": 0.66, "y": 0.72},
        "schematic": {"x": 660, "y": 500},
        "coast": "south",
    },
    "INVTZ": {
        "name": "Visakhapatnam",
        "short": "Vizag",
        "authority": "Visakhapatnam Port Authority",
        "location": {"lat": 17.69, "lon": 83.22},
        "radar": {"x": 0.78, "y": 0.46},
        "schematic": {"x": 780, "y": 325},
        "coast": "east",
    },
}


def risk_from_severity(severity: str) -> str:
    severity = severity.upper()

    if severity == "SEVERE":
        return "severe"

    if severity in {"HIGH", "MOD"}:
        return "congested"

    return "normal"


def build_port_snapshot(
    port_code: str,
    forecast_rows: list[dict],
    regime: dict | None,
) -> dict:
    if not forecast_rows:
        raise HTTPException(
            status_code=404,
            detail=f"No forecast rows available for port: {port_code}",
        )

    meta = PORT_META.get(
        port_code,
        {
            "name": port_code,
            "short": port_code,
            "authority": "Unknown Port Authority",
            "location": {"lat": 0.0, "lon": 0.0},
            "radar": {"x": 0.5, "y": 0.5},
            "schematic": {"x": 500, "y": 350},
            "coast": "unknown",
        },
    )

    rows = sorted(forecast_rows, key=lambda x: int(x.get("day", 1)))
    day1 = rows[0]
    peak = max(rows, key=lambda x: float(x.get("congestionIndex", 0.0)))

    day1_congestion = float(day1.get("congestionIndex", 0.0))
    peak_congestion = float(peak.get("congestionIndex", day1_congestion))
    peak_severity = str(peak.get("severity", "LOW"))

    regime_state = "NORMAL"
    confidence = 0.82

    if regime:
        regime_state = str(regime.get("state", "NORMAL"))
        confidence = float(regime.get("confidence", confidence))

    delay_hours = float(day1.get("delayHoursP95", 0.0))

    # These two are operational display proxies derived from TFT congestion.
    throughput = int(max(1000, 10000 - peak_congestion * 100))
    vessels = int(max(10, 85 - peak_congestion))

    return {
        "code": port_code,
        "name": meta["name"],
        "short": meta["short"],
        "authority": meta["authority"],
        "location": meta["location"],
        "radar": meta["radar"],
        "schematic": meta["schematic"],
        "coast": meta["coast"],

        # Derived from TFT forecast cache.
        "risk": risk_from_severity(peak_severity),
        "congestion": round(day1_congestion / 100.0, 3),
        "congestionIndex": round(day1_congestion, 1),
        "peakCongestionIndex": round(peak_congestion, 1),
        "delayHours": round(delay_hours, 1),
        "throughput": throughput,
        "vessels": vessels,
        "confidence": round(confidence, 3),
        "regime": regime_state,
        "updatedAt": day1.get("dateLabel", "live"),

        # Extra explanation fields for debugging/demo honesty.
        "dataSource": "TFT forecast cache",
        "model": "tft",
        "forecastHorizonDays": len(rows),
    }


@router.get("/ports")
def list_ports() -> list[dict]:
    try:
        forecasts = get_forecast_by_port()
        regimes = get_regime_by_port()

        snapshots = [
            build_port_snapshot(
                port_code=port_code,
                forecast_rows=forecast_rows,
                regime=regimes.get(port_code),
            )
            for port_code, forecast_rows in forecasts.items()
        ]

        return sorted(snapshots, key=lambda x: x["name"])

    except CacheNotReadyError as exc:
        raise HTTPException(status_code=503, detail=str(exc))


@router.get("/ports/{port_code}")
def get_port(port_code: str) -> dict:
    port_code = port_code.upper()

    try:
        forecasts = get_forecast_by_port()
        regimes = get_regime_by_port()

        if port_code not in forecasts:
            raise HTTPException(
                status_code=404,
                detail=f"Port not found in TFT forecast cache: {port_code}",
            )

        return build_port_snapshot(
            port_code=port_code,
            forecast_rows=forecasts[port_code],
            regime=regimes.get(port_code),
        )

    except CacheNotReadyError as exc:
        raise HTTPException(status_code=503, detail=str(exc))