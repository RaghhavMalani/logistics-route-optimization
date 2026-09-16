"""Central configuration for the maritime logistics forecasting system.

Everything that other modules need to agree on lives here:
  * folder layout (data/, outputs/, ...)
  * the canonical list of Indian ports and their static attributes
  * regime definitions
  * default forecast horizon

Keeping these in one place means the experts, the HSMM and the TFT/baseline
all speak the same vocabulary (same port_id values, same date column, etc.).
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
# config.py lives in <project>/src/utils/, so the project root is three levels up.
PROJECT_ROOT: Path = Path(__file__).resolve().parents[2]

DATA_DIR: Path = PROJECT_ROOT / "data"
RAW_DIR: Path = DATA_DIR / "raw"
PROCESSED_DIR: Path = DATA_DIR / "processed"
SAMPLE_DIR: Path = DATA_DIR / "sample"
# The repo already ships real preprocessed CSVs here; loaders auto-detect them.
PREPROCESSED_DIR: Path = DATA_DIR / "preprocessed"

OUTPUTS_DIR: Path = PROJECT_ROOT / "outputs"
# Durable state -- the decision ledger, the advisory register, the operator's
# cost assumptions -- lives here. It defaults to outputs/ so a checkout works
# unchanged, and a container host points PORTWATCH_STATE_DIR at a persistent
# volume so a restart or a redeploy keeps what people decided. Caches and
# pipeline artefacts are rebuildable and stay where they are.
STATE_DIR: Path = Path(os.environ.get("PORTWATCH_STATE_DIR") or OUTPUTS_DIR).expanduser()
EXPERT_FEATURES_DIR: Path = OUTPUTS_DIR / "expert_features"
REGIMES_DIR: Path = OUTPUTS_DIR / "regimes"
FORECASTS_DIR: Path = OUTPUTS_DIR / "forecasts"
ANALYTICS_DIR: Path = OUTPUTS_DIR / "analytics"

ALL_DIRS: List[Path] = [
    RAW_DIR,
    PROCESSED_DIR,
    SAMPLE_DIR,
    EXPERT_FEATURES_DIR,
    REGIMES_DIR,
    FORECASTS_DIR,
    ANALYTICS_DIR,
]


def ensure_dirs() -> None:
    """Create every output/data directory if it does not already exist."""
    for d in ALL_DIRS:
        d.mkdir(parents=True, exist_ok=True)


# ---------------------------------------------------------------------------
# Canonical column names (single source of truth)
# ---------------------------------------------------------------------------
PORT_ID = "port_id"
DATE = "date"
HORIZON = "horizon_day"

# ---------------------------------------------------------------------------
# Forecast configuration
# ---------------------------------------------------------------------------
FORECAST_HORIZON_DAYS: int = 10          # forecast 1..10 days ahead
QUANTILES: List[float] = [0.1, 0.5, 0.9]  # q10 / q50 / q90

# Forecast targets. The first one is the "primary" target and is always
# produced; the others are optional and only forecast if present in the data.
PRIMARY_TARGET = "congestion_index"
FORECAST_TARGETS: List[str] = ["congestion_index", "delay_hours", "throughput"]


# ---------------------------------------------------------------------------
# Operational regimes (used by the HSMM)
# ---------------------------------------------------------------------------
REGIME_NORMAL = "NORMAL"
REGIME_CONGESTED = "CONGESTED"
REGIME_SEVERE = "SEVERE"
REGIME_LABELS: List[str] = [REGIME_NORMAL, REGIME_CONGESTED, REGIME_SEVERE]

# Numeric ordering, lowest = calmest. Used to map clusters -> regimes by
# ascending mean congestion.
REGIME_ORDER: Dict[str, int] = {
    REGIME_NORMAL: 0,
    REGIME_CONGESTED: 1,
    REGIME_SEVERE: 2,
}


# ---------------------------------------------------------------------------
# Port registry (static features used by the TFT)
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class Port:
    port_id: str
    name: str
    region: str          # coast / cluster
    port_capacity: float  # relative daily capacity (TEU-equivalent, scaled)
    berth_count: int
    connectivity_score: float  # 0-1, hinterland / road-rail connectivity


# India's 12 central "major ports" + Mundra (largest non-major / Adani).
# port_capacity is a relative 0-1 scale (roughly by cargo throughput);
# values are illustrative for the prototype, not official figures.
PORTS: List[Port] = [
    # West / North-West coast
    Port("DEENDAYAL", "Deendayal (Kandla)", "West", 1.00, 14, 0.84),
    Port("MUNDRA", "Mundra (APSEZ)", "West", 0.98, 11, 0.85),
    Port("JNPT", "Jawaharlal Nehru (Nhava Sheva)", "West", 0.80, 13, 0.92),
    Port("MUMBAI", "Mumbai Port", "West", 0.45, 10, 0.80),
    Port("MORMUGAO", "Mormugao (Goa)", "West", 0.30, 6, 0.62),
    Port("NEW_MANGALORE", "New Mangalore", "West", 0.42, 7, 0.66),
    Port("COCHIN", "Cochin (Vallarpadam)", "South", 0.45, 6, 0.78),
    # East / South-East coast
    Port("TUTICORIN", "V.O. Chidambaranar (Tuticorin)", "South", 0.40, 8, 0.70),
    Port("CHENNAI", "Chennai", "East", 0.55, 8, 0.80),
    Port("KAMARAJAR", "Kamarajar (Ennore)", "East", 0.45, 7, 0.74),
    Port("VIZAG", "Visakhapatnam", "East", 0.72, 9, 0.72),
    Port("PARADIP", "Paradip", "East", 0.85, 9, 0.64),
    Port("KOLKATA", "Kolkata / Haldia", "East", 0.50, 7, 0.65),
]

PORT_IDS: List[str] = [p.port_id for p in PORTS]
PORT_BY_ID: Dict[str, Port] = {p.port_id: p for p in PORTS}

# Maps the port codes used in the shipped DGQI dataset to our canonical IDs.
DGQI_PORT_ALIASES: Dict[str, str] = {
    "APSEZ": "MUNDRA", "MUNDRA": "MUNDRA",
    "CHENNAI": "CHENNAI",
    "JNPT": "JNPT", "JNPA": "JNPT", "NHAVA SHEVA": "JNPT",
    "VIZAG": "VIZAG", "VISAKHAPATNAM": "VIZAG",
    "KOLKATA": "KOLKATA", "HALDIA": "KOLKATA", "SMP": "KOLKATA",
    "COCHIN": "COCHIN", "COCHIN PORT": "COCHIN",
    "DEENDAYAL": "DEENDAYAL", "KANDLA": "DEENDAYAL",
    "MUMBAI": "MUMBAI", "MUMBAI PORT": "MUMBAI", "BPT": "MUMBAI",
    "MORMUGAO": "MORMUGAO", "GOA": "MORMUGAO",
    "NEW MANGALORE": "NEW_MANGALORE", "MANGALORE": "NEW_MANGALORE",
    "TUTICORIN": "TUTICORIN", "VOC": "TUTICORIN", "V.O. CHIDAMBARANAR": "TUTICORIN",
    "KAMARAJAR": "KAMARAJAR", "ENNORE": "KAMARAJAR",
    "PARADIP": "PARADIP",
}


def static_features_frame():
    """Return port static features as a tidy DataFrame (imported lazily)."""
    import pandas as pd

    rows = [
        {
            PORT_ID: p.port_id,
            "name": p.name,
            "region": p.region,
            "port_capacity": p.port_capacity,
            "berth_count": p.berth_count,
            "connectivity_score": p.connectivity_score,
        }
        for p in PORTS
    ]
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# Reproducibility
# ---------------------------------------------------------------------------
RANDOM_SEED: int = 42


@dataclass
class DemoConfig:
    """Knobs for the synthetic-sample demo run."""

    start_date: str = "2022-01-01"
    n_days: int = 240
    horizon: int = FORECAST_HORIZON_DAYS
    seed: int = RANDOM_SEED
    port_ids: List[str] = field(default_factory=lambda: list(PORT_IDS))
