"""The World State Engine: units, time, structure, propagation and provenance.

The engine's value is entirely in what it refuses to do. A graph that happily
multiplies a severity by a distance, counts one hull twice because its routing
is long, or reports a rupee figure nobody configured would be worse than no
graph at all -- it would be confidently wrong in the units a buyer acts on.

So most of what is asserted here is a refusal.
"""

from __future__ import annotations

import unittest
from datetime import timedelta

from src.portwatch_os.global_eye.exposure import VesselVoyage
from src.portwatch_os.global_eye.model import GlobalEvent
from src.portwatch_os.world.build import build_world, seed_for
from src.portwatch_os.world.cascade import narrate, propagate
from src.portwatch_os.world.graph import (
    CHOKEPOINT,
    EVENT,
    Edge,
    GraphError,
    LANE,
    Node,
    PORT,
    SAILS,
    THREATENS,
    VESSEL,
    WorldGraph,
    key,
)
from src.portwatch_os.world.quantity import (
    HOURS,
    INR,
    Interval,
    Quantity,
    RATIO,
    RISK,
    UnitError,
    VESSELS,
    aggregate,
    hours,
    risk,
    utc,
    window,
)
from src.portwatch_os.world.transfers import registered

NOW = utc()


def an_event(**overrides) -> GlobalEvent:
    base = dict(
        event_id="E-REDSEA",
        title="Red Sea escalation near Bab-el-Mandeb",
        category="conflict",
        region="Red Sea",
        lat=12.6,
        lon=43.3,
        geolocation_basis="chokepoint_centroid",
        first_seen=NOW.isoformat(),
        last_seen=NOW.isoformat(),
        source_count=5,
        confidence=0.82,
        severity=0.78,
        chokepoints=["BAB_EL_MANDEB"],
        horizon_hours=72.0,
    )
    base.update(overrides)
    return GlobalEvent(**base)


def a_voyage(vessel_id="PWD-001", hours_to=30.0, **overrides) -> VesselVoyage:
    base = dict(
        vessel_id=vessel_id,
        name=f"MV {vessel_id}",
        lane_code="EUR_IND",
        destination_port="INNSA",
        hours_to_chokepoint={"BAB_EL_MANDEB": hours_to, "SUEZ": hours_to + 40},
        service_speed_kn=16.0,
    )
    base.update(overrides)
    return VesselVoyage(**base)


# --------------------------------------------------------------------------
# quantities
# --------------------------------------------------------------------------


class QuantityTests(unittest.TestCase):
    def test_a_unit_the_graph_does_not_carry_is_refused(self):
        with self.assertRaises(UnitError):
            Quantity(1.0, "furlongs")

    def test_two_units_cannot_be_combined(self):
        """The whole point of the type: only a transfer moves between units."""
        with self.assertRaises(UnitError):
            risk(0.5).combined_with(hours(4.0))

    def test_risk_aggregates_by_noisy_or_not_by_addition(self):
        combined = risk(0.6).combined_with(risk(0.5))
        self.assertAlmostEqual(combined.value, 0.8)      # 1 - 0.4*0.5
        self.assertLessEqual(combined.value, 1.0)

    def test_durations_add(self):
        self.assertAlmostEqual(hours(4.0).combined_with(hours(6.5)).value, 10.5)

    def test_confidence_attenuates_along_a_chain(self):
        """A conclusion is never surer than the weakest inference in it."""
        start = risk(0.8, confidence=0.9)
        step = start.converted(12.0, HOURS, confidence=0.5)
        self.assertAlmostEqual(step.confidence, 0.45)

    def test_risk_is_clamped_and_hours_are_not(self):
        self.assertEqual(risk(1.7).value, 1.0)
        self.assertEqual(hours(500.0).value, 500.0)

    def test_aggregate_folds_one_quantity_per_unit(self):
        folded = aggregate([risk(0.5), risk(0.5), hours(3.0), hours(4.0)])
        self.assertEqual(sorted(folded), [HOURS, RISK])
        self.assertAlmostEqual(folded[HOURS].value, 7.0)


