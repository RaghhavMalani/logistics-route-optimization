"""Observed hulls in the world graph: placed only as far as the evidence goes.

The replay tells the graph everything about a vessel. An observed hull tells
it a position, a speed, a course and -- sometimes -- a typed destination. What
these tests check is that each inference from there is graded, that an
ungradeable hull is on the chart without transmitting consequence, and that
the discount reaches the cascade as lower confidence, not lower risk.
"""

from __future__ import annotations

import unittest
from datetime import datetime, timedelta, timezone

from src.portwatch_os.fabric.ais import normalise
from src.portwatch_os.fusion import FusionEngine
from src.portwatch_os.global_eye.exposure import VesselVoyage
from src.portwatch_os.world.build import build_world
from src.portwatch_os.world.graph import LANE, SAILS, VESSEL, key
from src.portwatch_os.world.observed import (
    hours_to_chokepoints,
    infer_lane,
    observed_voyages,
    place_hull,
)

NOW = datetime(2026, 9, 12, 12, 0, tzinfo=timezone.utc)


def stamp(moment):
    return moment.strftime("%Y-%m-%d %H:%M:%S.%f") + "000 +0000 UTC"


def fed(engine, mmsi, lat, lon, *, sog=14.0, cog=100.0, destination=None, name="HULL", imo=0, at=NOW):
    engine.ingest_ais(normalise({
        "MessageType": "PositionReport",
        "MetaData": {"MMSI": mmsi, "latitude": lat, "longitude": lon, "time_utc": stamp(at)},
        "Message": {"PositionReport": {"UserID": int(mmsi), "Sog": sog, "Cog": cog,
                                       "TrueHeading": int(cog) if cog < 360 else 511,
                                       "NavigationalStatus": 0}},
    }, now=at))
    if destination is not None or name:
        engine.ingest_ais(normalise({
            "MessageType": "ShipStaticData",
            "MetaData": {"MMSI": mmsi, "latitude": lat, "longitude": lon, "time_utc": stamp(at)},
            "Message": {"ShipStaticData": {"UserID": int(mmsi), "ImoNumber": imo, "Name": name,
                                           "CallSign": "X", "Destination": destination or "",
                                           "Eta": {}}},
        }, now=at))
    return engine.lookup("MMSI", mmsi)


class LaneInferenceTests(unittest.TestCase):
    def test_no_destination_means_no_lane(self):
        guess = infer_lane(12.8, 45.5, None)
        self.assertIsNone(guess.lane_code)
        self.assertIn("position alone", guess.reason)

    def test_gulf_of_oman_bound_for_mundra_is_the_gulf_lane(self):
        guess = infer_lane(24.5, 58.5, "INMUN")
        self.assertEqual(guess.lane_code, "GULF_IND")
        self.assertLess(guess.confidence, 1.0)

    def test_gulf_of_aden_bound_for_nhava_sheva_is_a_suez_lane_with_lower_confidence(self):
        guess = infer_lane(12.8, 45.5, "INNSA")
        self.assertEqual(guess.lane_code, "EUR_IND")
        self.assertIn("origin unknown", guess.reason)
        self.assertLess(guess.confidence, infer_lane(24.5, 58.5, "INMUN").confidence)

    def test_outside_every_region_is_not_placed(self):
        self.assertIsNone(infer_lane(-10.0, 60.0, "INNSA").lane_code)

    def test_a_coastal_destination_falls_back_to_the_coastal_lane(self):
        self.assertEqual(infer_lane(15.0, 72.0, "INNML").lane_code, "COAST_W")


class TimingTests(unittest.TestCase):
    def test_heading_towards_a_strait_gives_positive_hours(self):
        # Mid Red Sea, heading south: Bab-el-Mandeb ahead, Suez behind.
        hours = hours_to_chokepoints(20.0, 38.5, 15.0, 150.0, "EUR_IND")
        self.assertGreater(hours["BAB_EL_MANDEB"], 0)
        self.assertLess(hours["SUEZ"], 0)

    def test_not_making_way_gives_no_eta_but_still_marks_what_is_behind(self):
        hours = hours_to_chokepoints(20.0, 38.5, 0.1, 150.0, "EUR_IND")
        self.assertNotIn("BAB_EL_MANDEB", hours)
        self.assertLess(hours["SUEZ"], 0)

    def test_no_course_gives_no_timing(self):
        self.assertEqual(hours_to_chokepoints(20.0, 38.5, 0.1, None, "EUR_IND"), {})


