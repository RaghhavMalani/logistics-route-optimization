"""Operational telemetry: what the process has been doing, in numbers.

A product that computes consequence has to be able to say how it is doing
at computing it: how many world rebuilds, how many cascades were reused
rather than recomputed, how long a decision takes to build, how often the
Critic rejects, how many observations arrived stale, which providers are
failing and which refresh jobs are retrying. None of that is intelligence;
all of it is what an operator asks when the screen looks wrong.

The registry is in-process and bounded. Counters count, gauges hold the last
value, and timers keep a reservoir of recent durations from which p50, p95
and p99 are read -- enough for a diagnostics page and a benchmark, not a
time-series store. Every name is a plain dotted string, so a reader of the
diagnostics payload sees ``world.rebuilds`` rather than an opaque id.

Nothing here ever holds a secret. Values are numbers and short labels; the
diagnostics route asserts that no environment value appears in the payload.
"""

from __future__ import annotations

import threading
import time
from collections import deque
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Any, Deque, Dict, Iterator, List, Optional, Tuple

from src.portwatch_os.clock import wall_now

#: Durations kept per timer, newest last. Percentiles are read from these.
RESERVOIR = 512
#: Recent events kept per stream (errors, rejections), newest last.
EVENT_LOG = 64


def _percentile(sorted_values: List[float], fraction: float) -> Optional[float]:
    if not sorted_values:
        return None
    if len(sorted_values) == 1:
        return sorted_values[0]
    position = fraction * (len(sorted_values) - 1)
    low = int(position)
    high = min(low + 1, len(sorted_values) - 1)
    weight = position - low
    return sorted_values[low] * (1 - weight) + sorted_values[high] * weight


@dataclass
class Timer:
    name: str
    samples: Deque[float] = field(default_factory=lambda: deque(maxlen=RESERVOIR))
    count: int = 0
    total_seconds: float = 0.0
    max_seconds: float = 0.0

    def record(self, seconds: float) -> None:
        self.samples.append(seconds)
        self.count += 1
        self.total_seconds += seconds
        self.max_seconds = max(self.max_seconds, seconds)

    def summary(self) -> Dict[str, Any]:
        ordered = sorted(self.samples)
        return {
            "count": self.count,
            "meanMs": None if not self.count else round(1000.0 * self.total_seconds / self.count, 2),
            "p50Ms": None if not ordered else round(1000.0 * (_percentile(ordered, 0.50) or 0.0), 2),
            "p95Ms": None if not ordered else round(1000.0 * (_percentile(ordered, 0.95) or 0.0), 2),
            "p99Ms": None if not ordered else round(1000.0 * (_percentile(ordered, 0.99) or 0.0), 2),
            "maxMs": round(1000.0 * self.max_seconds, 2),
            "window": len(ordered),
        }


class Telemetry:
    """One process's counters, gauges, timers and recent events."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._counters: Dict[str, float] = {}
        self._gauges: Dict[str, Any] = {}
        self._timers: Dict[str, Timer] = {}
        self._events: Dict[str, Deque[Dict[str, Any]]] = {}
        self.started_at = wall_now()  # wall-clock: process uptime is measured on the wall

    # -- writing ---------------------------------------------------------
    def incr(self, name: str, by: float = 1.0, **labels: Any) -> None:
        key = _labelled(name, labels)
        with self._lock:
            self._counters[key] = self._counters.get(key, 0.0) + by

    def gauge(self, name: str, value: Any, **labels: Any) -> None:
        with self._lock:
            self._gauges[_labelled(name, labels)] = value

    def observe(self, name: str, seconds: float, **labels: Any) -> None:
        key = _labelled(name, labels)
        with self._lock:
            timer = self._timers.get(key)
            if timer is None:
                timer = self._timers[key] = Timer(key)
            timer.record(seconds)

    def event(self, stream: str, **fields: Any) -> None:
        """Append a short structured record to a bounded stream."""
        with self._lock:
            log = self._events.get(stream)
            if log is None:
                log = self._events[stream] = deque(maxlen=EVENT_LOG)
            # wall-clock: an operational event happened in the real present
            log.append({"at": wall_now().isoformat(timespec="seconds"), **fields})

    @contextmanager
    def timed(self, name: str, **labels: Any) -> Iterator[Dict[str, Any]]:
        """Time a block; the yielded dict may be filled with labels to add on exit."""
        extra: Dict[str, Any] = {}
        started = time.perf_counter()
        try:
            yield extra
        finally:
            self.observe(name, time.perf_counter() - started, **labels, **extra)

    # -- reading ---------------------------------------------------------
    def counter(self, name: str, **labels: Any) -> float:
        with self._lock:
            return self._counters.get(_labelled(name, labels), 0.0)

    def timer(self, name: str, **labels: Any) -> Optional[Dict[str, Any]]:
        with self._lock:
            timer = self._timers.get(_labelled(name, labels))
            return None if timer is None else timer.summary()

    def snapshot(self) -> Dict[str, Any]:
        with self._lock:
            return {
                "startedAt": self.started_at.isoformat(timespec="seconds"),
                # wall-clock: uptime is a fact about the real present
                "uptimeSeconds": round((wall_now() - self.started_at).total_seconds(), 1),
                "counters": dict(sorted(self._counters.items())),
                "gauges": dict(sorted(self._gauges.items())),
                "timers": {k: t.summary() for k, t in sorted(self._timers.items())},
                "events": {k: list(v) for k, v in sorted(self._events.items())},
            }

    def reset(self) -> None:
        with self._lock:
            self._counters.clear()
            self._gauges.clear()
            self._timers.clear()
            self._events.clear()


def _labelled(name: str, labels: Dict[str, Any]) -> str:
    if not labels:
        return name
    tail = ",".join(f"{k}={v}" for k, v in sorted(labels.items()) if v is not None)
    return f"{name}{{{tail}}}" if tail else name


_TELEMETRY: Optional[Telemetry] = None
_LOCK = threading.Lock()


def get_telemetry() -> Telemetry:
    global _TELEMETRY
    with _LOCK:
        if _TELEMETRY is None:
            _TELEMETRY = Telemetry()
        return _TELEMETRY


def reset_telemetry() -> None:
    global _TELEMETRY
    with _LOCK:
        _TELEMETRY = None


# Convenience module-level verbs, so a call site reads as a sentence.
def incr(name: str, by: float = 1.0, **labels: Any) -> None:
    get_telemetry().incr(name, by, **labels)


def gauge(name: str, value: Any, **labels: Any) -> None:
    get_telemetry().gauge(name, value, **labels)


def observe(name: str, seconds: float, **labels: Any) -> None:
    get_telemetry().observe(name, seconds, **labels)


def event(stream: str, **fields: Any) -> None:
    get_telemetry().event(stream, **fields)


def timed(name: str, **labels: Any):
    return get_telemetry().timed(name, **labels)


__all__ = [
    "EVENT_LOG",
    "RESERVOIR",
    "Telemetry",
    "Timer",
    "event",
    "gauge",
    "get_telemetry",
    "incr",
    "observe",
    "reset_telemetry",
    "timed",
]