class IntervalTests(unittest.TestCase):
    def test_an_interval_cannot_end_before_it_starts(self):
        with self.assertRaises(ValueError):
            Interval(NOW, NOW - timedelta(hours=1))

    def test_an_open_interval_contains_everything(self):
        self.assertTrue(Interval().contains(NOW + timedelta(days=900)))

    def test_a_closed_interval_excludes_what_follows_it(self):
        w = window(NOW, 72.0)
        self.assertTrue(w.contains(NOW + timedelta(hours=71)))
        self.assertFalse(w.contains(NOW + timedelta(hours=73)))

    def test_clipping_two_intervals_gives_their_overlap(self):
        a = window(NOW, 48.0)
        b = window(NOW + timedelta(hours=24), 48.0)
        clipped = a.clipped_to(b)
        self.assertEqual(clipped.start, NOW + timedelta(hours=24))
        self.assertEqual(clipped.end, NOW + timedelta(hours=48))

    def test_disjoint_intervals_clip_to_an_empty_window(self):
        a = window(NOW, 1.0)
        b = window(NOW + timedelta(hours=10), 1.0)
        self.assertTrue(a.clipped_to(b).is_empty)


# --------------------------------------------------------------------------
# structure
# --------------------------------------------------------------------------


class GraphTests(unittest.TestCase):
    def setUp(self):
        self.graph = WorldGraph()
        self.graph.add_node(Node(key(EVENT, "E1"), EVENT, "An event"))
        self.graph.add_node(Node(key(CHOKEPOINT, "SUEZ"), CHOKEPOINT, "Suez"))

    def test_keys_are_typed_so_two_id_spaces_cannot_collide(self):
        """A vessel and a consignment may legitimately share an identifier."""
        self.assertNotEqual(key(VESSEL, "PWD-001"), key("cargo", "PWD-001"))

    def test_an_edge_to_a_node_that_does_not_exist_is_refused(self):
        """Otherwise a traversal stops early and looks small rather than wrong."""
        with self.assertRaises(GraphError) as caught:
            self.graph.add_edge(
                Edge(key(EVENT, "E1"), key(CHOKEPOINT, "HORMUZ"), THREATENS)
            )
        self.assertIn("not in", str(caught.exception))

    def test_an_edge_weight_outside_zero_to_one_is_refused(self):
        with self.assertRaises(GraphError):
            Edge(key(EVENT, "E1"), key(CHOKEPOINT, "SUEZ"), THREATENS, weight=4.0)

    def test_an_unknown_node_kind_is_refused(self):
        with self.assertRaises(GraphError):
            Node("weather:storm", "weather", "A storm")

    def test_a_temporal_view_drops_what_is_not_live(self):
        self.graph.add_node(
            Node(key(EVENT, "E2"), EVENT, "A lapsed event", interval=window(NOW, 6.0))
        )
        later = self.graph.at(NOW + timedelta(hours=48))
        self.assertIn(key(EVENT, "E1"), later)
        self.assertNotIn(key(EVENT, "E2"), later)


# --------------------------------------------------------------------------
# the rule catalogue
# --------------------------------------------------------------------------


class RuleCatalogueTests(unittest.TestCase):
    def test_every_rule_declares_what_it_explains(self):
        """A number whose unit change has no stated basis is not shippable."""
        for row in registered():
            self.assertTrue(row["explains"], f"{row['rule']} explains nothing")

    def test_the_catalogue_covers_the_chain_the_product_needs(self):
        pairs = {(r["on"], r["fromUnit"]) for r in registered()}
        for expected in [
            ("threatens", RISK),
            ("transits", RISK),
            ("sails", RISK),
            ("bound_for", RISK),
            (PORT, HOURS),
            (PORT, RATIO),
        ]:
            self.assertIn(expected, pairs, f"no rule for {expected}")


