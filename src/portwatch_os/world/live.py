"""The live world: a graph that is rebuilt when something changed, and cascades
that are recomputed only where the change could reach.

The world graph has been rebuilt on every request since it existed, and for a
world that changed once an hour that was the right call -- a cached graph
that lagged the event register would be the quiet inconsistency the product
exists to avoid. Observed AIS changes the arithmetic: a transponder reports
every few seconds, and a chart with a hundred observed hulls would rebuild
the whole graph and re-run every cascade at every poll.

So the world is versioned rather than cached. A **revision** is the tuple of
what the graph was built from: the event register's stamp, the fleet's stamp,
the observed-hull generation and the mode. A request whose revision matches
the last build gets the same graph; a request whose revision differs gets a
rebuild. That much is memoisation. The incremental part is the cascades: when
only observed hulls moved between two revisions, a cascade whose reach did not
touch any lane those hulls sit on -- before or after the move -- cannot have
changed, and is served as it was. One whose reach did touch such a lane is
recomputed. Nothing is served from before the event register or the fleet
changed, because either can change every cascade.

The recorded reason for each decision (``rebuilt``, ``reused``,
``recomputed: lane X moved``) is exposed so the trust surface can say how
fresh the consequence is, in the same terms as everything else.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable, Dict, FrozenSet, List, Optional, Tuple

from src.portwatch_os.world.cascade import Cascade, propagate
from src.portwatch_os.world.graph import LANE, VESSEL, WorldGraph, key
from src.portwatch_os.world.quantity import Quantity

#: Cascades are keyed to the minute: the world's own time resolution is the
#: event register's, and a cascade at 12:00:04 and 12:00:40 differ in nothing.
CASCADE_TIME_RESOLUTION_S = 60


@dataclass(frozen=True)
class Revision:
    """What a graph was built from. Equal revisions mean an identical graph."""

    mode: str
    company_id: Optional[str]
    events_stamp: str
    fleet_stamp: str
    observed_generation: int

    def differs_only_in_observations(self, other: "Revision") -> bool:
        return (
            self.mode == other.mode
            and self.company_id == other.company_id
            and self.events_stamp == other.events_stamp
            and self.fleet_stamp == other.fleet_stamp
            and self.observed_generation != other.observed_generation
        )


@dataclass
class Build:
    revision: Revision
    graph: WorldGraph
    events: List[Any]
    built_at: datetime
    #: Lane keys each observed hull was attached to when this graph was built.
    observed_lanes: Dict[str, Optional[str]] = field(default_factory=dict)


@dataclass
class CachedCascade:
    cascade: Cascade
    revision: Revision
    #: Every lane the cascade reached, so a moved hull can be tested against it.
    lanes: FrozenSet[str]
    computed_at: datetime
    reason: str


class LiveWorld:
    """One process's world, versioned, with incremental cascade recompute."""

    def __init__(self, *, keep_builds: int = 4) -> None:
        self._builds: Dict[Tuple[str, Optional[str]], Build] = {}
        self._cascades: Dict[Tuple[str, Optional[str], str, int], CachedCascade] = {}
        self._keep = keep_builds
        self._lock = threading.RLock()
        self._observed_generation = 0
        self.stats = {"builds": 0, "reused_builds": 0, "cascades": 0, "reused": 0, "recomputed": 0}

    # -- observation generation ------------------------------------------
    def bump(self) -> int:
        """An observed hull changed. Called by the ingest path on every accepted observation."""
        with self._lock:
            self._observed_generation += 1
            return self._observed_generation

    @property
    def observed_generation(self) -> int:
        return self._observed_generation

    # -- graphs ----------------------------------------------------------
    def graph(
        self,
        revision: Revision,
        *,
        build: Callable[[], Tuple[WorldGraph, List[Any]]],
        now: datetime,
    ) -> Tuple[Build, str]:
        """The graph for a revision: the last build if it matches, else a new one."""
        slot = (revision.mode, revision.company_id)
        with self._lock:
            held = self._builds.get(slot)
            if held is not None and held.revision == revision:
                self.stats["reused_builds"] += 1
                return held, "reused"
            graph, events = build()
            fresh = Build(
                revision=revision, graph=graph, events=events, built_at=now,
                observed_lanes=_observed_lanes(graph),
            )
            previous = held
            self._builds[slot] = fresh
            self.stats["builds"] += 1
            if previous is not None:
                self._invalidate(slot, previous, fresh)
            else:
                self._drop_cascades(slot)
            return fresh, "rebuilt"

    def _invalidate(self, slot: Tuple[str, Optional[str]], previous: Build, fresh: Build) -> None:
        """Drop the cascades the change could have reached."""
        if not previous.revision.differs_only_in_observations(fresh.revision):
            # The register or the fleet changed: every cascade may differ.
            self._drop_cascades(slot)
            return
        moved = set()
        hulls = set(previous.observed_lanes) | set(fresh.observed_lanes)
        for hull in hulls:
            before = previous.observed_lanes.get(hull)
            after = fresh.observed_lanes.get(hull)
            if before != after or hull not in previous.observed_lanes or hull not in fresh.observed_lanes:
                moved.update(k for k in (before, after) if k)
            elif after:
                # Same lane, but the hull's timing may have changed with its
                # position; the lane's cascades are recomputed to be safe.
                moved.add(after)
        for cache_key in list(self._cascades):
            if cache_key[0] != slot[0] or cache_key[1] != slot[1]:
                continue
            cached = self._cascades[cache_key]
            if cached.lanes & moved:
                # Left in place at its old revision so the recompute can say
                # why it happened; the revision mismatch is what forces it.
                cached.reason = "recomputed: an observed hull moved on a lane it reaches"
            else:
                # Provably unchanged by this revision: carry it forward as
                # valid for the new graph, with its original computation time.
                cached.revision = fresh.revision

    def _drop_cascades(self, slot: Tuple[str, Optional[str]]) -> None:
        for cache_key in list(self._cascades):
            if cache_key[0] == slot[0] and cache_key[1] == slot[1]:
                del self._cascades[cache_key]

    # -- cascades --------------------------------------------------------
    def cascade(
        self,
        build: Build,
        seed_key: str,
        seed: Quantity,
        *,
        at: datetime,
        now: datetime,
    ) -> Tuple[Cascade, str]:
        """A cascade for this build, reused when nothing that reaches it moved."""
        cache_key = (build.revision.mode, build.revision.company_id, f"{seed_key}|{seed.value:.4f}",
                     int(at.timestamp() // CASCADE_TIME_RESOLUTION_S))
        with self._lock:
            held = self._cascades.get(cache_key)
            if held is not None and held.revision == build.revision:
                self.stats["reused"] += 1
                return held.cascade, f"reused (computed {held.computed_at.isoformat()})"
            cascade = propagate(build.graph, seed_key, seed, at=at)
            lanes = frozenset(r.node.key for r in cascade.reached.values() if r.node.kind == LANE)
            reason = "computed" if held is None else held.reason
            self._cascades[cache_key] = CachedCascade(cascade, build.revision, lanes, now, reason)
            self.stats["cascades" if held is None else "recomputed"] += 1
            if len(self._cascades) > 512:
                oldest = min(self._cascades, key=lambda k: self._cascades[k].computed_at)
                del self._cascades[oldest]
            return cascade, reason

    def status(self) -> Dict[str, Any]:
        with self._lock:
            return {
                "observedGeneration": self._observed_generation,
                "heldBuilds": len(self._builds),
                "cascadesHeld": len(self._cascades),
                **self.stats,
            }


def _observed_lanes(graph: WorldGraph) -> Dict[str, Optional[str]]:
    out: Dict[str, Optional[str]] = {}
    for node in graph.nodes(kind=VESSEL):
        if node.attrs.get("source") == "OBSERVED_AIS":
            lane = node.attrs.get("lane_code")
            out[node.key] = key(LANE, lane) if lane else None
    return out


_LIVE: Optional[LiveWorld] = None
_LIVE_LOCK = threading.Lock()


def get_live_world() -> LiveWorld:
    global _LIVE
    with _LIVE_LOCK:
        if _LIVE is None:
            _LIVE = LiveWorld()
        return _LIVE


def reset_live_world() -> None:
    global _LIVE
    with _LIVE_LOCK:
        _LIVE = None


__all__ = ["Build", "LiveWorld", "Revision", "get_live_world", "reset_live_world"]
