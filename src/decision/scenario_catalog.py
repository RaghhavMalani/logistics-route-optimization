"""The scenario catalogue the Decision Room offers.

Each entry is a *typed shock* the impact model already understands, plus the
scope it acts on. Scope is what makes a local scenario work: a Hormuz closure
propagates through lane exposure, whereas a Bay of Bengal cyclone or an east
coast labour action lands directly on a set of ports.

Nothing here contains an outcome. The catalogue only says what kind of shock it
is, how severe the default setting is, and which ports are in scope; every
number the Decision Room shows is computed by the scenario engine from the live
forecast.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional


@dataclass(frozen=True)
class ScenarioSpec:
    key: str
    name: str
    description: str
    shock_type: str
    scope: str                       # chokepoint | coast | national
    default_severity: float
    chokepoint: Optional[str] = None
    coasts: tuple = ()
    duration_days: int = 14
    #: What the operator is really being asked to plan for.
    question: str = ""
    #: Real-world analogue the elasticities are calibrated against.
    analogue: str = ""

    def as_dict(self) -> dict:
        return {
            "key": self.key,
            "name": self.name,
            "desc": self.description,
            "shockType": self.shock_type,
            "scope": self.scope,
            "defaultSeverity": self.default_severity,
            "chokepoint": self.chokepoint,
            "affectedCoasts": list(self.coasts),
            "durationDays": self.duration_days,
            "question": self.question,
            "analogue": self.analogue,
        }


SCENARIOS: List[ScenarioSpec] = [
    ScenarioSpec(
        "HORMUZ", "Hormuz closure",
        "Strait of Hormuz closed to commercial traffic.",
        "chokepoint_closure", "chokepoint", 0.85, chokepoint="HORMUZ",
        coasts=("west",), duration_days=21,
        question="How much west-coast energy and berth exposure do we carry?",
        analogue="Hormuz carries roughly a fifth of seaborne oil and has no "
                 "maritime bypass, so a closure is first a price shock."),
    ScenarioSpec(
        "SUEZ", "Suez Canal blockage",
        "Suez Canal blocked; Asia-Europe traffic reroutes.",
        "chokepoint_closure", "chokepoint", 0.90, chokepoint="SUEZ",
        coasts=("west", "east"), duration_days=10,
        question="Which calls slip if Europe-bound strings add a Cape routing?",
        analogue="Ever Given, March 2021: six days of blockage, severe queueing "
                 "and a sharp container-rate response."),
    ScenarioSpec(
        "REDSEA", "Red Sea disruption",
        "Bab-el-Mandeb transits suspended; diversions via the Cape.",
        "chokepoint_closure", "chokepoint", 0.80, chokepoint="BAB_EL_MANDEB",
        coasts=("west", "east"), duration_days=30,
        question="What does a sustained Cape routing do to our arrival pattern?",
        analogue="Red Sea diversions, 2023-24: roughly ten to fourteen extra "
                 "steaming days on Asia-Europe strings."),
    ScenarioSpec(
        "MALACCA", "Malacca Strait disruption",
        "Strait of Malacca restricted; east-coast strings reroute.",
        "chokepoint_closure", "chokepoint", 0.70, chokepoint="MALACCA",
        coasts=("east",), duration_days=14,
        question="How exposed is the east coast to a single eastern lane?",
        analogue="Lombok and Sunda are the practical alternatives, at a few "
                 "extra steaming days."),
    ScenarioSpec(
        "CYC_E", "Cyclone, east coast",
        "Bay of Bengal cyclone across the Chennai-Vizag-Paradip corridor.",
        "weather_extreme", "coast", 0.80, coasts=("east",), duration_days=5,
        question="Which east-coast berth windows do we lose, and for how long?",
        analogue="Bay of Bengal systems routinely suspend east-coast pilotage "
                 "for two to four days."),
    ScenarioSpec(
        "STORM_W", "Storm, west coast",
        "Severe Arabian Sea system along the Gujarat-Maharashtra coast.",
        "weather_extreme", "coast", 0.70, coasts=("west",), duration_days=4,
        question="Do we hold arrivals at Mundra and JNPA, or re-time them?",
        analogue="Monsoon-season Arabian Sea systems degrade crane and pilotage "
                 "availability before they close a port outright."),
    ScenarioSpec(
        "CAPDROP", "Port capacity drop",
        "Unplanned berth or crane outage cutting handling capacity.",
        "strike", "coast", 0.60, coasts=("west", "east"), duration_days=7,
        question="How fast does the queue build if we lose a berth line?",
        analogue="Crane and berth outages behave like a partial labour action: "
                 "throughput falls while arrivals do not."),
    ScenarioSpec(
        "LABOUR", "Labour action",
        "Port workers' action reducing gate and yard operations.",
        "strike", "national", 0.65, coasts=("west", "east"), duration_days=5,
        question="What is the national queue exposure to a coordinated action?",
        analogue="Gate and yard slowdowns hit throughput hardest and berth "
                 "occupancy second."),
    ScenarioSpec(
        "DEMAND", "Demand surge",
        "Festival or quarter-end cargo surge across the network.",
        "conflict", "national", 0.50, coasts=("west", "east"), duration_days=14,
        question="Can the network absorb a surge without berth re-sequencing?",
        analogue="Seasonal surges raise arrivals against unchanged handling "
                 "capacity."),
    ScenarioSpec(
        "FUEL", "Fuel price shock",
        "Brent spike raising bunker and freight cost pressure.",
        "sanctions", "national", 0.55, coasts=("west", "east"), duration_days=30,
        question="Where does slow steaming become cheaper than waiting?",
        analogue="A bunker shock changes the economics of speed before it "
                 "changes the queue."),
]

BY_KEY: Dict[str, ScenarioSpec] = {spec.key: spec for spec in SCENARIOS}

#: Command-line and legacy aliases the terminal may still send.
ALIASES: Dict[str, str] = {
    "HORMUZ_CLOSURE": "HORMUZ", "HORMUZ-CLOSURE": "HORMUZ",
    "SUEZ_BLOCKAGE": "SUEZ", "SUEZ-BLOCKAGE": "SUEZ",
    "RED_SEA": "REDSEA", "RED-SEA": "REDSEA", "REDSEA_CRISIS": "REDSEA",
    "MALACCA_DISRUPTION": "MALACCA",
    "CYCLONE_EAST": "CYC_E", "CYCLONE-EAST": "CYC_E",
    "STORM_WEST": "STORM_W", "STORM-WEST": "STORM_W",
    "CAPACITY_DROP": "CAPDROP", "CAPACITY-DROP": "CAPDROP",
    "LABOUR_STRIKE": "LABOUR", "LABOR_STRIKE": "LABOUR", "STRIKE": "LABOUR",
    "DEMAND_SURGE": "DEMAND",
    "FUEL_PRICE": "FUEL", "FUEL_SHOCK": "FUEL",
}


def resolve(key: str) -> ScenarioSpec:
    """Resolve a scenario key or alias; falls back to the first entry."""
    normalised = str(key or "").strip().upper().replace(" ", "_")
    if normalised in BY_KEY:
        return BY_KEY[normalised]
    if normalised in ALIASES:
        return BY_KEY[ALIASES[normalised]]
    return SCENARIOS[0]


def catalogue() -> List[dict]:
    return [spec.as_dict() for spec in SCENARIOS]
