from __future__ import annotations

from fastapi import APIRouter

router = APIRouter()


SCENARIOS = [
    {
        "key": "STORM_W",
        "commandAlias": "storm-west",
        "name": "Storm near west coast",
        "desc": "Severe monsoon storm tracking along Arabian Sea.",
        "icon": "cloud-rain",
        "affectedCoasts": ["west"],
        "baseCongestionDelta": 22,
        "baseDelayDeltaHours": 5.8,
        "baseThroughputDelta": -9,
        "baseFreightDelta": 4.2,
        "affectedPorts": ["INNSA", "INMUN", "INCOK"],
    },
    {
        "key": "CYC_E",
        "commandAlias": "cyclone-east",
        "name": "Cyclone near east coast",
        "desc": "Bay of Bengal cyclone approaching Chennai-Vizag corridor.",
        "icon": "cyclone",
        "affectedCoasts": ["east"],
        "baseCongestionDelta": 28,
        "baseDelayDeltaHours": 7.0,
        "baseThroughputDelta": -13,
        "baseFreightDelta": 5.1,
        "affectedPorts": ["INMAA", "INVTZ", "INKAT"],
    },
    {
        "key": "LABOUR",
        "commandAlias": "labour-strike",
        "name": "Labour strike",
        "desc": "Port workers' strike reducing gate and yard operations.",
        "icon": "user-x",
        "affectedCoasts": ["west", "east"],
        "baseCongestionDelta": 18,
        "baseDelayDeltaHours": 4.2,
        "baseThroughputDelta": -10,
        "baseFreightDelta": 2.7,
        "affectedPorts": ["INNSA", "INMAA"],
    },
    {
        "key": "CAPDROP",
        "commandAlias": "capacity-drop",
        "name": "Port capacity drop",
        "desc": "Unplanned berth/crane outage reducing handling capacity.",
        "icon": "crane",
        "affectedCoasts": ["west", "east"],
        "baseCongestionDelta": 20,
        "baseDelayDeltaHours": 5.0,
        "baseThroughputDelta": -20,
        "baseFreightDelta": 3.5,
        "affectedPorts": ["INNSA", "INMUN", "INMAA"],
    },
    {
        "key": "DEMAND",
        "commandAlias": "demand-surge",
        "name": "Demand surge",
        "desc": "Festival or quarter-end cargo demand surge.",
        "icon": "bar-chart",
        "affectedCoasts": ["west", "east"],
        "baseCongestionDelta": 15,
        "baseDelayDeltaHours": 3.2,
        "baseThroughputDelta": -5,
        "baseFreightDelta": 2.5,
        "affectedPorts": ["INNSA", "INMUN", "INMAA", "INVTZ"],
    },
    {
        "key": "HORMUZ",
        "commandAlias": "hormuz",
        "name": "Hormuz closure",
        "desc": "Strait of Hormuz closure affecting Gulf crude/LNG traffic.",
        "icon": "route",
        "affectedCoasts": ["west"],
        "baseCongestionDelta": 26,
        "baseDelayDeltaHours": 6.4,
        "baseThroughputDelta": -11,
        "baseFreightDelta": 6.0,
        "affectedPorts": ["INMUN", "INNSA", "INCOK"],
    },
    {
        "key": "REDSEA",
        "commandAlias": "red-sea",
        "name": "Red Sea disruption",
        "desc": "Bab-el-Mandeb/Suez route disruption.",
        "icon": "ship",
        "affectedCoasts": ["west"],
        "baseCongestionDelta": 24,
        "baseDelayDeltaHours": 6.0,
        "baseThroughputDelta": -10,
        "baseFreightDelta": 5.5,
        "affectedPorts": ["INNSA", "INMUN", "INCOK"],
    },
    {
        "key": "FUEL",
        "commandAlias": "fuel-price",
        "name": "Fuel price shock",
        "desc": "Brent spike increasing bunker and freight cost pressure.",
        "icon": "fuel",
        "affectedCoasts": ["west", "east"],
        "baseCongestionDelta": 8,
        "baseDelayDeltaHours": 1.5,
        "baseThroughputDelta": -2,
        "baseFreightDelta": 7.5,
        "affectedPorts": ["INNSA", "INMUN", "INMAA"],
    },
]


PORT_NAMES = {
    "INNSA": "JNPT / Nhava Sheva",
    "INMUN": "Mundra",
    "INCOK": "Cochin",
    "INMAA": "Chennai",
    "INVTZ": "Visakhapatnam",
    "INKAT": "Kattupalli",
}


