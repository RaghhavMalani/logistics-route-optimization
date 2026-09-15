"""Entity fusion: IMO and MMSI are keys, a name is not, and nothing is lost.

Each test is a case a real feed produces. A transponder that reports for an
hour before it says its name. A registry entry with no IMO and a transponder
with the same name. A static report with the IMO fat-fingered. A transponder
that goes quiet for six weeks and comes back on a different ship. The engine
has to get each of these right, and -- more importantly -- has to leave behind
enough that a person can see what it decided and why.
"""

from __future__ import annotations

import unittest
from datetime import datetime, timedelta, timezone

from src.portwatch_os.fabric.ais import normalise
from src.portwatch_os.fusion import (
    ATTR_NAME,
    ATTR_POSITION,
    FLEET_ID,
    FLEET_REGISTRY,
    FusionEngine,
    IMO,
    MMSI,
    OBSERVED_AIS,
    STRONG,
    resolve_destination,
)

NOW = datetime(2026, 9, 12, 12, 0, tzinfo=timezone.utc)


def stamp(moment):
    return moment.strftime("%Y-%m-%d %H:%M:%S.%f") + "000 +0000 UTC"


def position(mmsi="419001234", at=NOW, lat=12.6, lon=43.3):
    return normalise({
        "MessageType": "PositionReport",
        "MetaData": {"MMSI": mmsi, "ShipName": "META", "latitude": lat, "longitude": lon,
                     "time_utc": stamp(at)},
        "Message": {"PositionReport": {"UserID": int(mmsi), "Sog": 10.0, "Cog": 90.0,
                                       "TrueHeading": 90, "NavigationalStatus": 0}},
    }, now=at, raw_ref=f"raw:{mmsi}:{at.isoformat()}")


def static(mmsi="419001234", imo=9876543, name="MV KONKAN", at=NOW, destination="INNSA"):
    return normalise({
        "MessageType": "ShipStaticData",
        "MetaData": {"MMSI": mmsi, "latitude": 12.6, "longitude": 43.3, "time_utc": stamp(at)},
        "Message": {"ShipStaticData": {"UserID": int(mmsi), "ImoNumber": imo, "Name": name,
                                       "CallSign": "VTKK", "Destination": destination,
                                       "Eta": {"Month": 9, "Day": 14, "Hour": 6, "Minute": 0}}},
    }, now=at, raw_ref=f"raw:static:{mmsi}")


class StrongKeyTests(unittest.TestCase):
    def setUp(self):
        self.engine = FusionEngine()

    def test_a_first_position_creates_a_hull_keyed_by_mmsi_only(self):
        outcome = self.engine.ingest_ais(position())
        self.assertTrue(outcome.created)
        hull = outcome.canonical
        self.assertEqual(hull.mmsis, ["419001234"])
        self.assertIsNone(hull.imo)
        self.assertIsNone(hull.name)                 # nobody said a name
        self.assertTrue(hull.observed)
        self.assertEqual(hull.attribute(ATTR_POSITION)["lat"], 12.6)
        link = hull.links[0]
        self.assertEqual((link.key_kind, link.key_value, link.strength), (MMSI, "419001234", STRONG))
        self.assertTrue(link.evidence)              # rests on assertions, not on nothing

    def test_static_data_attaches_the_imo_to_the_same_hull(self):
        first = self.engine.ingest_ais(position()).canonical
        outcome = self.engine.ingest_ais(static())
        self.assertIs(outcome.canonical, first)
        self.assertEqual(first.imo, "9876543")
        self.assertEqual(first.name, "MV KONKAN")
        self.assertEqual({l.key_kind for l in first.links if l.active}, {MMSI, IMO})
        self.assertIs(self.engine.lookup(IMO, "9876543"), first)

    def test_two_transponders_with_one_imo_are_one_hull(self):
        """Reflagged mid-history: the IMO proves it, and the earlier
        MMSI-only hull is folded in with its evidence intact."""
        self.engine.ingest_ais(static(mmsi="419000001", imo=5550001))
        self.engine.ingest_ais(position(mmsi="419000002"))            # a new hull, so far
        self.assertEqual(len(self.engine.vessels()), 2)
        outcome = self.engine.ingest_ais(static(mmsi="419000002", imo=5550001))
        self.assertEqual(len(self.engine.vessels()), 1)
        hull = outcome.canonical
        self.assertEqual(sorted(hull.mmsis), ["419000001", "419000002"])
        self.assertIsNotNone(outcome.merged_from)
        # Nothing was lost: both transponders' assertions are on the hull.
        subjects = {a.subject_value for a in hull.assertions}
        self.assertEqual(subjects, {"419000001", "419000002"})
        # And the fold is recorded as retracted links, not silence.
        self.assertTrue(any(l.retracted_at for l in hull.links))

    def test_a_registry_imo_links_to_the_observed_hull(self):
        self.engine.ingest_ais(static(imo=9876543))
        outcome = self.engine.register_fleet_vessel(vessel_id="fleet-7", name="KONKAN EXPRESS", imo="9876543")
        self.assertFalse(outcome.created)
        hull = outcome.canonical
        self.assertEqual(hull.fleet_ids, ["fleet-7"])
        self.assertEqual(hull.mmsis, ["419001234"])
        # The registry outranks the typed AIS name, and the disagreement is kept.
        self.assertEqual(hull.name, "KONKAN EXPRESS")
        self.assertEqual(hull.attributes[ATTR_NAME].source_kind, FLEET_REGISTRY)
        self.assertTrue(any(c.attribute == ATTR_NAME for c in hull.conflicts))

    def test_position_outranks_the_registry_where_the_hull_is(self):
        self.engine.register_fleet_vessel(vessel_id="fleet-1", name="X", imo="1234567",
                                          position={"lat": 0.0, "lon": 0.0})
        hull = self.engine.ingest_ais(static(imo=1234567)).canonical
        self.engine.ingest_ais(position(lat=15.0, lon=70.0))
        self.assertEqual(hull.attribute(ATTR_POSITION)["lat"], 15.0)
        self.assertEqual(hull.attributes[ATTR_POSITION].source_kind, OBSERVED_AIS)