# --------------------------------------------------------------------------
# propagation
# --------------------------------------------------------------------------


class CascadeTests(unittest.TestCase):
    """The chain the product is named for, over the real lane catalogue."""

    def setUp(self):
        self.event = an_event()
        self.voyages = [
            a_voyage("PWD-001", 30.0),
            a_voyage("PWD-002", 55.0),
            a_voyage("PWD-003", 12.0),
        ]
        self.graph = build_world(
            events=[self.event], voyages=self.voyages, now=NOW
        )
        self.cascade = propagate(
            self.graph, key(EVENT, "E-REDSEA"), seed_for(self.event), at=NOW
        )

    def test_the_world_is_built_from_the_real_catalogues(self):
        summary = self.graph.summary()
        self.assertGreaterEqual(summary["byNodeKind"]["lane"], 10)
        self.assertGreaterEqual(summary["byNodeKind"]["port"], 10)

    def test_risk_reaches_the_chokepoint_the_event_names(self):
        reached = self.cascade.reached[key(CHOKEPOINT, "BAB_EL_MANDEB")]
        self.assertGreater(reached.quantities[RISK].value, 0.0)

    def test_it_reaches_only_lanes_that_actually_transit_that_water(self):
        """A routing fact, so a Malacca lane must not appear at all."""
        lanes = {r.node.identifier for r in self.cascade.by_kind(LANE)}
        self.assertIn("EUR_IND", lanes)
        self.assertNotIn("SEA_IND", lanes)      # transits Malacca, not Bab-el-Mandeb

    def test_each_hull_is_counted_once_however_long_its_routing(self):
        """EUR_IND transits two straits; that must not make one ship two ships.

        An edge per chokepoint applied the lane's risk once for each of them,
        so a vessel on a long routing counted several times and its exposure
        was inflated by the length of its own passage.
        """
        for reached in self.cascade.by_kind(VESSEL):
            self.assertEqual(
                reached.quantities[VESSELS].value, 1.0, reached.node.label
            )
        self.assertEqual(self.cascade.total(VESSELS).value, 3.0)

    def test_exposure_becomes_an_arrival_shift_in_hours_at_the_port(self):
        port = self.cascade.reached[key(PORT, "INNSA")]
        self.assertIn(HOURS, port.quantities)
        self.assertGreater(port.quantities[HOURS].value, 0.0)

    def test_the_arrival_shift_becomes_yard_pressure(self):
        port = self.cascade.reached[key(PORT, "INNSA")]
        self.assertIn(RATIO, port.quantities)

    def test_a_vessel_already_inside_the_water_gets_no_diversion_delay(self):
        """It cannot take the diversion, so a delay from one would be fiction."""
        inside = build_world(events=[self.event], voyages=[a_voyage("PWD-009", -8.0)],
                             now=NOW)
        cascade = propagate(inside, key(EVENT, "E-REDSEA"), seed_for(self.event),
                            at=NOW)
        port = cascade.reached.get(key(PORT, "INNSA"))
        self.assertIsNone(port)
        self.assertTrue(
            any("already inside" in note for note in cascade.notes), cascade.notes
        )

    def test_a_vessel_with_no_timing_is_declined_rather_than_guessed(self):
        blind = build_world(
            events=[self.event],
            voyages=[a_voyage("PWD-008", hours_to=30.0, hours_to_chokepoint={})],
            now=NOW,
        )
        cascade = propagate(blind, key(EVENT, "E-REDSEA"), seed_for(self.event),
                            at=NOW)
        self.assertEqual(cascade.by_kind(VESSEL), [])
        self.assertTrue(
            any("cannot be decided" in note for note in cascade.notes), cascade.notes
        )

    def test_money_is_refused_when_no_rate_is_configured(self):
        """An invented rupee figure is worse than none: it is the one quoted."""
        port = self.cascade.reached[key(PORT, "INNSA")]
        self.assertNotIn(INR, port.quantities)
        self.assertTrue(
            any("berth day rate" in note for note in self.cascade.notes),
            self.cascade.notes,
        )

    def test_money_appears_once_a_rate_is_configured(self):
        priced = build_world(events=[self.event], voyages=self.voyages, now=NOW)
        node = priced.require(key(PORT, "INNSA"))
        priced.add_node(
            Node(node.key, node.kind, node.label, node.interval,
                 {**node.attrs, "berth_day_rate_inr": 450000.0})
        )
        cascade = propagate(priced, key(EVENT, "E-REDSEA"), seed_for(self.event),
                            at=NOW)
        port = cascade.reached[key(PORT, "INNSA")]
        self.assertIn(INR, port.quantities)
        self.assertGreater(port.quantities[INR].value, 0.0)

    def test_a_lapsed_event_does_not_reach_anything_later(self):
        """The scrubber is a query, so a stale claim must not haunt the future."""
        later = NOW + timedelta(hours=96)     # past the 72h horizon
        cascade = propagate(
            self.graph, key(EVENT, "E-REDSEA"), seed_for(self.event), at=later
        )
        self.assertEqual(len(cascade.reached), 1)     # the seed, and nothing else

    def test_every_reached_node_can_explain_itself(self):
        """Evidence Mode is a read of the trace, not a separate explanation."""
        for node_key, reached in self.cascade.reached.items():
            if node_key == self.cascade.seed_key:
                continue
            steps = self.cascade.explain(node_key)
            self.assertTrue(steps, f"{node_key} cannot say where it came from")
            for step in steps:
                self.assertTrue(step.rule)

    def test_the_trace_names_the_catalogue_each_relationship_came_from(self):
        steps = self.cascade.explain(key(LANE, "EUR_IND"))
        self.assertTrue(any("TRADE_LANES" in s.edge.source for s in steps))

    def test_a_narrative_line_exists_for_the_chain(self):
        lines = narrate(self.cascade)
        self.assertTrue(any("Bab-el-Mandeb" in line for line in lines))


