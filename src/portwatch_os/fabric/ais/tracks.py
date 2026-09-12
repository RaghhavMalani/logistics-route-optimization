"""The track store: what each transponder has said, in order, and not forever.

A live feed is a firehose that repeats itself. The same position arrives twice
because two receivers heard it; a burst of reports arrives out of order because
they crossed different satellite passes; a vessel that fell silent an hour ago
is still in memory unless something removes it. Each of those, left alone,
produces a chart that is confidently wrong -- a ghost that sailed on after its
transponder stopped, or a track that zig-zags because two receivers disagreed
by a second.

So the store does four things and refuses a fifth:

*   **Deduplicates** on (MMSI, source timestamp, position). The same claim
    heard twice is one claim.
*   **Orders** by source time, not arrival time. A report that arrives late
    is inserted where it belongs, and a report older than the newest one we
    hold does not move the vessel backwards.
*   **Evicts** transponders that have gone quiet. A vessel is *stale* before
    it is *gone*, and both states are visible -- an operator has to be able to
    see a track fading rather than have it vanish between glances.
*   **Bounds memory** per vessel and overall, evicting the quietest first when
    the ceiling is hit. A store that grew without limit would be the first
    thing to fall over on the first busy day.

What it refuses to do is merge identity. Two MMSIs are two tracks here, even if
they later turn out to be one hull; that decision belongs to the fusion layer,
where it can be explained.
"""

from __future__ import annotations

import threading
from collections import OrderedDict, deque
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Deque, Dict, Iterator, List, Optional, Tuple

from src.portwatch_os.fabric.ais.messages import AisObservation

#: A track is live within this, stale after it, and evicted after the second.
DEFAULT_STALE_AFTER = timedelta(minutes=10)
DEFAULT_EVICT_AFTER = timedelta(hours=2)
#: Positions kept per vessel. Enough to draw a passage; not a database.
DEFAULT_TRACK_LENGTH = 240
#: Vessels held at once. The Indian Ocean subscription box is well under this.
DEFAULT_MAX_VESSELS = 20_000


@dataclass
class Track:
    """One transponder's history, newest last, plus what it last said about itself."""

    mmsi: str
    positions: Deque[AisObservation]
    #: Latest identity claims, each with the observation that made it. Kept
    #: separately because static data arrives on its own cadence.
    imo: Optional[str] = None
    name: Optional[str] = None
    callsign: Optional[str] = None
    destination_text: Optional[str] = None
    eta_text: Optional[str] = None
    identity_at: Optional[datetime] = None
    #: How many claims were dropped as duplicates or as older than the head.
    duplicates: int = 0
    out_of_order: int = 0

    @property
    def latest(self) -> Optional[AisObservation]:
        return self.positions[-1] if self.positions else None

    @property
    def last_seen(self) -> Optional[datetime]:
        latest = self.latest
        return latest.source_timestamp if latest else self.identity_at

    def freshness(
        self,
        *,
        now: Optional[datetime] = None,
        stale_after: timedelta = DEFAULT_STALE_AFTER,
    ) -> str:
        seen = self.last_seen
        if seen is None:
            return "UNKNOWN"
        age = (now or datetime.now(timezone.utc)) - seen
        return "LIVE" if age <= stale_after else "STALE"

    def to_dict(self, *, now: Optional[datetime] = None, history: int = 60) -> Dict[str, Any]:
        latest = self.latest
        return {
            "mmsi": self.mmsi,
            "imo": self.imo,
            "name": self.name,
            "callsign": self.callsign,
            "destinationText": self.destination_text,
            "etaText": self.eta_text,
            "latest": None if latest is None else latest.to_dict(),
            "lastSeen": None if self.last_seen is None else self.last_seen.isoformat(),
            "freshness": self.freshness(now=now),
            "positions": len(self.positions),
            "history": [
                {"lat": p.lat, "lon": p.lon, "t": p.source_timestamp.isoformat(),
                 "sog": p.sog_knots, "cog": p.cog_degrees}
                for p in list(self.positions)[-history:]
            ],
            "duplicates": self.duplicates,
            "outOfOrder": self.out_of_order,
            # The source is on every track, so the frontend can label the
            # history as observed rather than assuming.
            "source": "OBSERVED_AIS",
        }


@dataclass
class IngestOutcome:
    """What the store did with one observation."""

    accepted: bool
    reason: str
    mmsi: str


