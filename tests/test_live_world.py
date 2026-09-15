"""The live world: rebuilt when something changed, recomputed where it reached.

What these tests defend is the pair of guarantees the versioning makes. A
cascade is never served from before the event register or the fleet changed,
because either can change every cascade. And when only observed hulls moved,
a cascade is served as it was only if no lane it reached is a lane a moved
hull sits on -- before or after the move -- because that is the one case in
which it provably cannot have changed.
"""

from __future__ import annotations

import unittest
from datetime import datetime, timedelta, timezone

from src.portwatch_os.fabric.ais import normalise
from src.portwatch_os.fusion import FusionEngine
from src.portwatch_os.global_eye.exposure import VesselVoyage
from src.portwatch_os.world.build import build_world
from src.portwatch_os.world.graph import LANE, key
from src.portwatch_os.world.live import LiveWorld, Revision
from src.portwatch_os.world.observed import place_hull
from src.portwatch_os.world.quantity import Quantity, RISK

NOW = datetime(2026, 9, 12, 12, 0, tzinfo=timezone.utc)


def stamp(moment):
    return moment.strftime("%Y-%m-%d %H:%M:%S.%f") + "000 +0000 UTC"


def hull(engine, mmsi, lat, lon, *, cog=150.0, destination="INNSA", at=NOW):
    for kind, body in (
        ("PositionReport", {"UserID": int(mmsi), "Sog": 14.0, "Cog": cog, "TrueHeading": int(cog),
                            "NavigationalStatus": 0}),
        ("ShipStaticData", {"UserID": int(mmsi), "ImoNumber": 0, "Name": f"HULL {mmsi[-3:]}",
                            "CallSign": "X", "Destination": destination, "Eta": {}}),
    ):
        engine.ingest_ais(normalise({
            "MessageType": kind,
            "MetaData": {"MMSI": mmsi, "latitude": lat, "longitude": lon, "time_utc": stamp(at)},
            "Message": {kind: body},
        }, now=at))
    return place_hull(engine.lookup("MMSI", mmsi), now=at).voyage


def revision(generation=0, events="e1", fleet="f1"):
    return Revision(mode="DEMO", company_id=None, events_stamp=events, fleet_stamp=fleet,
                    observed_generation=generation)


SEED = Quantity(0.8, RISK, confidence=0.9, attrs={"chokepoint": "BAB_EL_MANDEB"})
GULF_SEED = Quantity(0.8, RISK, confidence=0.9, attrs={"chokepoint": "HORMUZ"})


class GraphVersioningTests(unittest.TestCase):
    def setUp(self):
        self.live = LiveWorld()
        self.builds = 0

    def _build(self, voyages=()):
        def build():
            self.builds += 1
            return build_world(voyages=list(voyages), now=NOW), []
        return build

    def test_the_same_revision_is_the_same_graph_without_a_rebuild(self):
        first, why = self.live.graph(revision(), build=self._build(), now=NOW)
        again, why_again = self.live.graph(revision(), build=self._build(), now=NOW)
        self.assertIs(first.graph, again.graph)
        self.assertEqual((why, why_again), ("rebuilt", "reused"))
        self.assertEqual(self.builds, 1)

    def test_a_new_observation_generation_rebuilds(self):
        self.live.graph(revision(0), build=self._build(), now=NOW)
        self.live.bump()
        _, why = self.live.graph(revision(self.live.observed_generation), build=self._build(), now=NOW)
        self.assertEqual(why, "rebuilt")
        self.assertEqual(self.builds, 2)

    def test_a_changed_register_rebuilds(self):
        self.live.graph(revision(events="e1"), build=self._build(), now=NOW)
        _, why = self.live.graph(revision(events="e2"), build=self._build(), now=NOW)
        self.assertEqual(why, "rebuilt")


