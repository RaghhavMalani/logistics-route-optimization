"""The AISStream websocket client, and the two state machines it drives.

Two things are being tracked, and they are deliberately kept apart.

**Provider health** is about the pipe: are we connected, is the connection
being fed, did the server refuse us. It moves through CONNECTING, LIVE,
DEGRADED, STALE, DISCONNECTED, AUTH_FAILED and RATE_LIMITED, and it is what an
engineer looks at.

**Traffic source** is about the picture: what kind of positions is the chart
drawing right now. It is LIVE_AIS only while valid observations are actually
arriving, AIS_STALE once they stop but the last ones are still worth showing,
SIMULATED_TRAFFIC only when the replay was chosen on purpose, and UNAVAILABLE
when a real provider was asked for and cannot serve. It is what an operator
looks at, and it is the one this module must never get wrong.

The rule that connects them is the one that shapes everything here: **the
source is LIVE_AIS because messages arrived, never because a key exists.** A
configured socket that has received nothing is CONNECTING. A socket that was
receiving and stopped is STALE, then DISCONNECTED. At no point does a failed
live provider become the replay -- if the operator wanted live traffic and it
is gone, the honest picture is an emptying chart, not a fresh-looking one.

Secrets stay here. The key is read from the environment on the server and
appears in no payload, no log line and no status response.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import random
import threading
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

from src.portwatch_os.fabric.ais.messages import (
    AisMessageError,
    AisObservation,
    CONSUMED_TYPES,
    normalise,
)
from src.portwatch_os.fabric.ais.tracks import DEFAULT_STALE_AFTER, TrackStore

log = logging.getLogger(__name__)

# --------------------------------------------------------------------------
# provider health
# --------------------------------------------------------------------------

CONNECTING = "CONNECTING"
LIVE = "LIVE"
DEGRADED = "DEGRADED"
STALE = "STALE"
DISCONNECTED = "DISCONNECTED"
AUTH_FAILED = "AUTH_FAILED"
RATE_LIMITED = "RATE_LIMITED"

HEALTH_STATES: Tuple[str, ...] = (
    CONNECTING, LIVE, DEGRADED, STALE, DISCONNECTED, AUTH_FAILED, RATE_LIMITED,
)

# --------------------------------------------------------------------------
# traffic source
# --------------------------------------------------------------------------

LIVE_AIS = "LIVE_AIS"
AIS_STALE = "AIS_STALE"
SIMULATED_TRAFFIC = "SIMULATED_TRAFFIC"
UNAVAILABLE = "UNAVAILABLE"

SOURCE_STATES: Tuple[str, ...] = (LIVE_AIS, AIS_STALE, SIMULATED_TRAFFIC, UNAVAILABLE)

#: The Indian Ocean subscription box, as AISStream wants it: [[lat, lon], [lat, lon]].
DEFAULT_BOUNDING_BOX: List[List[List[float]]] = [[[-15.0, 40.0], [30.0, 100.0]]]
DEFAULT_URL = "wss://stream.aisstream.io/v0/stream"

#: Backoff: 1s doubling to a ceiling, with jitter so a fleet of reconnecting
#: clients does not hammer the server in lockstep after an outage.
BACKOFF_INITIAL = 1.0
BACKOFF_MAX = 60.0
#: A socket that has delivered nothing in this long is DEGRADED; the store's
#: own staleness rule decides when the *picture* is stale.
QUIET_AFTER = timedelta(seconds=90)
#: AISStream requires the subscription within three seconds of connecting.
SUBSCRIBE_WITHIN = 3.0
#: Messages per second above which we suspect a runaway and pause reading.
RATE_CEILING = 5_000
#: Consecutive sessions that closed with nothing delivered before we conclude
#: the credential is being refused. Observed 2026-09-12 against the live
#: endpoint: an invalid key produces no error envelope, just an abrupt close
#: with no close frame -- indistinguishable from a network drop on any single
#: attempt, and only recognisable as a pattern.
EMPTY_CLOSES_BEFORE_REFUSED = 3


@dataclass
class ProviderStatus:
    """The pipe's state, and the evidence for it."""

    health: str = DISCONNECTED
    connected_at: Optional[datetime] = None
    last_message_at: Optional[datetime] = None
    last_good_observation_at: Optional[datetime] = None
    last_error: Optional[str] = None
    reconnect_attempts: int = 0
    messages_seen: int = 0
    messages_consumed: int = 0
    messages_rejected: int = 0
    #: Message types received and not modelled, by name.
    unconsumed_types: Dict[str, int] = field(default_factory=dict)
    coverage: str = "Indian Ocean subscription box"

    def to_dict(self, *, now: Optional[datetime] = None) -> Dict[str, Any]:
        moment = now or datetime.now(timezone.utc)
        last_good = self.last_good_observation_at
        return {
            "health": self.health,
            "connectedAt": None if self.connected_at is None else self.connected_at.isoformat(),
            "lastMessageAt": None if self.last_message_at is None else self.last_message_at.isoformat(),
            "lastGoodObservationAt": None if last_good is None else last_good.isoformat(),
            "lastGoodAgeSeconds": (
                None if last_good is None else round((moment - last_good).total_seconds(), 1)
            ),
            "lastError": self.last_error,
            "reconnectAttempts": self.reconnect_attempts,
            "messagesSeen": self.messages_seen,
            "messagesConsumed": self.messages_consumed,
            "messagesRejected": self.messages_rejected,
            "unconsumedTypes": dict(self.unconsumed_types),
            "coverage": self.coverage,
        }