class NameIsNotAKeyTests(unittest.TestCase):
    def setUp(self):
        self.engine = FusionEngine()

    def test_a_registry_entry_without_an_imo_is_not_merged_by_name(self):
        """The demo fleet has no IMOs. A transponder with the same name is a
        candidate for a person, and two hulls remain two hulls."""
        fleet = self.engine.register_fleet_vessel(vessel_id="fleet-3", name="MV KONKAN", imo=None)
        observed = self.engine.ingest_ais(static(name="MV KONKAN", imo=0))
        self.assertEqual(len(self.engine.vessels()), 2)
        self.assertIsNot(fleet.canonical, observed.canonical)
        self.assertEqual(fleet.canonical.mmsis, [])
        self.assertEqual(observed.canonical.fleet_ids, [])
        candidate = observed.candidates[0]
        self.assertEqual(candidate.canonical_id, fleet.canonical.canonical_id)
        self.assertFalse(candidate.to_dict()["applied"])
        self.assertIn("not an identifier", candidate.reason)
        # And it is visible from both sides.
        self.assertEqual(fleet.canonical.candidates[0].canonical_id, observed.canonical.canonical_id)

    def test_two_transponders_sharing_a_name_stay_apart(self):
        a = self.engine.ingest_ais(static(mmsi="419000001", imo=0, name="SEA STAR")).canonical
        b = self.engine.ingest_ais(static(mmsi="419000002", imo=0, name="SEA STAR")).canonical
        self.assertIsNot(a, b)
        self.assertIsNone(self.engine.lookup("NAME", "SEA STAR"))    # no such link exists

    def test_registering_the_same_fleet_id_twice_does_not_duplicate(self):
        self.engine.register_fleet_vessel(vessel_id="fleet-3", name="A", imo=None)
        self.engine.register_fleet_vessel(vessel_id="fleet-3", name="A", imo=None)
        self.assertEqual(len(self.engine.vessels()), 1)


class SafeguardTests(unittest.TestCase):
    def setUp(self):
        self.engine = FusionEngine(imo_claims_before_move=2, mmsi_reuse_window=timedelta(days=30))

    def test_one_conflicting_imo_report_does_not_move_the_transponder(self):
        hull = self.engine.ingest_ais(static(imo=1111111)).canonical
        outcome = self.engine.ingest_ais(static(imo=2222222))            # a typo, perhaps
        self.assertIs(outcome.canonical, hull)
        self.assertEqual(hull.imo, "1111111")
        self.assertEqual(len(self.engine.vessels()), 1)
        self.assertEqual(len(outcome.conflicts), 1)
        self.assertIn("not re-identified on a single static report", outcome.conflicts[0].reason)

    def test_a_repeated_conflicting_imo_moves_the_transponder_with_a_record(self):
        old = self.engine.ingest_ais(static(imo=1111111)).canonical
        self.engine.ingest_ais(static(imo=2222222))
        outcome = self.engine.ingest_ais(static(imo=2222222))
        new = outcome.canonical
        self.assertIsNot(new, old)
        self.assertEqual(new.imo, "2222222")
        self.assertEqual(new.mmsis, ["419001234"])
        self.assertEqual(old.mmsis, [])                                # moved off
        self.assertEqual(old.imo, "1111111")                           # the hull keeps its number
        retracted = [l for l in old.links if l.retracted_at is not None]
        self.assertEqual(len(retracted), 1)
        self.assertIn("moved hull", retracted[0].retraction_reason)
        self.assertIs(self.engine.lookup(MMSI, "419001234"), new)

    def test_a_transponder_back_after_the_reuse_window_under_a_new_name_is_a_new_hull(self):
        old = self.engine.ingest_ais(static(imo=0, name="OLD NAME")).canonical
        later = NOW + timedelta(days=45)
        outcome = self.engine.ingest_ais(static(imo=0, name="NEW NAME", at=later))
        self.assertTrue(outcome.created)
        self.assertIsNot(outcome.canonical, old)
        self.assertEqual(old.mmsis, [])
        self.assertIn("possible reassignment", outcome.notes[0])
        self.assertIn("possible reassignment", old.links[0].retraction_reason)

    def test_a_transponder_back_after_the_window_with_the_same_name_is_the_same_hull(self):
        old = self.engine.ingest_ais(static(imo=0, name="SAME")).canonical
        outcome = self.engine.ingest_ais(static(imo=0, name="SAME", at=NOW + timedelta(days=45)))
        self.assertIs(outcome.canonical, old)

    def test_a_silent_return_without_a_name_is_not_treated_as_reassigned(self):
        """A position report says nothing about who; it cannot contradict."""
        old = self.engine.ingest_ais(static(imo=0, name="SAME")).canonical
        outcome = self.engine.ingest_ais(position(at=NOW + timedelta(days=45)))
        self.assertIs(outcome.canonical, old)