class StoppingTests(unittest.TestCase):
    """A world where everything affects everything ranks nothing."""

    def setUp(self):
        self.event = an_event()
        self.graph = build_world(
            events=[self.event], voyages=[a_voyage()], now=NOW
        )
        self.seed = seed_for(self.event)

    def test_a_confidence_floor_stops_a_long_chain(self):
        cascade = propagate(
            self.graph, key(EVENT, "E-REDSEA"), self.seed, at=NOW,
            confidence_floor=0.99,
        )
        self.assertEqual(len(cascade.reached), 1)

    def test_a_depth_limit_is_reported_rather_than_hidden(self):
        cascade = propagate(
            self.graph, key(EVENT, "E-REDSEA"), self.seed, at=NOW, max_depth=1,
        )
        self.assertTrue(cascade.truncated)

    def test_a_negligible_seed_reaches_nothing(self):
        cascade = propagate(
            self.graph, key(EVENT, "E-REDSEA"), risk(0.0001, confidence=0.9), at=NOW,
        )
        self.assertEqual(len(cascade.reached), 1)

    def test_a_cascade_terminates_on_a_graph_that_contains_a_cycle(self):
        """A vessel bound for a port that serves its lane is a real cycle."""
        cascade = propagate(self.graph, key(EVENT, "E-REDSEA"), self.seed, at=NOW)
        self.assertFalse(cascade.truncated)
        self.assertGreater(len(cascade.reached), 1)

    def test_an_unknown_seed_is_an_error_rather_than_an_empty_answer(self):
        with self.assertRaises(KeyError):
            propagate(self.graph, key(EVENT, "does-not-exist"), self.seed)


if __name__ == "__main__":
    unittest.main()
