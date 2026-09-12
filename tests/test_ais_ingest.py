"""Observed AIS: messages, tracks, the socket lifecycle and the source state.

The one sentence every test here defends: the chart says LIVE because valid
observations arrived, and for no other reason. Everything else -- dedup,
ordering, eviction, backoff, the refusal to fall through to the replay -- is a
way of keeping that sentence true under the conditions a real feed produces.

The socket is exercised against a scripted transport rather than the network.
That is not a shortcut: the behaviours under test are what the client does when
the server refuses it, goes quiet, or drops the connection, and a live server
cannot be asked to do those on cue.
"""

from __future__ import annotations

import asyncio
import json
import unittest
from datetime import datetime, timedelta, timezone
from typing import Any, List, Optional

from src.portwatch_os.fabric.ais import (
    AIS_STALE,
    AUTH_FAILED,
    AisMessageError,
    AisStreamClient,
    CONNECTING,
    DEGRADED,
    DISCONNECTED,
    LIVE,
    LIVE_AIS,
    SIMULATED_TRAFFIC,
    TrackStore,
    UNAVAILABLE,
    normalise,
)
from src.portwatch_os.fabric.ais import client as client_module

NOW = datetime(2026, 9, 12, 12, 0, tzinfo=timezone.utc)


def stamp(moment: datetime) -> str:
    """AISStream's own time format, nanoseconds and the trailing UTC word."""
    return moment.strftime("%Y-%m-%d %H:%M:%S.%f") + "123 +0000 UTC"


def position(mmsi="419001234", lat=12.6, lon=43.3, at=NOW, **body) -> dict:
    report = {"UserID": int(mmsi), "Sog": 12.5, "Cog": 311.0, "TrueHeading": 310,
              "NavigationalStatus": 0}
    report.update(body)
    return {
        "MessageType": "PositionReport",
        "MetaData": {"MMSI": mmsi, "ShipName": "META NAME", "latitude": lat,
                     "longitude": lon, "time_utc": stamp(at)},
        "Message": {"PositionReport": report},
    }


def static(mmsi="419001234", at=NOW, **body) -> dict:
    data = {"UserID": int(mmsi), "ImoNumber": 9876543, "Name": "MV KONKAN@@@",
            "CallSign": "VTKK", "Destination": "IN NSA",
            "Eta": {"Month": 9, "Day": 14, "Hour": 6, "Minute": 30}}
    data.update(body)
    return {
        "MessageType": "ShipStaticData",
        "MetaData": {"MMSI": mmsi, "latitude": 12.6, "longitude": 43.3, "time_utc": stamp(at)},
        "Message": {"ShipStaticData": data},
    }


# --------------------------------------------------------------------------
# normalisation
# --------------------------------------------------------------------------


class NormaliseTests(unittest.TestCase):
    def test_a_position_report_carries_no_identity(self):
        """The whole rule. A position says where, never who."""
        obs = normalise(position(), now=NOW)
        self.assertEqual(obs.mmsi, "419001234")
        self.assertIsNone(obs.imo)
        self.assertIsNone(obs.name)
        self.assertIsNone(obs.callsign)
        self.assertIsNone(obs.destination_text)
        self.assertFalse(obs.has_identity)

    def test_the_metadata_ship_name_is_provenance_not_a_claim(self):
        """AISStream joins a name onto positions. That is their inference, not
        the transponder's statement, and it is kept where that is visible."""
        obs = normalise(position(), now=NOW)
        self.assertIsNone(obs.name)
        self.assertEqual(obs.provenance["meta_ship_name"], "META NAME")

    def test_static_data_carries_identity_as_stated(self):
        obs = normalise(static(), now=NOW)
        self.assertEqual(obs.imo, "9876543")
        self.assertEqual(obs.name, "MV KONKAN")          # padding stripped
        self.assertEqual(obs.callsign, "VTKK")
        self.assertEqual(obs.destination_text, "IN NSA")  # text, not a port
        self.assertEqual(obs.eta_text, "09-14 06:30")

    def test_imo_zero_is_absence_not_an_identifier(self):
        obs = normalise(static(ImoNumber=0), now=NOW)
        self.assertIsNone(obs.imo)

    def test_sentinels_become_none_rather_than_numbers(self):
        obs = normalise(position(TrueHeading=511, Sog=102.3, Cog=360.0), now=NOW)
        self.assertIsNone(obs.heading_degrees)
        self.assertIsNone(obs.sog_knots)
        self.assertIsNone(obs.cog_degrees)

    def test_the_source_time_is_the_transponders_not_ours(self):
        earlier = NOW - timedelta(minutes=7)
        obs = normalise(position(at=earlier), now=NOW)
        self.assertEqual(obs.source_timestamp, earlier)
        self.assertEqual(obs.ingested_at, NOW)
        self.assertTrue(obs.provenance["source_time_known"])

    def test_a_missing_time_is_declared_rather_than_replaced(self):
        env = position()
        del env["MetaData"]["time_utc"]
        obs = normalise(env, now=NOW)
        self.assertFalse(obs.provenance["source_time_known"])

    def test_a_malformed_mmsi_is_refused(self):
        with self.assertRaises(AisMessageError):
            normalise(position(mmsi="12345"), now=NOW)

    def test_a_position_at_the_sentinel_is_refused(self):
        with self.assertRaises(AisMessageError):
            normalise(position(lat=91.0), now=NOW)

    def test_an_unconsumed_type_is_refused_not_guessed(self):
        env = position()
        env["MessageType"] = "AidsToNavigationReport"
        with self.assertRaises(AisMessageError):
            normalise(env, now=NOW)


