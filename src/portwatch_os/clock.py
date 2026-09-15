"""The WorldClock: one instant that every temporal subsystem reads.

Until this module existed, "now" was answered in fifty places. Each of them
asked the operating system, which is the right answer for a live deployment
and the wrong answer for everything else the product does: a mission replay
at 08:00Z on 23 March 2021 must not let a claim horizon lapse against
September 2026, a scenario branch at ``+24h`` must not measure a feed's
staleness from the moment the request arrived, and a recorded feed replayed
at four times speed must age its observations against the replay's clock,
not the wall's. Fifty independent wall-clock reads cannot agree about any of
that, and the disagreements are quiet.

So there is one clock, in one of four modes:

    LIVE                the wall. The default; the deployment's real present.
    REPLAY              a recorded feed being replayed: an anchor instant that
                        advances at ``rate`` times wall speed (0 = frozen).
    HISTORICAL_MISSION  a mission's clock, frozen at the instant the operator
                        is replaying; moved only by the mission's seek.
    SCENARIO            a scenario branch's instant, frozen at the branch's
                        ``at``.

Domain code reads ``world_now()``. A subsystem that takes an explicit ``now``
keyword keeps it -- an explicit instant is a query, not a clock -- but its
fallback is the WorldClock, never the wall. The only code that may read the
wall directly is code whose subject *is* the wall: audit stamps on ledger
rows, refresh scheduling (how old a file is on disk is a fact about the real
world whatever mode the clock is in), and telemetry. Those call
``wall_now()`` and say why; :mod:`tests.test_world_clock` enforces that no
other path asks the operating system.

Two scopes, so a replay in one request cannot move the world for everyone:

*   the **process clock**, set by an administrator (``set_live``,
    ``set_replay``, ...) and read by every request that has not pinned its
    own;
*   a **pinned clock**, a context-local override installed with
    :func:`pinned` for the duration of one replay step, one scenario
    evaluation or one test. It restores the previous state on exit, including
    on exceptions, and is invisible to other threads and tasks.

Timestamps are never rewritten to make something look current. The clock
decides *when it is*; it does not decide *how old a thing is* -- that is the
thing's own recorded instant measured against the clock, in
:mod:`src.portwatch_os.fabric.observation` and the freshness coordinator.
"""

from __future__ import annotations

import contextvars
import threading
from contextlib import contextmanager
from dataclasses import dataclass, field, replace
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Dict, Iterator, Optional

LIVE = "LIVE"
REPLAY = "REPLAY"
HISTORICAL_MISSION = "HISTORICAL_MISSION"
SCENARIO = "SCENARIO"

MODES = (LIVE, REPLAY, HISTORICAL_MISSION, SCENARIO)

#: Modes whose instant is frozen unless the owner moves it.
FROZEN_MODES = (HISTORICAL_MISSION, SCENARIO)


class ClockError(ValueError):
    """A clock misuse: an unknown mode, a naive instant, a frozen clock asked to run."""


def _aware(moment: datetime, what: str = "instant") -> datetime:
    if moment.tzinfo is None:
        raise ClockError(f"the {what} must be timezone-aware; naive datetimes are ambiguous")
    return moment.astimezone(timezone.utc)


def _os_now() -> datetime:
    return datetime.now(timezone.utc)


def wall_now() -> datetime:
    """The wall. Only for code whose subject is the real present.

    Every call site outside this module is expected to carry a
    ``# wall-clock:`` comment naming why the real present is the right
    answer there; the audit test reads those comments. Reads through the
    installed clock's wall source, so a test that scripts the wall scripts
    every audit stamp too.
    """
    return get_clock().wall()