class IncrementalCascadeTests(unittest.TestCase):
    def setUp(self):
        self.live = LiveWorld()
        self.engine = FusionEngine()
        self.fleet = VesselVoyage("V1", "MV Fleet", "GULF_IND", "INMUN", {"HORMUZ": 20.0})

    def _graph_with(self, *observed):
        return build_world(voyages=[self.fleet, *observed], now=NOW), []

    def test_a_cascade_is_reused_at_the_same_revision(self):
        build, _ = self.live.graph(revision(0), build=lambda: self._graph_with(), now=NOW)
        first, why = self.live.cascade(build, key(LANE, "GULF_IND"), GULF_SEED, at=NOW, now=NOW)
        again, why_again = self.live.cascade(build, key(LANE, "GULF_IND"), GULF_SEED, at=NOW, now=NOW)
        self.assertIs(first, again)
        self.assertEqual(why, "computed")
        self.assertTrue(why_again.startswith("reused"))

    def test_a_hull_moving_on_another_lane_leaves_a_cascade_untouched(self):
        # A Red Sea hull on the Suez lane; the Gulf cascade does not reach it.
        red_sea = hull(self.engine, "419000001", 20.0, 38.5)
        build, _ = self.live.graph(revision(0), build=lambda: self._graph_with(red_sea), now=NOW)
        gulf, _ = self.live.cascade(build, key(LANE, "GULF_IND"), GULF_SEED, at=NOW, now=NOW)
        suez, _ = self.live.cascade(build, key(LANE, "EUR_IND"), SEED, at=NOW, now=NOW)

        # The hull reports again, further south. Only observed hulls changed.
        self.live.bump()
        moved = hull(self.engine, "419000001", 18.0, 39.5, at=NOW + timedelta(minutes=5))
        build2, why = self.live.graph(revision(1), build=lambda: self._graph_with(moved), now=NOW)
        self.assertEqual(why, "rebuilt")

        gulf_again, gulf_why = self.live.cascade(build2, key(LANE, "GULF_IND"), GULF_SEED, at=NOW, now=NOW)
        suez_again, suez_why = self.live.cascade(build2, key(LANE, "EUR_IND"), SEED, at=NOW, now=NOW)
        self.assertIs(gulf_again, gulf)                      # nothing it reaches moved
        self.assertTrue(gulf_why.startswith("reused"))
        self.assertIsNot(suez_again, suez)                   # its lane's hull moved
        self.assertIn("recomputed", suez_why)

    def test_a_hull_arriving_on_a_lane_recomputes_that_lanes_cascade(self):
        build, _ = self.live.graph(revision(0), build=lambda: self._graph_with(), now=NOW)
        before, _ = self.live.cascade(build, key(LANE, "EUR_IND"), SEED, at=NOW, now=NOW)
        self.assertEqual([r for r in before.reached.values() if r.node.attrs.get("source") == "OBSERVED_AIS"], [])

        self.live.bump()
        arrived = hull(self.engine, "419000002", 20.0, 38.5)
        build2, _ = self.live.graph(revision(1), build=lambda: self._graph_with(arrived), now=NOW)
        after, why = self.live.cascade(build2, key(LANE, "EUR_IND"), SEED, at=NOW, now=NOW)
        self.assertIn("recomputed", why)
        observed = [r for r in after.reached.values() if r.node.attrs.get("source") == "OBSERVED_AIS"]
        self.assertEqual(len(observed), 1)

    def test_a_changed_register_recomputes_everything(self):
        build, _ = self.live.graph(revision(events="e1"), build=lambda: self._graph_with(), now=NOW)
        first, _ = self.live.cascade(build, key(LANE, "GULF_IND"), GULF_SEED, at=NOW, now=NOW)
        build2, _ = self.live.graph(revision(events="e2"), build=lambda: self._graph_with(), now=NOW)
        again, why = self.live.cascade(build2, key(LANE, "GULF_IND"), GULF_SEED, at=NOW, now=NOW)
        self.assertIsNot(again, first)
        self.assertEqual(why, "computed")

    def test_cascades_are_keyed_to_the_minute(self):
        build, _ = self.live.graph(revision(0), build=lambda: self._graph_with(), now=NOW)
        first, _ = self.live.cascade(build, key(LANE, "GULF_IND"), GULF_SEED, at=NOW, now=NOW)
        same_minute, why = self.live.cascade(build, key(LANE, "GULF_IND"), GULF_SEED,
                                             at=NOW + timedelta(seconds=40), now=NOW)
        next_hour, why_hour = self.live.cascade(build, key(LANE, "GULF_IND"), GULF_SEED,
                                                at=NOW + timedelta(hours=1), now=NOW)
        self.assertIs(same_minute, first)
        self.assertIsNot(next_hour, first)
        self.assertEqual(why_hour, "computed")

    def test_status_counts_what_was_reused_and_what_was_not(self):
        build, _ = self.live.graph(revision(0), build=lambda: self._graph_with(), now=NOW)
        self.live.cascade(build, key(LANE, "GULF_IND"), GULF_SEED, at=NOW, now=NOW)
        self.live.cascade(build, key(LANE, "GULF_IND"), GULF_SEED, at=NOW, now=NOW)
        status = self.live.status()
        self.assertEqual((status["builds"], status["cascades"], status["reused"]), (1, 1, 1))


if __name__ == "__main__":
    unittest.main()