# --------------------------------------------------------------------------
# the store
# --------------------------------------------------------------------------


class TrackStoreTests(unittest.TestCase):
    def setUp(self):
        self.store = TrackStore(track_length=5, max_vessels=3)

    def _feed(self, env):
        return self.store.ingest(normalise(env, now=NOW))

    def test_a_duplicate_is_one_claim(self):
        self._feed(position())
        outcome = self._feed(position())
        self.assertFalse(outcome.accepted)
        self.assertEqual(len(self.store.get("419001234").positions), 1)
        self.assertEqual(self.store.get("419001234").duplicates, 1)

    def test_a_late_position_goes_into_history_not_the_head(self):
        self._feed(position(lat=12.6, at=NOW))
        self._feed(position(lat=12.5, at=NOW - timedelta(seconds=30)))
        track = self.store.get("419001234")
        self.assertEqual(track.latest.lat, 12.6)           # head unchanged
        self.assertEqual([p.lat for p in track.positions], [12.5, 12.6])
        self.assertEqual(track.out_of_order, 1)

    def test_identity_is_updated_without_adding_a_position(self):
        self._feed(position())
        self._feed(static())
        track = self.store.get("419001234")
        self.assertEqual(track.name, "MV KONKAN")
        self.assertEqual(len(track.positions), 1)

    def test_static_data_without_a_field_does_not_erase_it(self):
        self._feed(static())
        self._feed(static(ImoNumber=0, Name="@@@@"))
        track = self.store.get("419001234")
        self.assertEqual(track.imo, "9876543")
        self.assertEqual(track.name, "MV KONKAN")

    def test_track_length_is_bounded(self):
        for i in range(12):
            self._feed(position(lat=12.0 + i * 0.01, at=NOW + timedelta(seconds=i)))
        self.assertEqual(len(self.store.get("419001234").positions), 5)

    def test_the_quietest_vessel_is_evicted_at_the_ceiling(self):
        for i, mmsi in enumerate(("419000001", "419000002", "419000003")):
            self._feed(position(mmsi=mmsi, at=NOW + timedelta(seconds=i)))
        self._feed(position(mmsi="419000001", at=NOW + timedelta(seconds=10)))  # touch
        self._feed(position(mmsi="419000004", at=NOW + timedelta(seconds=11)))
        self.assertIsNone(self.store.get("419000002"))      # quietest went
        self.assertIsNotNone(self.store.get("419000001"))
        self.assertEqual(self.store.evicted, 1)

    def test_silent_transponders_are_evicted_and_reported(self):
        self._feed(position(mmsi="419000001", at=NOW - timedelta(hours=3)))
        self._feed(position(mmsi="419000002", at=NOW))
        removed = self.store.evict_stale(now=NOW)
        self.assertEqual(removed, ["419000001"])
        self.assertIsNotNone(self.store.get("419000002"))

    def test_a_track_knows_it_is_stale_before_it_is_gone(self):
        self._feed(position(at=NOW - timedelta(minutes=20)))
        self.assertEqual(self.store.get("419001234").freshness(now=NOW), "STALE")

    def test_every_track_declares_its_source(self):
        self._feed(position())
        self.assertEqual(self.store.get("419001234").to_dict()["source"], "OBSERVED_AIS")


# --------------------------------------------------------------------------
# source state
# --------------------------------------------------------------------------