@dataclass(frozen=True)
class ClockState:
    """What the clock is doing. Immutable; a change is a new state."""

    mode: str = LIVE
    #: The instant the clock read when this state was set (non-LIVE modes).
    anchor: Optional[datetime] = None
    #: The wall instant this state was set at; REPLAY advances from here.
    set_at: Optional[datetime] = None
    #: REPLAY only: multiples of wall speed. 0 freezes the replay.
    rate: float = 0.0
    #: Who or what set it, for the trust surface.
    set_by: str = "system"
    #: Why a non-LIVE mode is in force, in words an operator can read.
    reason: str = ""
    #: The mission, recording or scenario this clock belongs to, if any.
    subject: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.mode not in MODES:
            raise ClockError(f"unknown clock mode {self.mode!r}; one of {', '.join(MODES)}")
        if self.mode != LIVE and self.anchor is None:
            raise ClockError(f"a {self.mode} clock needs an anchor instant")
        if self.rate < 0:
            raise ClockError("a replay cannot run backwards; rate must be >= 0")
        if self.mode in FROZEN_MODES and self.rate:
            raise ClockError(f"a {self.mode} clock is frozen; it has no rate")

    def read(self, wall: datetime) -> datetime:
        """The instant this state reads at wall time ``wall``."""
        if self.mode == LIVE:
            return wall
        assert self.anchor is not None
        if self.mode == REPLAY and self.rate and self.set_at is not None:
            elapsed = (wall - self.set_at).total_seconds() * self.rate
            return self.anchor + timedelta(seconds=elapsed)
        return self.anchor

    def to_dict(self, wall: datetime) -> Dict[str, Any]:
        return {
            "mode": self.mode,
            "now": self.read(wall).isoformat(timespec="seconds"),
            "wallNow": wall.isoformat(timespec="seconds"),
            "anchor": None if self.anchor is None else self.anchor.isoformat(timespec="seconds"),
            "setAt": None if self.set_at is None else self.set_at.isoformat(timespec="seconds"),
            "rate": self.rate if self.mode == REPLAY else None,
            "frozen": self.mode in FROZEN_MODES or (self.mode == REPLAY and not self.rate),
            "setBy": self.set_by,
            "reason": self.reason,
            "subject": dict(self.subject),
            "offsetFromWallSeconds": round((self.read(wall) - wall).total_seconds(), 3),
        }


