"""Pure compatibility parser for retained public intelligence timestamps.

Kept independent of collector/cache initialization for read-only projections.
"""
from datetime import datetime, timezone


def instant(value):
    dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt.astimezone(timezone.utc)
