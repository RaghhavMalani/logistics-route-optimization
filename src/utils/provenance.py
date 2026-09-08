"""Data provenance, freshness and honesty registry.

Every connector and expert declares where its data actually came from. Nothing
in this system is allowed to present a synthetic fallback as live telemetry, so
each source carries an explicit state:

    LIVE          fetched from the provider inside this run, observation recent
    CACHED_LIVE   real provider data replayed from the local cache, still inside
                  the freshness budget
    STALE         real provider data, but older than the freshness budget --
                  usable with a reduced confidence, and labelled as such
    SYNTHETIC     modelled or generated stand-in; never presented as measured
    UNAVAILABLE   the source failed and no usable fallback exists

Each record also carries the two timestamps that matter operationally --
``observed_at`` (when the world produced the data) and ``fetched_at`` (when we
retrieved it) -- plus the age, a confidence multiplier and the fallback that was
used. :func:`snapshot` serialises the whole registry so the API and the terminal
UI can render exactly the same truth the pipeline saw.
"""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Optional

from src.utils.config import ANALYTICS_DIR, DATA_DIR

LIVE = "LIVE"
CACHED_LIVE = "CACHED_LIVE"
STALE = "STALE"
SYNTHETIC = "SYNTHETIC"
UNAVAILABLE = "UNAVAILABLE"

#: Retained so older call sites keep working.
CACHE = CACHED_LIVE

#: How much each state is trusted when a source feeds a downstream confidence.
STATE_CONFIDENCE: Dict[str, float] = {
    LIVE: 1.00,
    CACHED_LIVE: 0.90,
    STALE: 0.55,
    SYNTHETIC: 0.30,
    UNAVAILABLE: 0.00,
}

#: A source older than this many hours is downgraded to STALE.
DEFAULT_FRESHNESS_HOURS = 36.0

_REAL_STATES = (LIVE, CACHED_LIVE, STALE)


@dataclass
class SourceRecord:
    """One declared data source and everything needed to audit it."""

    source: str
    status: str
    provider: str = ""
    detail: str = ""
    observed_at: Optional[str] = None
    fetched_at: Optional[str] = None
    age_seconds: Optional[int] = None
    freshness_budget_hours: float = DEFAULT_FRESHNESS_HOURS
    confidence: float = 0.0
    fallback: Optional[str] = None
    rows: Optional[int] = None
    recorded_at: str = field(default_factory=lambda: _now().isoformat())

    def to_dict(self) -> dict:
        payload = asdict(self)
        payload["isReal"] = self.status in _REAL_STATES
        payload["ageHours"] = (round(self.age_seconds / 3600.0, 2)
                               if self.age_seconds is not None else None)
        return payload


_STATE: Dict[str, SourceRecord] = {}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _parse(ts) -> Optional[datetime]:
    """Best-effort parse of anything a connector might hand us as a timestamp."""
    if ts is None:
        return None
    if isinstance(ts, datetime):
        return ts if ts.tzinfo else ts.replace(tzinfo=timezone.utc)
    try:
        import pandas as pd

        parsed = pd.to_datetime(ts, errors="coerce", utc=True)
        if parsed is None or (hasattr(parsed, "__len__") and len(parsed) == 0):
            return None
        if pd.isna(parsed):
            return None
        return parsed.to_pydatetime()
    except Exception:
        return None


def reset() -> None:
    """Clear the registry (used at the start of a pipeline run and in tests)."""
    _STATE.clear()


def record(source: str,
           status: str,
           detail: str = "",
           *,
           provider: str = "",
           observed_at=None,
           fetched_at=None,
           freshness_hours: float = DEFAULT_FRESHNESS_HOURS,
           fallback: Optional[str] = None,
           rows: Optional[int] = None,
           confidence: Optional[float] = None) -> SourceRecord:
    """Register a source. Returns the stored record (with the resolved state).

    A source declared LIVE or CACHED_LIVE whose newest observation is older than
    ``freshness_hours`` is automatically downgraded to STALE -- the system can
    never claim freshness it does not have.
    """
    status = _normalise_status(status)
    observed = _parse(observed_at)
    fetched = _parse(fetched_at) or _now()

    age_seconds = None
    if observed is not None:
        age_seconds = max(0, int((_now() - observed).total_seconds()))
        if status in (LIVE, CACHED_LIVE) and age_seconds > freshness_hours * 3600:
            status = STALE

    resolved_confidence = (STATE_CONFIDENCE.get(status, 0.0)
                           if confidence is None else float(confidence))

    entry = SourceRecord(
        source=source,
        status=status,
        provider=provider,
        detail=detail,
        observed_at=observed.isoformat() if observed else None,
        fetched_at=fetched.isoformat(),
        age_seconds=age_seconds,
        freshness_budget_hours=freshness_hours,
        confidence=round(resolved_confidence, 3),
        fallback=fallback,
        rows=rows,
    )
    _STATE[source] = entry
    return entry


def _normalise_status(status: str) -> str:
    key = str(status or "").strip().upper()
    if key in STATE_CONFIDENCE:
        return key
    # Tolerate the older lowercase vocabulary ("live", "cache", "synthetic").
    return {
        "LIVE": LIVE, "CACHE": CACHED_LIVE, "CACHED": CACHED_LIVE,
        "SYNTHETIC": SYNTHETIC, "STALE": STALE,
    }.get(key, UNAVAILABLE)


def get(source: str) -> Optional[SourceRecord]:
    return _STATE.get(source)


def get_all() -> Dict[str, dict]:
    return {name: entry.to_dict() for name, entry in _STATE.items()}


def by_status(status: str) -> list[str]:
    target = _normalise_status(status)
    return sorted(name for name, e in _STATE.items() if e.status == target)


def readiness_score() -> float:
    """Confidence-weighted fraction of sources backed by real measurements."""
    if not _STATE:
        return 0.0
    total = sum(STATE_CONFIDENCE.get(e.status, 0.0) for e in _STATE.values())
    return round(total / len(_STATE), 3)


def has_synthetic() -> bool:
    return any(e.status == SYNTHETIC for e in _STATE.values())


def snapshot() -> dict:
    """The full provenance payload the API and UI render."""
    return {
        "generatedAt": _now().isoformat(),
        "readiness": readiness_score(),
        "counts": {
            state: len(by_status(state))
            for state in (LIVE, CACHED_LIVE, STALE, SYNTHETIC, UNAVAILABLE)
        },
        "live": by_status(LIVE),
        "cached": by_status(CACHED_LIVE),
        "stale": by_status(STALE),
        "synthetic": by_status(SYNTHETIC),
        "unavailable": by_status(UNAVAILABLE),
        "sources": get_all(),
    }


def save(extra: Optional[dict] = None) -> Path:
    """Persist the registry for the API layer and for post-run auditing."""
    payload = snapshot()
    if extra:
        payload.update(extra)
    ANALYTICS_DIR.mkdir(parents=True, exist_ok=True)
    (ANALYTICS_DIR / "provenance.json").write_text(
        json.dumps(payload, indent=2), encoding="utf-8")

    cache_dir = DATA_DIR / "cache"
    cache_dir.mkdir(parents=True, exist_ok=True)
    path = cache_dir / "provenance.json"
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return path


def load(path: Optional[Path] = None) -> dict:
    """Read a persisted snapshot (used by the API when no run is in memory)."""
    path = path or (DATA_DIR / "cache" / "provenance.json")
    if not os.path.exists(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, json.JSONDecodeError):
        return {}