class TrafficSourceTests(unittest.TestCase):
    def test_a_key_alone_is_not_live(self):
        """The sentence the whole module defends."""
        client = AisStreamClient(TrackStore(), api_key="k")
        self.assertEqual(client.traffic_source(now=NOW)["mode"], UNAVAILABLE)
        self.assertNotEqual(client.status.health, LIVE)

    def test_a_valid_observation_makes_it_live(self):
        client = AisStreamClient(TrackStore(), api_key="k")
        client.feed(position(at=NOW - timedelta(seconds=3)), now=NOW)
        self.assertEqual(client.traffic_source(now=NOW)["mode"], LIVE_AIS)
        self.assertEqual(client.status.health, LIVE)

    def test_silence_degrades_to_stale_then_unavailable_never_replay(self):
        client = AisStreamClient(TrackStore(), api_key="k")
        client.feed(position(at=NOW), now=NOW)
        self.assertEqual(client.traffic_source(now=NOW + timedelta(minutes=15))["mode"], AIS_STALE)
        later = client.traffic_source(now=NOW + timedelta(hours=3))
        self.assertEqual(later["mode"], UNAVAILABLE)
        self.assertIn("not been replaced by the replay", later["statement"])

    def test_the_replay_appears_only_when_chosen(self):
        unconfigured = AisStreamClient(TrackStore(), api_key=None)
        self.assertEqual(unconfigured.traffic_source(now=NOW)["mode"], UNAVAILABLE)
        self.assertEqual(
            unconfigured.traffic_source(now=NOW, replay_chosen=True)["mode"],
            SIMULATED_TRAFFIC,
        )

    def test_choosing_the_replay_does_not_override_a_configured_live_source(self):
        """A live provider that is configured but silent is not the replay."""
        client = AisStreamClient(TrackStore(), api_key="k")
        self.assertEqual(
            client.traffic_source(now=NOW, replay_chosen=True)["mode"], UNAVAILABLE,
        )

    def test_a_rejected_message_does_not_make_it_live(self):
        client = AisStreamClient(TrackStore(), api_key="k")
        client.feed(position(lat=91.0), now=NOW)
        self.assertEqual(client.status.messages_rejected, 1)
        self.assertEqual(client.traffic_source(now=NOW)["mode"], UNAVAILABLE)

    def test_the_key_appears_in_no_status_payload(self):
        client = AisStreamClient(TrackStore(), api_key="super-secret-key")
        client.feed(position(), now=NOW)
        blob = json.dumps(client.traffic_source(now=NOW)) + json.dumps(client.status.to_dict())
        self.assertNotIn("super-secret-key", blob)


# --------------------------------------------------------------------------
# socket lifecycle, against a scripted transport
# --------------------------------------------------------------------------


class _Socket:
    """A scripted server: yields the given frames, then behaves as told."""

    def __init__(self, frames: List[Any], *, then: str = "close"):
        self.frames = list(frames)
        self.then = then
        self.sent: List[str] = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def send(self, text: str):
        self.sent.append(text)

    async def recv(self):
        if self.frames:
            frame = self.frames.pop(0)
            if isinstance(frame, Exception):
                raise frame
            return frame
        if self.then == "close":
            raise ConnectionError("server closed")
        if self.then == "hang":
            await asyncio.sleep(3600)
        raise RuntimeError(self.then)


class _Connector:
    """Hands out scripted sockets in order and records every attempt."""

    def __init__(self, sockets: List[_Socket]):
        self.sockets = sockets
        self.attempts = 0

    def __call__(self, url: str):
        self.attempts += 1
        if not self.sockets:
            raise ConnectionError("no more scripted sockets")
        return self.sockets.pop(0)


def run_briefly(client: AisStreamClient, seconds: float) -> None:
    async def _run():
        task = asyncio.ensure_future(client.run())
        await asyncio.sleep(seconds)
        client._stop.set()
        task.cancel()
        try:
            await task
        except (asyncio.CancelledError, Exception):
            pass

    asyncio.new_event_loop().run_until_complete(_run())


