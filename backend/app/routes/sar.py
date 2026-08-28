from __future__ import annotations

from fastapi import APIRouter

router = APIRouter()


VESSELS = [
    {
        "id": "AIS-001",
        "vesselType": "CONT",
        "location": {"lat": 13.22, "lon": 80.35},
        "radar": {"x": 0.72, "y": 0.55},
        "schematic": {"x": 720, "y": 360},
        "destinationPortCode": "INMAA",
        "status": "waiting",
        "eta": "T+18h",
        "heading": 282,
        "speedKnots": 6.2,
        "flag": "IN",
        "source": "AIS_SAR",
        "confidence": 0.84,
    },
    {
        "id": "AIS-002",
        "vesselType": "TANKER",
        "location": {"lat": 18.98, "lon": 72.91},
        "radar": {"x": 0.43, "y": 0.46},
        "schematic": {"x": 430, "y": 310},
        "destinationPortCode": "INNSA",
        "status": "approach",
        "eta": "T+10h",
        "heading": 110,
        "speedKnots": 9.4,
        "flag": "SG",
        "source": "AIS",
        "confidence": 0.88,
    },
]


@router.get("/sar/vessels")
def sar_vessels() -> dict:
    return {
        "vessels": VESSELS,
        "updatedAt": "live",
    }


@router.get("/sar/feed-adapters")
def sar_feed_adapters() -> list[dict]:
    return [
        {
            "key": "AIS",
            "name": "AIS Feed",
            "status": "online",
            "confidence": 0.88,
            "lastUpdated": "live",
        },
        {
            "key": "SAR",
            "name": "SAR Proxy Feed",
            "status": "online",
            "confidence": 0.81,
            "lastUpdated": "live",
        },
    ]


@router.get("/sar/{port_code}")
def sar_signal(port_code: str) -> dict:
    port_code = port_code.upper()

    port_vessels = [v for v in VESSELS if v["destinationPortCode"] == port_code]

    return {
        "portCode": port_code,
        "sceneId": f"SAR-{port_code}-LATEST",
        "timestamp": "live",
        "vesselDetections": max(12, len(port_vessels) * 12),
        "anchorageCount": max(4, len(port_vessels) * 5),
        "changeScore": 0.58,
        "confidence": 0.81,
        "aisActive": max(8, len(port_vessels) * 8),
        "sarOnly": max(2, len(port_vessels) * 2),
        "darkVessels": 4,
        "crossMatchRate": 0.74,
        "boundingIou": 0.69,
        "headingAgreement": 0.77,
    }