class AisStreamClient:
    """One subscription to AISStream, feeding one track store.

    Runs its own event loop on a daemon thread so the FastAPI process can host
    it without becoming async end to end. `start()` and `stop()` are the whole
    lifecycle; everything else is status.
    """

    ENV_KEY = "AISSTREAM_API_KEY"

    def __init__(
        self,
        store: Optional[TrackStore] = None,
        *,
        empty_closes_before_refused: int = EMPTY_CLOSES_BEFORE_REFUSED,
        url: str = DEFAULT_URL,
        bounding_boxes: Optional[List[List[List[float]]]] = None,
        message_types: Sequence[str] = CONSUMED_TYPES,
        api_key: Optional[str] = None,
        on_observation: Optional[Callable[[AisObservation], None]] = None,
        connector: Optional[Callable[..., Any]] = None,
    ) -> None:
        self.store = store or TrackStore()
        self.url = url
        self.bounding_boxes = bounding_boxes or DEFAULT_BOUNDING_BOX
        self.message_types = list(message_types)
        # The key never leaves this object. It is not in status, not in logs.
        self._api_key = api_key if api_key is not None else os.getenv(self.ENV_KEY)
        self._on_observation = on_observation
        # Injectable so the lifecycle can be tested without a network.
        self._connector = connector
        self.status = ProviderStatus()
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._thread: Optional[threading.Thread] = None
        self._stop = threading.Event()
        self._sequence = 0
        self._empty_closes_before_refused = empty_closes_before_refused
        self._consecutive_empty_closes = 0

    # -- configuration ---------------------------------------------------
    @property
    def configured(self) -> bool:
        return bool(self._api_key)

    def subscription(self) -> Dict[str, Any]:
        """The message AISStream expects. Includes the key; never serialise it."""
        return {
            "APIKey": self._api_key,
            "BoundingBoxes": self.bounding_boxes,
            "FilterMessageTypes": self.message_types,
        }

    # -- lifecycle -------------------------------------------------------
    def start(self) -> None:
        if not self.configured:
            self.status.health = DISCONNECTED
            self.status.last_error = "no API key configured"
            return
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run_thread, name="aisstream", daemon=True)
        self._thread.start()

    def stop(self, *, timeout: float = 5.0) -> None:
        """Graceful shutdown: signal, then wait for the loop to unwind."""
        self._stop.set()
        if self._loop is not None:
            self._loop.call_soon_threadsafe(lambda: None)
        if self._thread is not None:
            self._thread.join(timeout=timeout)
        self.status.health = DISCONNECTED

    def _run_thread(self) -> None:
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)
        try:
            self._loop.run_until_complete(self.run())
        finally:
            self._loop.close()

    async def run(self) -> None:
        """Connect, subscribe, read; on any failure back off and try again."""
        backoff = BACKOFF_INITIAL
        while not self._stop.is_set():
            self.status.health = CONNECTING
            delivered_before = self.status.messages_seen
            try:
                await self._session()
                backoff = BACKOFF_INITIAL          # a clean session resets it
            except _AuthFailure as exc:
                self.status.health = AUTH_FAILED
                self.status.last_error = str(exc)
                # Retrying a bad key is pointless and looks like an attack.
                log.warning("AISStream refused the credential: %s", exc)
                return
            except _RateLimited as exc:
                self.status.health = RATE_LIMITED
                self.status.last_error = str(exc)
                backoff = BACKOFF_MAX
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # noqa: BLE001 - any transport failure
                self.status.health = DISCONNECTED
                self.status.last_error = f"{type(exc).__name__}: {exc}"
                log.info("AISStream session ended: %s", self.status.last_error)

                # The server does not say "bad key". It hangs up immediately
                # after the subscription, every time. One such close is a
                # network blip; several in a row with nothing delivered is a
                # refusal, and retrying it forever would look like an attack.
                if self.status.messages_seen == delivered_before:
                    self._consecutive_empty_closes += 1
                    if self._consecutive_empty_closes >= self._empty_closes_before_refused:
                        self.status.health = AUTH_FAILED
                        self.status.last_error = (
                            f"the connection closed immediately after subscribing "
                            f"{self._consecutive_empty_closes} times in a row with "
                            "nothing delivered. That is how AISStream rejects an "
                            "invalid key; check AISSTREAM_API_KEY."
                        )
                        log.warning("AISStream appears to refuse the credential: %s",
                                    self.status.last_error)
                        return
                else:
                    self._consecutive_empty_closes = 0

            if self._stop.is_set():
                break
            self.status.reconnect_attempts += 1
            # Bounded exponential backoff with full jitter.
            wait = random.uniform(0, min(BACKOFF_MAX, backoff))
            backoff = min(BACKOFF_MAX, backoff * 2)
            await asyncio.sleep(wait)
        self.status.health = DISCONNECTED

    async def _session(self) -> None:
        connect = self._connector or _default_connector
        async with connect(self.url) as socket:
            self.status.connected_at = datetime.now(timezone.utc)
            # Subscribe inside the window the server allows.
            await asyncio.wait_for(
                socket.send(json.dumps(self.subscription())), timeout=SUBSCRIBE_WITHIN,
            )
            window_start = datetime.now(timezone.utc)
            window_count = 0

            while not self._stop.is_set():
                try:
                    raw = await asyncio.wait_for(socket.recv(), timeout=QUIET_AFTER.total_seconds())
                except asyncio.TimeoutError:
                    # Connected, silent. Not disconnected; not live either.
                    self.status.health = DEGRADED
                    continue

                now = datetime.now(timezone.utc)
                self.status.messages_seen += 1
                self.status.last_message_at = now

                # Rate protection: a runaway subscription is paused, not read
                # into oblivion.
                window_count += 1
                if (now - window_start).total_seconds() >= 1.0:
                    if window_count > RATE_CEILING:
                        raise _RateLimited(f"{window_count} messages in one second")
                    window_start, window_count = now, 0

                self._handle(raw, now=now)

    def _handle(self, raw: Any, *, now: datetime) -> None:
        try:
            envelope = json.loads(raw) if isinstance(raw, (str, bytes)) else raw
        except (TypeError, ValueError):
            self.status.messages_rejected += 1
            return
        if not isinstance(envelope, dict):
            self.status.messages_rejected += 1
            return

        # AISStream reports a bad key as an error envelope, not a socket close.
        error = envelope.get("error") or envelope.get("Error")
        if error:
            text = str(error).lower()
            if "api key" in text or "unauthor" in text or "invalid" in text:
                raise _AuthFailure(str(error))
            self.status.last_error = str(error)
            return

        self._sequence += 1
        try:
            observation = normalise(
                envelope, now=now, raw_ref=f"aisstream:{self._sequence}",
            )
        except AisMessageError as exc:
            kind = str(envelope.get("MessageType") or "?")
            if kind not in CONSUMED_TYPES:
                self.status.unconsumed_types[kind] = self.status.unconsumed_types.get(kind, 0) + 1
            else:
                self.status.messages_rejected += 1
                log.debug("AIS message rejected: %s", exc)
            return

        outcome = self.store.ingest(observation)
        if outcome.accepted:
            self._consecutive_empty_closes = 0
            self.status.messages_consumed += 1
            self.status.last_good_observation_at = observation.source_timestamp
            # Health is LIVE because a valid observation arrived. Nothing else
            # can set it.
            self.status.health = LIVE
            if self._on_observation is not None:
                try:
                    self._on_observation(observation)
                except Exception:  # noqa: BLE001 - a listener must not kill ingest
                    log.exception("AIS observation listener failed")

    # -- feeding without a socket ---------------------------------------
    def feed(self, envelope: Dict[str, Any], *, now: Optional[datetime] = None) -> None:
        """Push one envelope through the same path the socket uses.

        For tests and for replaying recorded sessions. It is the *only* way in
        besides the socket, and it runs the same validation, so a recorded
        message cannot bypass a check a live one would face.
        """
        moment = now or datetime.now(timezone.utc)
        self.status.messages_seen += 1
        self.status.last_message_at = moment
        self._handle(envelope, now=moment)

    # -- the picture -----------------------------------------------------
    def traffic_source(
        self,
        *,
        now: Optional[datetime] = None,
        replay_chosen: bool = False,
        stale_after: timedelta = DEFAULT_STALE_AFTER,
    ) -> Dict[str, Any]:
        """What the chart is drawing, decided from evidence.

        Only the replay being *chosen* yields SIMULATED_TRAFFIC. A live
        provider that has stopped delivering yields AIS_STALE and then
        UNAVAILABLE; it never becomes the replay by falling through.
        """
        moment = now or datetime.now(timezone.utc)
        last_good = self.status.last_good_observation_at

        if replay_chosen and not self.configured:
            return _source(
                SIMULATED_TRAFFIC,
                "positions are a deterministic replay, not observed AIS, and are "
                "labelled as simulated wherever they are drawn",
                self, moment,
            )

        if self.status.health == AUTH_FAILED:
            return _source(UNAVAILABLE, "AISStream refused the configured credential", self, moment)

        if last_good is None:
            if self.configured:
                return _source(
                    UNAVAILABLE if self.status.health == DISCONNECTED else UNAVAILABLE,
                    "a live provider is configured and no valid observation has "
                    "arrived yet; the chart is not showing the replay in its place",
                    self, moment,
                )
            return _source(UNAVAILABLE, "no traffic source is configured", self, moment)

        age = moment - last_good
        if age <= stale_after:
            return _source(LIVE_AIS, "valid observations are arriving", self, moment)
        if age <= stale_after * 6:
            return _source(
                AIS_STALE,
                f"the last valid observation is {age.total_seconds() / 60:.0f} minutes "
                "old; positions shown are the last known, not current",
                self, moment,
            )
        return _source(
            UNAVAILABLE,
            f"no valid observation for {age.total_seconds() / 3600:.1f} hours; the "
            "live picture has lapsed and has not been replaced by the replay",
            self, moment,
        )


