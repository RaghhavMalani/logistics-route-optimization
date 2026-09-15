"""The live-AIS acceptance utility: honest without a key, correct with a socket.

The second test feeds the utility a *scripted* socket. That proves the
utility's own claims are wired to the right evidence -- it is not, and the
printed output says it is not, a live acceptance. A live acceptance needs a
real key and the real server, and only ``scripts/verify_live_ais.py`` run
by a person with one can produce it.
"""

from __future__ import annotations

import asyncio
import importlib.util
import json
import os
import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, List

from src.portwatch_os.clock import reset_clock
from src.portwatch_os.fabric.ais.client import AisStreamClient
from src.portwatch_os.fabric.ais.tracks import TrackStore

ROOT = Path(__file__).resolve().parents[1]


def _load_utility():
    spec = importlib.util.spec_from_file_location("verify_live_ais", ROOT / "scripts" / "verify_live_ais.py")
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _stamp(moment: datetime) -> str:
    return moment.strftime("%Y-%m-%d %H:%M:%S.%f") + "123 +0000 UTC"


def _position(mmsi: str, lat: float, lon: float, at: datetime) -> str:
    return json.dumps({
        "MessageType": "PositionReport",
        "MetaData": {"MMSI": mmsi, "ShipName": "META NAME", "latitude": lat, "longitude": lon,
                     "time_utc": _stamp(at)},
        "Message": {"PositionReport": {"UserID": int(mmsi), "Sog": 12.5, "Cog": 311.0, "TrueHeading": 310,
                                       "NavigationalStatus": 0}},
    })


class _Socket:
    def __init__(self, frames: List[Any]):
        self.frames = list(frames)
        self.sent: List[str] = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def send(self, text: str):
        self.sent.append(text)

    async def recv(self):
        if self.frames:
            return self.frames.pop(0)
        await asyncio.sleep(3600)


class _Connector:
    def __init__(self, sockets: List[_Socket]):
        self.sockets = sockets

    def __call__(self, url: str):
        if not self.sockets:
            raise ConnectionError("no more scripted sockets")
        return self.sockets.pop(0)


class VerifyLiveAisTests(unittest.TestCase):
    def setUp(self):
        self.utility = _load_utility()
        self.lines: List[str] = []
        self._key = os.environ.pop("AISSTREAM_API_KEY", None)
        os.environ["PORTWATCH_LICENCE_MODE"] = "DEMO"

    def tearDown(self):
        if self._key is not None:
            os.environ["AISSTREAM_API_KEY"] = self._key
        reset_clock()

    def test_without_a_key_every_claim_is_skipped_and_nothing_passes(self):
        code = self.utility.main([], out=self.lines.append)
        self.assertEqual(code, 0)
        text = "\n".join(self.lines)
        self.assertIn("[SKIP] key present", text)
        self.assertIn("0 passed, 0 failed, 11 skipped", text)
        self.assertNotIn("[PASS]", text)

    def test_a_scripted_socket_exercises_every_claim_and_says_it_is_scripted(self):
        os.environ["AISSTREAM_API_KEY"] = "scripted-not-a-real-key"
        now = datetime.now(timezone.utc)
        frames = [
            _position("419001234", 12.6, 43.3, now - timedelta(seconds=20)),
            _position("419005678", 13.1, 44.0, now - timedelta(seconds=15)),
            _position("419009999", 6.8, 79.9, now - timedelta(seconds=10)),
        ]
        connector = _Connector([_Socket(frames)])

        def factory(*, on_observation):
            return AisStreamClient(TrackStore(), api_key="scripted-not-a-real-key",
                                   on_observation=on_observation, connector=connector)

        code = self.utility.main(["--wait", "10", "--min-observations", "3"],
                                 client_factory=factory, out=self.lines.append)
        text = "\n".join(self.lines)
        self.assertEqual(code, 0, text)
        self.assertIn("scripted socket: this run tests the utility, not a live feed", text)
        for claim in ("connect", "observations", "source timestamp", "LIVE_AIS", "track storage",
                      "observed world", "signal health", "anonymised summary", "disconnect -> stale"):
            self.assertIn(f"[PASS] {claim}", text, claim)
        # The summary never carries an identity field.
        summary = next(line for line in self.lines if "summary:" in line)
        for mmsi in ("419001234", "419005678", "419009999"):
            self.assertNotIn(mmsi, summary)
        self.assertNotIn("META NAME", summary)
        self.assertNotIn("scripted-not-a-real-key", text)

    def test_a_silent_socket_fails_the_observations_claim_rather_than_passing(self):
        os.environ["AISSTREAM_API_KEY"] = "scripted-not-a-real-key"
        connector = _Connector([_Socket([])])

        def factory(*, on_observation):
            return AisStreamClient(TrackStore(), api_key="scripted-not-a-real-key",
                                   on_observation=on_observation, connector=connector)

        code = self.utility.main(["--wait", "2", "--min-observations", "1"],
                                 client_factory=factory, out=self.lines.append)
        text = "\n".join(self.lines)
        self.assertEqual(code, 1, text)
        self.assertIn("[FAIL] observations", text)
        self.assertNotIn("[PASS] LIVE_AIS", text)


if __name__ == "__main__":
    unittest.main()
