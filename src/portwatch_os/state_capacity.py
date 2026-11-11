"""Capacity policy for the filesystem holding durable state."""

import shutil
from pathlib import Path

MIN_FREE_PERCENT = 20


def state_capacity(path: Path) -> dict:
    try:
        total, _, free = shutil.disk_usage(path)
    except OSError:
        return {"totalBytes": None, "freeBytes": None, "freePercent": None,
                "minimumFreePercent": MIN_FREE_PERCENT, "status": "unavailable"}
    return {
        "totalBytes": total,
        "freeBytes": free,
        "freePercent": round(100 * free / total, 2) if total else None,
        "minimumFreePercent": MIN_FREE_PERCENT,
        "status": "ok" if total and 100 * free >= MIN_FREE_PERCENT * total else "low",
    }


def require_capacity(capacity: dict, *, copy_bytes: int = 0) -> None:
    """Reject an unmeasurable volume or a backup that would consume the reserve."""
    total, free = capacity["totalBytes"], capacity["freeBytes"]
    if not total or free is None:
        raise ValueError("Cannot measure available space on the state volume")
    required = (3 * copy_bytes + 1) // 2
    if free < required:
        raise ValueError(f"Backup needs at least {required} free bytes (1.5 × state size); found {free}")
    if 100 * (free - copy_bytes) < MIN_FREE_PERCENT * total:
        raise ValueError(f"State volume must retain at least {MIN_FREE_PERCENT}% free space")
