"""A bounded recorder for raw AIS envelopes, and a replay of what it kept.

Two reasons to keep the raw messages. The first is audit: every observation
carries a ``raw_ref``, and a reference to a message nobody kept is a
reference to nothing. The second is replay: the socket cannot be asked to
reproduce yesterday's traffic, and a test or a demo that needs a real
sequence of real messages needs them written down.

The recorder is bounded in count and in bytes, oldest out first, because a
recorder that grew without limit would be the first thing to fall over on
the first busy day. It records envelopes *as received*, with the moment they
were received, and replays them through the same ``feed()`` the socket uses,
with those moments -- never re-timed. A recording from yesterday replayed
today produces yesterday's timestamps, and the traffic state machine reads
them as what they are: stale, or lapsed. That is the point. A replay that
freshened its timestamps would be a way of manufacturing LIVE_AIS, and this
module refuses to be one.
"""

from __future__ import annotations

import json
import logging
import threading
from collections import deque
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Deque, Dict, Iterable, Iterator, List, Optional, Tuple

log = logging.getLogger(__name__)

DEFAULT_CAPACITY = 50_000
DEFAULT_MAX_BYTES = 64 * 1024 * 1024


class ObservationRecorder:
    """Raw envelopes in arrival order, bounded, with a JSON-lines file behind them."""

    def __init__(
        self,
        *,
        capacity: int = DEFAULT_CAPACITY,
        max_bytes: int = DEFAULT_MAX_BYTES,
        path: Optional[Path] = None,
        flush_every: int = 500,
    ) -> None:
        self.capacity = capacity
        self.max_bytes = max_bytes
        self.path = path
        self.flush_every = flush_every
        self._items: Deque[Tuple[str, str]] = deque()
        self._bytes = 0
        self._lock = threading.Lock()
        self.recorded = 0
        self.dropped = 0
        self._unflushed: List[Tuple[str, str]] = []
        self.started_at: Optional[datetime] = None
        self.last_at: Optional[datetime] = None

    # -- recording -------------------------------------------------------
    def record(self, envelope: Dict[str, Any], *, received_at: Optional[datetime] = None) -> str:
        """Keep one envelope. Returns the reference the observation should carry."""
        moment = received_at or datetime.now(timezone.utc)
        stamp = moment.isoformat()
        line = json.dumps(envelope, separators=(",", ":"))
        with self._lock:
            self.recorded += 1
            ref = f"rec:{self.recorded}"
            self._items.append((stamp, line))
            self._bytes += len(line)
            while self._items and (len(self._items) > self.capacity or self._bytes > self.max_bytes):
                _, gone = self._items.popleft()
                self._bytes -= len(gone)
                self.dropped += 1
            if self.started_at is None:
                self.started_at = moment
            self.last_at = moment
            if self.path is not None:
                self._unflushed.append((stamp, line))
                if len(self._unflushed) >= self.flush_every:
                    self._flush_locked()
        return ref

    def _flush_locked(self) -> None:
        if not self._unflushed or self.path is None:
            return
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with self.path.open("a", encoding="utf-8") as handle:
                for stamp, line in self._unflushed:
                    handle.write(f'{{"receivedAt":"{stamp}","envelope":{line}}}\n')
        except OSError as exc:
            log.warning("AIS recording not written: %s", exc)
        self._unflushed = []

    def flush(self) -> None:
        with self._lock:
            self._flush_locked()

    # -- reading ---------------------------------------------------------
    def __len__(self) -> int:
        with self._lock:
            return len(self._items)

    def entries(self) -> List[Tuple[datetime, Dict[str, Any]]]:
        with self._lock:
            items = list(self._items)
        return [(datetime.fromisoformat(stamp), json.loads(line)) for stamp, line in items]

    def stats(self) -> Dict[str, Any]:
        with self._lock:
            return {
                "held": len(self._items),
                "capacity": self.capacity,
                "bytes": self._bytes,
                "maxBytes": self.max_bytes,
                "recorded": self.recorded,
                "dropped": self.dropped,
                "startedAt": None if self.started_at is None else self.started_at.isoformat(),
                "lastAt": None if self.last_at is None else self.last_at.isoformat(),
                "path": None if self.path is None else str(self.path),
            }

    # -- files -----------------------------------------------------------
    def dump(self, path: Path) -> int:
        """Write everything held to a JSON-lines file. Returns the count."""
        entries = self.entries()
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8") as handle:
            for moment, envelope in entries:
                handle.write(json.dumps({"receivedAt": moment.isoformat(), "envelope": envelope},
                                        separators=(",", ":")) + "\n")
        return len(entries)

    @staticmethod
    def read(path: Path) -> Iterator[Tuple[datetime, Dict[str, Any]]]:
        """Yield (received_at, envelope) from a recording, skipping bad lines."""
        with path.open("r", encoding="utf-8") as handle:
            for raw in handle:
                raw = raw.strip()
                if not raw:
                    continue
                try:
                    row = json.loads(raw)
                    yield datetime.fromisoformat(row["receivedAt"]), row["envelope"]
                except (ValueError, KeyError, TypeError):
                    continue


def replay(
    source: Iterable[Tuple[datetime, Dict[str, Any]]],
    client: Any,
    *,
    limit: Optional[int] = None,
) -> Dict[str, Any]:
    """Push a recording through a client's ``feed()`` at the recorded times.

    Nothing is re-timed. The client's state machine will read a recording
    from an hour ago as an hour old, which is what it is.
    """
    fed = 0
    first: Optional[datetime] = None
    last: Optional[datetime] = None
    for received_at, envelope in source:
        if limit is not None and fed >= limit:
            break
        client.feed(envelope, now=received_at)
        fed += 1
        first = first or received_at
        last = received_at
    client.status.replay_of = (
        f"recording of {fed} messages received "
        f"{first.isoformat() if first else '?'} to {last.isoformat() if last else '?'}"
    )
    return {"fed": fed, "first": None if first is None else first.isoformat(),
            "last": None if last is None else last.isoformat()}


__all__ = ["DEFAULT_CAPACITY", "DEFAULT_MAX_BYTES", "ObservationRecorder", "replay"]
