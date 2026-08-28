from __future__ import annotations

from fastapi import APIRouter

router = APIRouter()


@router.get("/fleet")
def fleet() -> list[dict]:
    return [
        {
            "id": "MV-KONKAN",
            "name": "MV Konkan",
            "type": "Container",
            "destinationPortCode": "INNSA",
            "eta": "T+36h",
            "status": "en route",
            "risk": "medium",
            "recommendedAction": "Maintain schedule with buffer.",
            "confidence": 0.84,
        },
        {
            "id": "MV-COROMANDEL",
            "name": "MV Coromandel",
            "type": "Bulk Carrier",
            "destinationPortCode": "INMAA",
            "eta": "T+48h",
            "status": "slow steaming",
            "risk": "high",
            "recommendedAction": "Consider arrival staggering for Chennai.",
            "confidence": 0.82,
        },
        {
            "id": "MV-MALABAR",
            "name": "MV Malabar",
            "type": "Tanker",
            "destinationPortCode": "INCOK",
            "eta": "T+24h",
            "status": "approach",
            "risk": "low",
            "recommendedAction": "Proceed with standard buffer.",
            "confidence": 0.86,
        },
    ]