class SocketLifecycleTests(unittest.TestCase):
    def setUp(self):
        # Make backoff instant so the tests run in milliseconds.
        self._backoff = (client_module.BACKOFF_INITIAL, client_module.BACKOFF_MAX)
        client_module.BACKOFF_INITIAL = 0.0
        client_module.BACKOFF_MAX = 0.01

    def tearDown(self):
        client_module.BACKOFF_INITIAL, client_module.BACKOFF_MAX = self._backoff

    def test_it_subscribes_on_connect_and_the_key_is_in_the_subscription_only(self):
        socket = _Socket([json.dumps(position())])
        client = AisStreamClient(TrackStore(), api_key="k", connector=_Connector([socket]))
        run_briefly(client, 0.2)
        self.assertEqual(len(socket.sent), 1)
        self.assertEqual(json.loads(socket.sent[0])["APIKey"], "k")
        self.assertIn("BoundingBoxes", json.loads(socket.sent[0]))

    def test_a_delivered_message_makes_health_live(self):
        socket = _Socket([json.dumps(position(at=NOW))], then="hang")
        client = AisStreamClient(TrackStore(), api_key="k", connector=_Connector([socket]))
        run_briefly(client, 0.2)
        self.assertEqual(client.status.messages_consumed, 1)
        self.assertIsNotNone(client.status.last_good_observation_at)

    def test_a_dropped_connection_reconnects(self):
        connector = _Connector([_Socket([], then="close"), _Socket([], then="close"),
                                _Socket([json.dumps(position())], then="hang")])
        client = AisStreamClient(TrackStore(), api_key="k", connector=connector)
        run_briefly(client, 0.5)
        self.assertGreaterEqual(connector.attempts, 3)
        self.assertGreaterEqual(client.status.reconnect_attempts, 2)
        self.assertEqual(client.status.messages_consumed, 1)

    def test_an_error_envelope_naming_the_key_stops_immediately(self):
        socket = _Socket([json.dumps({"error": "Api Key Is Not Valid"})])
        connector = _Connector([socket, _Socket([]), _Socket([])])
        client = AisStreamClient(TrackStore(), api_key="bad", connector=connector)
        run_briefly(client, 0.3)
        self.assertEqual(client.status.health, AUTH_FAILED)
        self.assertEqual(connector.attempts, 1)              # no retry
        self.assertEqual(client.traffic_source(now=NOW)["mode"], UNAVAILABLE)

    def test_repeated_empty_closes_are_recognised_as_a_refusal(self):
        """What the real server actually does with a bad key.

        Probed 2026-09-12: no error envelope, no close frame -- the socket is
        simply dropped after the subscription. One drop is a network blip and
        must reconnect; three in a row with nothing delivered is a refusal and
        must stop. Written against the observed behaviour, not the assumed one.
        """
        connector = _Connector([_Socket([], then="close") for _ in range(6)])
        client = AisStreamClient(
            TrackStore(), api_key="bad", connector=connector,
            empty_closes_before_refused=3,
        )
        run_briefly(client, 0.5)
        self.assertEqual(client.status.health, AUTH_FAILED)
        self.assertEqual(connector.attempts, 3)              # stopped, not six
        self.assertIn("closed immediately after subscribing", client.status.last_error)

    def test_a_delivered_message_resets_the_refusal_counter(self):
        """Two blips around a good session are blips, not a refusal."""
        connector = _Connector([
            _Socket([], then="close"),
            _Socket([], then="close"),
            _Socket([json.dumps(position())], then="close"),   # delivered
            _Socket([], then="close"),
            _Socket([], then="close"),
            _Socket([json.dumps(position(at=NOW + timedelta(seconds=1)))], then="hang"),
        ])
        client = AisStreamClient(
            TrackStore(), api_key="k", connector=connector,
            empty_closes_before_refused=3,
        )
        run_briefly(client, 0.6)
        self.assertNotEqual(client.status.health, AUTH_FAILED)
        self.assertEqual(client.status.messages_consumed, 2)

    def test_an_unconfigured_client_does_not_start(self):
        client = AisStreamClient(TrackStore(), api_key=None, connector=_Connector([]))
        client.start()
        self.assertEqual(client.status.health, DISCONNECTED)
        self.assertIn("no API key", client.status.last_error)

    def test_backoff_is_bounded_and_jittered(self):
        """Delays grow, cap, and are not identical -- so a fleet of clients
        reconnecting after an outage does not arrive in lockstep."""
        client_module.BACKOFF_INITIAL, client_module.BACKOFF_MAX = 1.0, 8.0
        seen: List[float] = []

        async def fake_sleep(seconds):
            seen.append(seconds)
            if len(seen) >= 6:
                client._stop.set()

        connector = _Connector([_Socket([], then="close") for _ in range(8)])
        client = AisStreamClient(TrackStore(), api_key="k", connector=connector)
        original = client_module.asyncio.sleep
        client_module.asyncio.sleep = fake_sleep
        try:
            asyncio.new_event_loop().run_until_complete(client.run())
        finally:
            client_module.asyncio.sleep = original
        self.assertTrue(all(0.0 <= s <= 8.0 for s in seen), seen)
        self.assertGreater(len(set(round(s, 6) for s in seen)), 1)


if __name__ == "__main__":
    unittest.main()