class TrackStore:
    """Bounded, ordered, deduplicated tracks keyed by MMSI."""

    def __init__(
        self,
        *,
        track_length: int = DEFAULT_TRACK_LENGTH,
        max_vessels: int = DEFAULT_MAX_VESSELS,
        stale_after: timedelta = DEFAULT_STALE_AFTER,
        evict_after: timedelta = DEFAULT_EVICT_AFTER,
    ) -> None:
        self.track_length = track_length
        self.max_vessels = max_vessels
        self.stale_after = stale_after
        self.evict_after = evict_after
        # Insertion-ordered so the quietest vessel is findable in O(1) when the
        # ceiling is hit; touched on every accepted observation.
        self._tracks: "OrderedDict[str, Track]" = OrderedDict()
        self._lock = threading.Lock()
        self.accepted = 0
        self.rejected = 0
        self.evicted = 0

    # -- ingest ----------------------------------------------------------
    def ingest(self, observation: AisObservation) -> IngestOutcome:
        with self._lock:
            track = self._tracks.get(observation.mmsi)
            if track is None:
                if len(self._tracks) >= self.max_vessels:
                    self._evict_quietest()
                track = Track(mmsi=observation.mmsi, positions=deque(maxlen=self.track_length))
                self._tracks[observation.mmsi] = track

            # Static data updates identity without adding a position: a name
            # arriving is not a movement.
            if observation.has_identity or observation.destination_text or observation.eta_text:
                self._apply_identity(track, observation)
                if not _is_position(observation):
                    self._tracks.move_to_end(observation.mmsi)
                    self.accepted += 1
                    return IngestOutcome(True, "identity updated", observation.mmsi)

            outcome = self._apply_position(track, observation)
            if outcome.accepted:
                self._tracks.move_to_end(observation.mmsi)
                self.accepted += 1
            else:
                self.rejected += 1
            return outcome

    def _apply_identity(self, track: Track, observation: AisObservation) -> None:
        # Only fields the message actually carried. A static report with no
        # IMO does not erase an IMO an earlier one stated.
        if observation.imo:
            track.imo = observation.imo
        if observation.name:
            track.name = observation.name
        if observation.callsign:
            track.callsign = observation.callsign
        if observation.destination_text:
            track.destination_text = observation.destination_text
        if observation.eta_text:
            track.eta_text = observation.eta_text
        track.identity_at = observation.source_timestamp

    def _apply_position(self, track: Track, observation: AisObservation) -> IngestOutcome:
        head = track.latest
        if head is not None:
            same_instant = head.source_timestamp == observation.source_timestamp
            same_place = abs(head.lat - observation.lat) < 1e-6 and abs(head.lon - observation.lon) < 1e-6
            if same_instant and same_place:
                track.duplicates += 1
                return IngestOutcome(False, "duplicate of the latest position", observation.mmsi)
            if observation.source_timestamp < head.source_timestamp:
                # Late arrival. Slot it into history where it belongs so the
                # drawn track is right, but never let it become the head --
                # that would move the vessel backwards on the chart.
                track.out_of_order += 1
                self._insert_ordered(track, observation)
                return IngestOutcome(True, "late position inserted into history", observation.mmsi)
        track.positions.append(observation)
        return IngestOutcome(True, "position appended", observation.mmsi)

    @staticmethod
    def _insert_ordered(track: Track, observation: AisObservation) -> None:
        items = list(track.positions)
        # Drop an exact duplicate anywhere in history, not only at the head.
        for existing in items:
            if (existing.source_timestamp == observation.source_timestamp
                    and abs(existing.lat - observation.lat) < 1e-6
                    and abs(existing.lon - observation.lon) < 1e-6):
                track.duplicates += 1
                return
        items.append(observation)
        items.sort(key=lambda o: o.source_timestamp)
        track.positions.clear()
        track.positions.extend(items[-track.positions.maxlen:])

    # -- eviction --------------------------------------------------------
    def _evict_quietest(self) -> None:
        mmsi, _ = self._tracks.popitem(last=False)
        self.evicted += 1

    def evict_stale(self, *, now: Optional[datetime] = None) -> List[str]:
        """Remove transponders silent for longer than `evict_after`.

        Returns what was removed, because a track vanishing is a fact the world
        layer needs -- a vessel that was there and is not is not the same as a
        vessel that was never observed.
        """
        moment = now or datetime.now(timezone.utc)
        removed: List[str] = []
        with self._lock:
            for mmsi, track in list(self._tracks.items()):
                seen = track.last_seen
                if seen is not None and moment - seen > self.evict_after:
                    del self._tracks[mmsi]
                    removed.append(mmsi)
                    self.evicted += 1
        return removed

    # -- reading ---------------------------------------------------------
    def get(self, mmsi: str) -> Optional[Track]:
        with self._lock:
            return self._tracks.get(mmsi)

    def tracks(self) -> List[Track]:
        with self._lock:
            return list(self._tracks.values())

    def newest_observation(self) -> Optional[AisObservation]:
        """The most recent position across every track: the feed's last-good."""
        with self._lock:
            latest: Optional[AisObservation] = None
            for track in self._tracks.values():
                head = track.latest
                if head is not None and (latest is None or head.source_timestamp > latest.source_timestamp):
                    latest = head
            return latest

    def __len__(self) -> int:
        with self._lock:
            return len(self._tracks)

    def stats(self, *, now: Optional[datetime] = None) -> Dict[str, Any]:
        moment = now or datetime.now(timezone.utc)
        with self._lock:
            live = sum(1 for t in self._tracks.values()
                       if t.freshness(now=moment, stale_after=self.stale_after) == "LIVE")
            return {
                "vessels": len(self._tracks),
                "live": live,
                "stale": len(self._tracks) - live,
                "accepted": self.accepted,
                "rejected": self.rejected,
                "evicted": self.evicted,
            }


def _is_position(observation: AisObservation) -> bool:
    from src.portwatch_os.fabric.ais.messages import POSITION_REPORT, STANDARD_CLASS_B

    return observation.message_type in (POSITION_REPORT, STANDARD_CLASS_B)


__all__ = [
    "DEFAULT_EVICT_AFTER",
    "DEFAULT_MAX_VESSELS",
    "DEFAULT_STALE_AFTER",
    "DEFAULT_TRACK_LENGTH",
    "IngestOutcome",
    "Track",
    "TrackStore",
]