class PlacementTests(unittest.TestCase):
    def setUp(self):
        self.engine = FusionEngine()

    def test_a_placed_hull_carries_every_confidence_it_earned(self):
        hull = fed(self.engine, "419000001", 12.8, 45.5, destination="INNSA")
        placed = place_hull(hull, now=NOW)
        v = placed.voyage
        self.assertTrue(v.observed)
        self.assertEqual(v.destination_port, "INNSA")
        self.assertEqual(v.destination_confidence, 0.9)
        self.assertEqual(v.lane_code, "EUR_IND")
        self.assertIsNotNone(v.lane_confidence)
        self.assertIsNotNone(v.timing_confidence)
        self.assertAlmostEqual(v.placement_confidence, 0.9 * v.lane_confidence * v.timing_confidence)
        self.assertLess(v.placement_confidence, 0.5)

    def test_an_unplaceable_hull_is_still_a_voyage_with_no_lane_and_zero_placement(self):
        hull = fed(self.engine, "419000002", 18.0, 70.0, sog=0.1, cog=360.0, name="", destination=None)
        placed = place_hull(hull, now=NOW)
        v = placed.voyage
        self.assertIsNone(v.destination_port)
        self.assertIsNone(v.lane_code)
        self.assertEqual(v.placement_confidence, 0.0)
        self.assertFalse(v.name_stated)
        self.assertEqual(v.name, "MMSI 419000002")            # a placeholder, labelled as one

    def test_a_foreign_destination_is_not_a_port_edge(self):
        hull = fed(self.engine, "419000003", 12.8, 45.5, destination="SGSIN")
        v = place_hull(hull, now=NOW).voyage
        self.assertIsNone(v.destination_port)
        self.assertIsNone(v.destination_confidence)

    def test_hulls_older_than_the_window_leave_the_graph(self):
        fed(self.engine, "419000004", 12.8, 45.5, destination="INNSA", at=NOW - timedelta(hours=3))
        fed(self.engine, "419000005", 12.8, 45.5, destination="INNSA", at=NOW - timedelta(minutes=5))
        placed = observed_voyages(self.engine, now=NOW)
        self.assertEqual([p.voyage.mmsi for p in placed], ["419000005"])

    def test_a_registry_hull_with_no_observation_is_not_an_observed_voyage(self):
        self.engine.register_fleet_vessel(vessel_id="f", name="F", imo=None)
        self.assertEqual(observed_voyages(self.engine, now=NOW), [])


class GraphTests(unittest.TestCase):
    def test_an_observed_voyage_becomes_a_node_with_its_provenance(self):
        engine = FusionEngine()
        hull = fed(engine, "419000001", 12.8, 45.5, destination="INNSA", name="SEEN", imo=9000001)
        voyage = place_hull(hull, now=NOW).voyage
        graph = build_world(voyages=[voyage], now=NOW)
        node = graph.node(key(VESSEL, voyage.vessel_id))
        self.assertEqual(node.attrs["source"], "OBSERVED_AIS")
        self.assertEqual(node.attrs["mmsi"], "419000001")
        self.assertEqual(node.attrs["imo"], "9000001")
        self.assertEqual(node.attrs["destination_confidence"], 0.9)
        self.assertLess(node.attrs["placement_confidence"], 1.0)
        sails = [e for e in graph.edges() if e.kind == SAILS and e.dst == node.key]
        self.assertEqual(len(sails), 1)
        self.assertEqual(sails[0].weight, 1.0)                  # the hull is on the lane
        self.assertEqual(sails[0].source, "OBSERVED_AIS")

    def test_a_fleet_voyage_is_unchanged_by_the_new_fields(self):
        graph = build_world(voyages=[VesselVoyage("V1", "MV Fleet", "EUR_IND", "INNSA",
                                                  {"BAB_EL_MANDEB": 40.0})], now=NOW)
        node = graph.node(key(VESSEL, "V1"))
        self.assertEqual(node.attrs["source"], "FLEET")
        self.assertNotIn("placement_confidence", node.attrs)

    def test_consequence_reaches_an_observed_hull_with_lower_confidence_not_lower_risk(self):
        from src.portwatch_os.world.cascade import propagate
        from src.portwatch_os.world.quantity import Quantity, RISK

        engine = FusionEngine()
        hull = fed(engine, "419000001", 20.0, 38.5, cog=150.0, destination="INNSA")   # Red Sea, southbound
        observed = place_hull(hull, now=NOW).voyage
        fleet = VesselVoyage("V1", "MV Fleet", "EUR_IND", "INNSA",
                             {"BAB_EL_MANDEB": observed.hours_to_chokepoint["BAB_EL_MANDEB"]})
        graph = build_world(voyages=[observed, fleet], now=NOW)
        lane = key(LANE, "EUR_IND")
        seed = Quantity(0.8, RISK, confidence=0.9, attrs={"chokepoint": "BAB_EL_MANDEB"})
        cascade = propagate(graph, lane, seed, at=NOW)
        reached = {r.node.identifier: r for r in cascade.reached.values()}
        a, b = reached[observed.vessel_id].quantities[RISK], reached["V1"].quantities[RISK]
        self.assertEqual(a.value, b.value)                     # the water is as dangerous
        self.assertLess(a.confidence, b.confidence)            # being in it is less certain
        self.assertTrue(a.attrs.get("observed"))
        self.assertEqual(a.attrs["placement_confidence"], observed.placement_confidence)


if __name__ == "__main__":
    unittest.main()