class WorldClock:
    """The process clock plus the context-local pin. See the module docstring."""

    def __init__(self, *, wall: Callable[[], datetime] = _os_now) -> None:
        self._wall = wall
        self._state = ClockState()
        self._lock = threading.RLock()
        self._pinned: contextvars.ContextVar[Optional[ClockState]] = contextvars.ContextVar(
            "portwatch_world_clock_pin", default=None,
        )
        self.changes = 0

    # -- reading -----------------------------------------------------------
    @property
    def state(self) -> ClockState:
        pinned = self._pinned.get()
        if pinned is not None:
            return pinned
        with self._lock:
            return self._state

    @property
    def mode(self) -> str:
        return self.state.mode

    def now(self) -> datetime:
        """The instant it is, in the mode in force for this context."""
        return self.state.read(self._wall())

    def wall(self) -> datetime:
        return self._wall()

    def describe(self) -> Dict[str, Any]:
        state = self.state
        body = state.to_dict(self._wall())
        body["pinned"] = self._pinned.get() is not None
        body["changes"] = self.changes
        return body

    # -- setting the process clock ---------------------------------------
    def _set(self, state: ClockState) -> ClockState:
        with self._lock:
            self._state = state
            self.changes += 1
            return state

    def set_live(self, *, by: str = "system", reason: str = "") -> ClockState:
        return self._set(ClockState(mode=LIVE, set_at=self._wall(), set_by=by, reason=reason))

    def set_replay(
        self, at: datetime, *, rate: float = 1.0, by: str = "system", reason: str = "",
        subject: Optional[Dict[str, Any]] = None,
    ) -> ClockState:
        return self._set(ClockState(
            mode=REPLAY, anchor=_aware(at, "replay anchor"), set_at=self._wall(), rate=float(rate),
            set_by=by, reason=reason, subject=dict(subject or {}),
        ))

    def set_mission(
        self, at: datetime, *, mission_id: str, by: str = "system", reason: str = "",
        subject: Optional[Dict[str, Any]] = None,
    ) -> ClockState:
        return self._set(ClockState(
            mode=HISTORICAL_MISSION, anchor=_aware(at, "mission clock"), set_at=self._wall(),
            set_by=by, reason=reason or f"historical mission {mission_id}",
            subject={"missionId": mission_id, **dict(subject or {})},
        ))

    def set_scenario(
        self, at: datetime, *, scenario_id: str, by: str = "system", reason: str = "",
        subject: Optional[Dict[str, Any]] = None,
    ) -> ClockState:
        return self._set(ClockState(
            mode=SCENARIO, anchor=_aware(at, "scenario instant"), set_at=self._wall(),
            set_by=by, reason=reason or f"scenario {scenario_id}",
            subject={"scenarioId": scenario_id, **dict(subject or {})},
        ))

    def seek(self, at: datetime, *, by: str = "system") -> ClockState:
        """Move a non-LIVE clock to a new anchor without changing its mode."""
        with self._lock:
            current = self.state
            if current.mode == LIVE:
                raise ClockError("a LIVE clock cannot be sought; it reads the wall")
            moved = replace(current, anchor=_aware(at, "seek instant"), set_at=self._wall(), set_by=by)
            pinned = self._pinned.get()
            if pinned is not None:
                self._pinned.set(moved)
                return moved
            return self._set(moved)

    # -- pinning for one context -----------------------------------------
    @contextmanager
    def pinned(self, state: ClockState) -> Iterator[ClockState]:
        """Install ``state`` for this context only, restoring on exit."""
        token = self._pinned.set(state)
        try:
            yield state
        finally:
            self._pinned.reset(token)

    def pin_mission(self, at: datetime, *, mission_id: str, **subject: Any):
        return self.pinned(ClockState(
            mode=HISTORICAL_MISSION, anchor=_aware(at, "mission clock"), set_at=self._wall(),
            set_by="mission-replay", reason=f"historical mission {mission_id}",
            subject={"missionId": mission_id, **subject},
        ))

    def pin_scenario(self, at: datetime, *, scenario_id: str, **subject: Any):
        return self.pinned(ClockState(
            mode=SCENARIO, anchor=_aware(at, "scenario instant"), set_at=self._wall(),
            set_by="scenario", reason=f"scenario {scenario_id}",
            subject={"scenarioId": scenario_id, **subject},
        ))

    def pin_replay(self, at: datetime, *, rate: float = 0.0, **subject: Any):
        return self.pinned(ClockState(
            mode=REPLAY, anchor=_aware(at, "replay anchor"), set_at=self._wall(), rate=float(rate),
            set_by="replay", reason="recorded feed replay", subject=dict(subject),
        ))

    def pin_live(self):
        return self.pinned(ClockState(mode=LIVE, set_at=self._wall(), set_by="pin"))


_CLOCK: Optional[WorldClock] = None
_CLOCK_LOCK = threading.Lock()


def get_clock() -> WorldClock:
    global _CLOCK
    with _CLOCK_LOCK:
        if _CLOCK is None:
            _CLOCK = WorldClock()
        return _CLOCK


def set_clock(clock: Optional[WorldClock]) -> None:
    """Install a clock with a scripted wall. For tests."""
    global _CLOCK
    with _CLOCK_LOCK:
        _CLOCK = clock


def reset_clock() -> None:
    set_clock(None)


def world_now() -> datetime:
    """The instant it is in the world. Every temporal subsystem reads this."""
    return get_clock().now()


def world_mode() -> str:
    return get_clock().mode


def resolve(now: Optional[datetime]) -> datetime:
    """An explicit instant if one was given, else the world's. Naive input is UTC."""
    if now is None:
        return world_now()
    if now.tzinfo is None:
        return now.replace(tzinfo=timezone.utc)
    return now.astimezone(timezone.utc)


__all__ = [
    "ClockError",
    "ClockState",
    "FROZEN_MODES",
    "HISTORICAL_MISSION",
    "LIVE",
    "MODES",
    "REPLAY",
    "SCENARIO",
    "WorldClock",
    "get_clock",
    "reset_clock",
    "resolve",
    "set_clock",
    "wall_now",
    "world_mode",
    "world_now",
]