class ProvenanceTests(unittest.TestCase):
    def test_every_attribute_names_the_assertion_it_rests_on(self):
        engine = FusionEngine()
        hull = engine.ingest_ais(static()).canonical
        for name, held in hull.attributes.items():
            matching = [a for a in hull.assertions if a.assertion_id == held.assertion_id]
            self.assertEqual(len(matching), 1, name)
            self.assertEqual(matching[0].raw_ref, "raw:static:419001234")

    def test_explain_returns_the_whole_record(self):
        engine = FusionEngine()
        hull = engine.ingest_ais(position()).canonical
        engine.ingest_ais(static())
        body = engine.explain(hull.canonical_id)
        self.assertEqual(body["imo"], "9876543")
        self.assertEqual(len(body["links"]), 2)
        self.assertGreaterEqual(len(body["assertions"]), 6)
        self.assertEqual(body["sourceKinds"], [OBSERVED_AIS])
        self.assertTrue(body["observed"])

    def test_stats_count_what_was_decided_and_what_was_not(self):
        engine = FusionEngine()
        engine.register_fleet_vessel(vessel_id="f", name="TWIN", imo=None)
        engine.ingest_ais(static(imo=0, name="TWIN"))
        stats = engine.stats()
        self.assertEqual(stats["vessels"], 2)
        self.assertEqual(stats["observed"], 1)
        self.assertEqual(stats["candidates"], 2)


class DestinationTests(unittest.TestCase):
    def test_a_locode_resolves_with_high_confidence(self):
        r = resolve_destination("INNSA")
        self.assertEqual((r.port_code, r.method, r.confidence), ("INNSA", "LOCODE", 0.9))

    def test_a_spaced_locode_still_resolves(self):
        self.assertEqual(resolve_destination("IN NSA").port_code, "INNSA")

    def test_a_name_resolves_with_lower_confidence(self):
        r = resolve_destination("NHAVA SHEVA")
        self.assertEqual((r.port_code, r.method, r.confidence), ("INNSA", "NAME", 0.7))
        self.assertEqual(resolve_destination("JNPT").port_code, "INNSA")
        self.assertEqual(resolve_destination("VIZAG").port_code, "INVTZ")

    def test_the_last_leg_of_a_route_is_the_destination(self):
        self.assertEqual(resolve_destination("COLOMBO > INMAA").port_code, "INMAA")
        self.assertEqual(resolve_destination("MUNDRA VIA COLOMBO").port_code, "INMUN")

    def test_a_foreign_locode_is_not_resolved_and_says_why(self):
        r = resolve_destination("SGSIN")
        self.assertFalse(r.resolved)
        self.assertEqual(r.method, "FOREIGN")
        self.assertIn("SG", r.reason)

    def test_india_without_a_known_port_is_low_confidence_and_unresolved(self):
        r = resolve_destination("IN XYZ")
        self.assertFalse(r.resolved)
        self.assertEqual((r.method, r.confidence), ("COUNTRY", 0.2))

    def test_for_orders_and_empty_are_nothing(self):
        self.assertEqual(resolve_destination("FOR ORDERS").method, "NONE")
        self.assertEqual(resolve_destination("").method, "NONE")
        self.assertEqual(resolve_destination(None).method, "NONE")

    def test_a_legacy_locode_maps_to_the_modelled_port(self):
        self.assertEqual(resolve_destination("INHAL").port_code, "INCCU")


if __name__ == "__main__":
    unittest.main()
