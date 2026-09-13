"""The observation recorder: bounded, replayable, and never a way to fake LIVE.

A replayed recording goes through the same feed() the socket uses, at the
recorded times. What these tests defend is that a recording reproduces the
tracks it was made from, that it stays within its bounds, and that replaying
an old recording produces an old picture -- stale, not live -- because a
replay that freshened its timestamps would manufacture LIVE_AIS.
"""

from __future__ import annotations

import json
import os
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from src.portwatch_os.fabric.ais import (
    AIS_STALE,
    AisStreamClient,
    LIVE_AIS,
    ObservationRecorder,
    TrackStore,
    UNAVAILABLE,
    replay,
)
from src.portwatch_os.fabric.ais import client as client_module

NOW = datetime(2026, 9, 13, 12, 0, tzinfo=timezone.utc)


def stamp(moment):
    return moment.strftime("%Y-%m-%d %H:%M:%S.%f") + "000 +0000 UTC"


def position(mmsi="419001234", lat=12.6, lon=43.3, at=NOW):
    return {
        "MessageType": "PositionReport",
        "MetaData": {"MMSI": mmsi, "latitude": lat, "longitude": lon, "time_utc": stamp(at)},
        "Message": {"PositionReport": {"UserID": int(mmsi), "Sog": 12.0, "Cog": 90.0,
                                       "TrueHeading": 90, "NavigationalStatus": 0}},
    }


class RecorderTests(unittest.TestCase):
    def test_the_client_records_every_raw_envelope_and_the_observation_points_at_it(self):
        recorder = ObservationRecorder()
        client = AisStreamClient(TrackStore(), api_key="k", recorder=recorder)
        client.feed(position(), now=NOW)
        client.feed({"MessageType": "AidsToNavigationReport", "MetaData": {}, "Message": {}}, now=NOW)
        self.assertEqual(len(recorder), 2)                    # even what was not consumed
        self.assertEqual(client.store.get("419001234").latest.raw_ref, "rec:1")

    def test_the_recorder_is_bounded_by_count_oldest_out_first(self):
        recorder = ObservationRecorder(capacity=3)
        for i in range(5):
            recorder.record(position(at=NOW + timedelta(seconds=i)), received_at=NOW + timedelta(seconds=i))
        self.assertEqual(len(recorder), 3)
        self.assertEqual(recorder.dropped, 2)
        self.assertEqual(recorder.stats()["recorded"], 5)
        kept = [moment for moment, _ in recorder.entries()]
        self.assertEqual(kept[0], NOW + timedelta(seconds=2))

    def test_the_recorder_is_bounded_by_bytes(self):
        one = len(json.dumps(position(), separators=(",", ":")))
        recorder = ObservationRecorder(capacity=1000, max_bytes=one * 2 + 1)
        for i in range(4):
            recorder.record(position(), received_at=NOW)
        self.assertEqual(len(recorder), 2)

    def test_a_recording_round_trips_through_a_file(self):
        recorder = ObservationRecorder()
        for i in range(3):
            recorder.record(position(lat=12.0 + i, at=NOW + timedelta(minutes=i)),
                            received_at=NOW + timedelta(minutes=i, seconds=2))
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "session.jsonl"
            self.assertEqual(recorder.dump(path), 3)
            rows = list(ObservationRecorder.read(path))
        self.assertEqual(len(rows), 3)
        self.assertEqual(rows[1][0], NOW + timedelta(minutes=1, seconds=2))
        self.assertEqual(rows[2][1]["MetaData"]["latitude"], 14.0)

    def test_a_file_backed_recorder_appends_and_flushes(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "live.jsonl"
            recorder = ObservationRecorder(path=path, flush_every=2)
            recorder.record(position(), received_at=NOW)
            self.assertFalse(path.exists())                   # not yet flushed
            recorder.record(position(), received_at=NOW)
            self.assertEqual(len(list(ObservationRecorder.read(path))), 2)
            recorder.record(position(), received_at=NOW)
            recorder.flush()
            self.assertEqual(len(list(ObservationRecorder.read(path))), 3)


class ReplayTests(unittest.TestCase):
    def test_a_replay_reproduces_the_tracks_at_the_recorded_times(self):
        recorder = ObservationRecorder()
        original = AisStreamClient(TrackStore(), api_key="k", recorder=recorder)
        for i in range(4):
            original.feed(position(lat=12.0 + i * 0.1, at=NOW + timedelta(minutes=i)),
                          now=NOW + timedelta(minutes=i))
        original.feed(position(mmsi="419000002", at=NOW), now=NOW)

        fresh = AisStreamClient(TrackStore(), api_key="k")
        outcome = replay(recorder.entries(), fresh)
        self.assertEqual(outcome["fed"], 5)
        self.assertEqual(len(fresh.store), 2)
        track = fresh.store.get("419001234")
        self.assertEqual(len(track.positions), 4)
        self.assertEqual(track.latest.source_timestamp, NOW + timedelta(minutes=3))
        self.assertIn("recording of 5 messages", fresh.status.replay_of)

    def test_a_recent_recording_is_live_and_says_it_is_a_replay(self):
        recorder = ObservationRecorder()
        recorder.record(position(at=NOW), received_at=NOW)
        fresh = AisStreamClient(TrackStore(), api_key="k")
        replay(recorder.entries(), fresh)
        source = fresh.traffic_source(now=NOW + timedelta(minutes=1))
        self.assertEqual(source["mode"], LIVE_AIS)
        self.assertIn("replayed", source["statement"])
        self.assertIn("replayOf", source["health"])

    def test_an_old_recording_is_an_old_picture_not_a_live_one(self):
        """The rule. Yesterday's messages replayed today are yesterday's."""
        recorder = ObservationRecorder()
        yesterday = NOW - timedelta(hours=26)
        recorder.record(position(at=yesterday), received_at=yesterday)
        fresh = AisStreamClient(TrackStore(), api_key="k")
        replay(recorder.entries(), fresh)
        self.assertEqual(fresh.traffic_source(now=NOW)["mode"], UNAVAILABLE)
        twenty_min = NOW - timedelta(minutes=20)
        recorder2 = ObservationRecorder()
        recorder2.record(position(at=twenty_min), received_at=twenty_min)
        again = AisStreamClient(TrackStore(), api_key="k")
        replay(recorder2.entries(), again)
        self.assertEqual(again.traffic_source(now=NOW)["mode"], AIS_STALE)

    def test_start_client_replays_a_file_instead_of_dialing(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "session.jsonl"
            recorder = ObservationRecorder()
            recorder.record(position(at=NOW), received_at=NOW)
            recorder.dump(path)
            client_module.reset_client()
            saved = {k: os.environ.get(k) for k in (client_module.REPLAY_ENV, "AISSTREAM_API_KEY")}
            os.environ[client_module.REPLAY_ENV] = str(path)
            os.environ.pop("AISSTREAM_API_KEY", None)
            try:
                client = client_module.start_client()
                self.assertIsNone(client._thread)                  # no socket
                self.assertEqual(client.status.messages_seen, 1)
                self.assertIsNotNone(client.status.replay_of)
            finally:
                for k, v in saved.items():
                    if v is None:
                        os.environ.pop(k, None)
                    else:
                        os.environ[k] = v
                client_module.reset_client()


if __name__ == "__main__":
    unittest.main()
