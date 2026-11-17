"""Measure Open-Meteo transport and end-of-hour port coverage from a preview volume."""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
import json
from math import isfinite
from pathlib import Path
import sqlite3

from src.utils.port_registry import PORTS

HOUR = timedelta(hours=1)
FIELDS = ("wind_speed_10m", "wind_gusts_10m", "wind_direction_10m", "precipitation", "visibility")


def instant(value):
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)


def attempt_outcomes(journal, artifact, start, end):
    with sqlite3.connect(journal.resolve().as_uri() + "?mode=ro", uri=True) as db:
        db.execute("PRAGMA query_only=ON")
        rows = db.execute(
            "SELECT ok, result FROM refresh_attempts WHERE artifact=? AND skipped=0 "
            "AND finished>=? AND finished<? ORDER BY finished",
            (artifact, start.isoformat(), end.isoformat()),
        ).fetchall()
    failures = Counter()
    successful = 0
    for ok, rendered in rows:
        result = json.loads(rendered)
        attempts = result.get("detail", {}).get("httpAttempts")
        if attempts is not None:
            successful += attempts.get("ok", 0)
            failures.update({key: count for key, count in attempts.items() if key != "ok"})
        elif ok:
            successful += 1
        else:
            error = result.get("error") or "unspecified"
            kind = "HTTP 429" if "HTTP 429" in error else "timeout" if "timed out" in error.lower() else error.split(":", 1)[0]
            failures[kind] += 1
    return {"total": successful + sum(failures.values()), "successful": successful, "failures": failures}


def cycle_coverage(archive, start, end):
    ports = {port.locode for port in PORTS}
    snapshots = defaultdict(list)
    for path in archive.glob("*.json"):
        data = json.loads(path.read_text(encoding="utf-8"))
        if data.get("kind") != "surface" or data["portCode"] not in ports:
            continue
        available = instant(data["availableAt"])
        fetched = instant(data["fetchedAt"])
        if fetched < end:
            hours = {
                instant(row["validAt"]) for row in data["rows"]
                if all(type(row.get(key)) in (int, float) and isfinite(row[key]) for key in FIELDS)
            }
            snapshots[data["portCode"]].append((fetched, available, hours))
    cycles = []
    close = start + HOUR
    while close <= end:
        hour = close - HOUR
        missing = []
        stale = []
        retained_only = []
        for port in sorted(ports):
            candidates = (row for row in snapshots[port] if row[0] < close)
            latest = max(candidates, key=lambda row: row[0], default=None)
            if latest is None or latest[0] < hour or hour not in latest[2]:
                missing.append(port)
            if latest is None or latest[1] < hour or hour not in latest[2]:
                stale.append(port)
            if latest is not None and latest[0] < hour and hour in latest[2]:
                retained_only.append(port)
        cycles.append({"end": close.isoformat(), "portsWithData": len(ports) - len(missing), "missing": missing,
                       "portsRetainedOnly": len(retained_only), "portsWithinAvailabilityPolicy": len(ports) - len(stale)})
        close += HOUR
    return {"total": len(cycles), "successful": sum(not cycle["missing"] for cycle in cycles),
            "allPortsWithinAvailabilityPolicy": sum(cycle["portsWithinAvailabilityPolicy"] == len(ports) for cycle in cycles),
            "ports": len(ports), "cycles": cycles}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--start", type=instant, required=True)
    parser.add_argument("--end", type=instant, required=True)
    parser.add_argument("--state", type=Path, required=True)
    parser.add_argument("--artifact", default="current_surface_batch")
    args = parser.parse_args()
    start, end = args.start, args.end
    if any(time.minute or time.second or time.microsecond for time in (start, end)):
        parser.error("start and end must be on UTC hour boundaries")
    if end - start < 12 * HOUR or datetime.now(timezone.utc) < end:
        parser.error("wait for all twelve or more observation hours to finish")
    print(json.dumps({"start": start.isoformat(), "end": end.isoformat(),
                      "attempts": attempt_outcomes(args.state / "live/freshness.sqlite3", args.artifact, start, end),
                      "cycles": cycle_coverage(args.state / "current_environment/archive", start, end)}))


if __name__ == "__main__":
    main()