def _source(mode: str, statement: str, client: AisStreamClient, now: datetime) -> Dict[str, Any]:
    return {
        "mode": mode,
        "statement": statement,
        "providerId": "aisstream" if mode in (LIVE_AIS, AIS_STALE) else (
            "ais-replay" if mode == SIMULATED_TRAFFIC else None
        ),
        "health": client.status.to_dict(now=now),
        "vessels": client.store.stats(now=now),
    }


class _AuthFailure(RuntimeError):
    """The server refused the credential. Do not retry."""


class _RateLimited(RuntimeError):
    """We are reading faster than is sane, or the server said stop."""


def _default_connector(url: str):
    """The real transport. Imported lazily so tests never need the package."""
    import websockets

    return websockets.connect(url, compression="deflate", max_queue=4096)


# --------------------------------------------------------------------------
# process-wide instance
# --------------------------------------------------------------------------

_CLIENT: Optional[AisStreamClient] = None
_CLIENT_LOCK = threading.Lock()


def get_client() -> AisStreamClient:
    """The process's one AISStream client, unstarted.

    Reading status must not open a socket: a test that asks "what mode are we
    in" with a dummy key in the environment would otherwise dial the real
    server. The application starts the client on startup, explicitly.
    """
    global _CLIENT
    with _CLIENT_LOCK:
        if _CLIENT is None:
            _CLIENT = AisStreamClient()
        return _CLIENT


def start_client() -> AisStreamClient:
    """Start the process-wide client if a key is configured. Idempotent."""
    client = get_client()
    if client.configured:
        client.start()
    return client


def stop_client() -> None:
    global _CLIENT
    with _CLIENT_LOCK:
        if _CLIENT is not None:
            _CLIENT.stop()


def reset_client() -> None:
    """Forget the process-wide client. For tests that swap the environment."""
    global _CLIENT
    with _CLIENT_LOCK:
        if _CLIENT is not None:
            _CLIENT.stop(timeout=0.5)
        _CLIENT = None


__all__ = [
    "AIS_STALE",
    "AUTH_FAILED",
    "AisStreamClient",
    "BACKOFF_INITIAL",
    "BACKOFF_MAX",
    "CONNECTING",
    "DEFAULT_BOUNDING_BOX",
    "DEGRADED",
    "DISCONNECTED",
    "HEALTH_STATES",
    "LIVE",
    "LIVE_AIS",
    "ProviderStatus",
    "RATE_LIMITED",
    "SIMULATED_TRAFFIC",
    "SOURCE_STATES",
    "STALE",
    "UNAVAILABLE",
    "get_client",
    "reset_client",
    "start_client",
    "stop_client",
]