def risk_level(score: float) -> str:
    if score >= 75:
        return "severe"
    if score >= 55:
        return "high"
    if score >= 30:
        return "medium"
    return "normal"


@router.get("/scenarios")
def list_scenarios() -> list[dict]:
    return SCENARIOS


@router.post("/scenarios/simulate")
def simulate_scenario(payload: dict) -> dict:
    scenario_key = (
        payload.get("scenarioKey")
        or payload.get("scenarioId")
        or payload.get("id")
        or payload.get("scenario")
        or "STORM_W"
    )

    intensity = float(
        payload.get("intensity")
        or payload.get("scenarioIntensity")
        or payload.get("multiplier")
        or 1.0
    )

    run_id = int(payload.get("runId") or 1247)

    scenario = next((s for s in SCENARIOS if s["key"] == scenario_key), None)
    if scenario is None:
        scenario = SCENARIOS[0]

    congestion_delta = round(float(scenario["baseCongestionDelta"]) * intensity, 1)
    delay_delta_hours = round(float(scenario["baseDelayDeltaHours"]) * intensity, 1)
    throughput_delta = round(float(scenario["baseThroughputDelta"]) * intensity, 1)
    freight_delta = round(float(scenario["baseFreightDelta"]) * intensity, 1)

    overall_score = min(99.0, max(0.0, congestion_delta * 2.0))
    overall_risk = risk_level(overall_score)

    affected_ports = []
    for idx, code in enumerate(scenario["affectedPorts"], start=1):
        scale = max(0.55, 1.0 - idx * 0.08)
        port_congestion = round(congestion_delta * scale, 1)
        port_delay = round(delay_delta_hours * scale, 1)
        port_throughput = round(throughput_delta * scale, 1)
        impact_score = int(min(99, max(20, port_congestion * 2.0)))

        affected_ports.append(
            {
                "portCode": code,
                "name": PORT_NAMES.get(code, code),
                "impactScore": impact_score,
                "riskLevel": risk_level(impact_score),
                "congestionDelta": port_congestion,
                "delayDeltaHours": port_delay,
                "throughputDelta": port_throughput,
            }
        )

    route_impacts = [
        {
            "name": "West Coast Route",
            "delayDeltaHours": round(delay_delta_hours * 0.85, 1),
            "riskLevel": overall_risk if "west" in scenario["affectedCoasts"] else "medium",
        },
        {
            "name": "East Coast Route",
            "delayDeltaHours": round(delay_delta_hours * 0.65, 1),
            "riskLevel": overall_risk if "east" in scenario["affectedCoasts"] else "medium",
        },
    ]

    chokepoint_impacts = [
        {
            "name": "Strait of Hormuz",
            "riskLevel": "high" if scenario["key"] == "HORMUZ" else "medium",
        },
        {
            "name": "Bab-el-Mandeb",
            "riskLevel": "high" if scenario["key"] == "REDSEA" else "medium",
        },
        {
            "name": "Malacca Strait",
            "riskLevel": "medium",
        },
        {
            "name": "Suez Canal",
            "riskLevel": "high" if scenario["key"] == "REDSEA" else "normal",
        },
    ]

    recommendation = {
        "id": f"REC-{scenario['key']}-{run_id}",
        "scenarioKey": scenario["key"],
        "severity": overall_risk,
        "title": "Protect critical calls and update ETA guidance",
        "actions": [
            "Move discretionary calls to safer operating windows.",
            "Stagger inbound ETA by 24-48h for high-risk vessels.",
            "Reserve yard capacity for priority cargo classes.",
            "Push updated delay guidance to fleet operators.",
        ],
        "rationale": (
            f"{scenario['name']} at {intensity:.1f}x intensity increases "
            f"congestion by {congestion_delta:.1f} points and delay by "
            f"{delay_delta_hours:.1f} hours."
        ),
        "confidence": 0.82,
        "timestamp": "live",
    }

    return {
        "scenarioKey": scenario["key"],
        "scenarioName": scenario["name"],
        "intensity": intensity,
        "runId": run_id,
        "affectedPorts": affected_ports,
        "congestionDelta": congestion_delta,
        "delayDeltaHours": delay_delta_hours,
        "throughputDelta": throughput_delta,
        "freightDelta": freight_delta,
        "riskLevel": overall_risk,
        "recommendation": recommendation,
        "routeImpacts": route_impacts,
        "chokepointImpacts": chokepoint_impacts,

        # Extra aliases are harmless and useful for debugging.
        "id": scenario["key"],
        "name": scenario["name"],
        "summary": f"{scenario['name']} simulated at {intensity:.1f}x intensity.",
    }
