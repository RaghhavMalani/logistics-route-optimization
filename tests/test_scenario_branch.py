"""Scenario branching: the observed world is frozen; a branch is a copy with
its assumptions written on every node and edge they touch.

What these tests defend: an assumption never edits the observed graph; every
assumed relation says ASSUMPTION; a closure produces a cascade the observed
world does not have; a diversion takes a hull off its lane and the cascade
stops reaching it; a branch knows when the world has moved on since the fork.
"""

from __future__ import annotations

import unittest
from datetime import datetime, timezone

from fastapi.testclient import TestClient

from backend.app.main import app
from src.portwatch_os.global_eye.exposure import VesselVoyage
from src.portwatch_os.world.branch import (
    Assumption,
    BranchError,
    BranchRegistry,
    ObservedWorldState,
    SOURCE_ASSUMPTION,
    branch,
    compare,
    propagate,
    reset_registry,
)
from src.portwatch_os.world.build import build_world
from src.portwatch_os.world.graph import CHOKEPOINT, EVENT, LANE, PORT, SAILS, VESSEL, key
from src.portwatch_os.world.live import Revision
from src.portwatch_os.world.quantity import Quantity, RISK

NOW = datetime(2026, 9, 13, 12, 0, tzinfo=timezone.utc)


def observed_world():
    voyages = [
        VesselVoyage("V1", "MV Fleet", "EUR_IND", "INNSA", {"BAB_EL_MANDEB": 30.0, "SUEZ": 60.0}),
        VesselVoyage("V2", "MV Gulf", "GULF_IND", "INMUN", {"HORMUZ": 12.0}),
    ]
    graph = build_world(voyages=voyages, now=NOW)
    revision = Revision(mode="DEMO", company_id=None, events_stamp="e", fleet_stamp="f", observed_generation=3)
    return ObservedWorldState(state_id="obs-test", revision=revision, at=NOW, graph=graph,
                              traffic_mode="SIMULATED_TRAFFIC")


class BranchTests(unittest.TestCase):
    def setUp(self):
        self.state = observed_world()

    def test_a_closure_is_an_assumed_event_the_observed_world_does_not_have(self):
        forked = branch(self.state, [Assumption("close_chokepoint", "BAB_EL_MANDEB", 0.9)],
                        branch_id="br-1", now=NOW)
        seed_key, seed = forked.seeds[0]
        self.assertEqual(seed_key, key(EVENT, "scenario:br-1:BAB_EL_MANDEB"))
        self.assertIsNone(self.state.graph.node(seed_key))                 # not in the observed world
        node = forked.graph.node(seed_key)
        self.assertEqual(node.attrs["source"], SOURCE_ASSUMPTION)
        edges = [e for e in forked.graph.edges() if e.src == seed_key]
        self.assertEqual(len(edges), 1)
        self.assertEqual(edges[0].source, SOURCE_ASSUMPTION)
        self.assertEqual(edges[0].dst, key(CHOKEPOINT, "BAB_EL_MANDEB"))

        cascade = propagate(forked.graph, seed_key, seed, at=NOW)
        reached = {r.node.identifier for r in cascade.reached.values() if r.node.kind == VESSEL}
        self.assertIn("V1", reached)                                        # the Suez-lane hull
        self.assertNotIn("V2", reached)                                     # the Gulf hull is elsewhere
        # And the step across the assumed edge is legible as assumed.
        self.assertTrue(any(step.edge.source == SOURCE_ASSUMPTION for step in cascade.steps))

    def test_the_observed_graph_is_never_edited(self):
        before = (len(self.state.graph), len(self.state.graph.edges()))
        branch(self.state, [
            Assumption("close_chokepoint", "HORMUZ", 1.0),
            Assumption("divert_vessel", "V1"),
            Assumption("derate_port", "INNSA", 0.6),
        ], branch_id="br-2", now=NOW)
        self.assertEqual((len(self.state.graph), len(self.state.graph.edges())), before)
        self.assertIsNone(self.state.graph.node(key(VESSEL, "V1")).attrs.get("assumption"))
        self.assertNotIn("capacity_factor", self.state.graph.node(key(PORT, "INNSA")).attrs)

    def test_a_diverted_hull_leaves_its_lane_and_the_cascade_no_longer_reaches_it(self):
        seed = Quantity(0.8, RISK, confidence=0.9, attrs={"chokepoint": "BAB_EL_MANDEB"})
        observed = propagate(self.state.graph, key(LANE, "EUR_IND"), seed, at=NOW)
        self.assertIn(key(VESSEL, "V1"), observed.reached)

        forked = branch(self.state, [Assumption("divert_vessel", "V1")], branch_id="br-3", now=NOW)
        sails = [e for e in forked.graph.edges() if e.kind == SAILS and e.dst == key(VESSEL, "V1")]
        self.assertEqual(sails, [])
        node = forked.graph.node(key(VESSEL, "V1"))
        self.assertEqual(node.attrs["assumption"]["source"], SOURCE_ASSUMPTION)
        self.assertEqual(node.attrs["diverted_from"], "EUR_IND")
        self.assertGreater(node.attrs["detour_hours"], 0)
        branched = propagate(forked.graph, key(LANE, "EUR_IND"), seed, at=NOW)
        self.assertNotIn(key(VESSEL, "V1"), branched.reached)
        diff = compare(observed, branched)
        self.assertIn(key(VESSEL, "V1"), diff["noLongerReached"])
        self.assertLess(diff["totals"]["vessels"]["delta"], 0)

    def test_a_diversion_onto_a_named_lane_relinks_the_hull(self):
        forked = branch(self.state, [Assumption("divert_vessel", "V1", lane_code="EAF_IND")], branch_id="br-4", now=NOW)
        sails = [e for e in forked.graph.edges() if e.kind == SAILS and e.dst == key(VESSEL, "V1")]
        self.assertEqual(len(sails), 1)
        self.assertEqual(sails[0].src, key(LANE, "EAF_IND"))
        self.assertEqual(sails[0].source, SOURCE_ASSUMPTION)

    def test_a_derated_port_keeps_its_observed_capacity_beside_the_assumed_one(self):
        forked = branch(self.state, [Assumption("derate_port", "INNSA", 0.5)], branch_id="br-5", now=NOW)
        attrs = forked.graph.node(key(PORT, "INNSA")).attrs
        self.assertEqual(attrs["capacity_factor"], 0.5)
        self.assertAlmostEqual(attrs["capacity"], attrs["capacity_observed"] * 0.5)

    def test_an_impossible_assumption_is_refused_with_a_reason(self):
        with self.assertRaises(BranchError):
            branch(self.state, [Assumption("close_chokepoint", "PANAMA_X")], branch_id="x", now=NOW)
        with self.assertRaises(BranchError):
            branch(self.state, [Assumption("divert_vessel", "nobody")], branch_id="x", now=NOW)
        with self.assertRaises(BranchError):
            Assumption.from_dict({"kind": "teleport", "subject": "V1"})

    def test_a_branch_knows_when_the_world_moved_on(self):
        forked = branch(self.state, [Assumption("close_chokepoint", "HORMUZ")], branch_id="br-6", now=NOW)
        same = self.state.revision
        later = Revision(mode="DEMO", company_id=None, events_stamp="e", fleet_stamp="f", observed_generation=4)
        self.assertFalse(forked.summary(current_revision=same)["observedWorldMovedOn"])
        self.assertTrue(forked.summary(current_revision=later)["observedWorldMovedOn"])

    def test_the_registry_is_bounded(self):
        registry = BranchRegistry(capacity=2)
        ids = [registry.create(self.state, [Assumption("close_chokepoint", "HORMUZ")], now=NOW).branch_id
               for _ in range(3)]
        self.assertIsNone(registry.get(ids[0]))
        self.assertIsNotNone(registry.get(ids[2]))


class BranchApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(app)

    def setUp(self):
        reset_registry()
        self.addCleanup(reset_registry)

    def test_observed_state_and_a_closure_branch_over_http(self):
        observed = self.client.get("/api/world/observed?mode=DEMO").json()
        self.assertIn("stateId", observed["state"])
        self.assertEqual(observed["branches"], [])

        created = self.client.post("/api/world/branches", json={
            "mode": "DEMO",
            "assumptions": [{"kind": "close_chokepoint", "subject": "BAB_EL_MANDEB", "value": 0.9,
                             "note": "what if the strait closes tonight"}],
        }).json()
        branch_id = created["branch"]["branchId"]
        self.assertEqual(created["branch"]["assumptions"][0]["source"], "ASSUMPTION")
        self.assertFalse(created["branch"]["observedWorldMovedOn"])
        seed = created["branch"]["seeds"][0].split(":", 1)[1]

        body = self.client.get(f"/api/world/branches/{branch_id}/cascades/{seed}?mode=DEMO").json()
        self.assertTrue(body["assumed"])
        self.assertIsNone(body["observed"])                     # the observed world has no such event
        self.assertGreater(len(body["branched"]["affected"]["lanes"]), 0)
        self.assertTrue(any(step["source"] == "ASSUMPTION" for step in body["branched"]["steps"]))

    def test_a_branch_refuses_a_bad_assumption(self):
        self.assertEqual(self.client.post("/api/world/branches", json={"assumptions": []}).status_code, 400)
        self.assertEqual(self.client.post("/api/world/branches", json={
            "assumptions": [{"kind": "close_chokepoint", "subject": "NOWHERE"}],
        }).status_code, 400)
        self.assertEqual(self.client.get("/api/world/branches/br-9999/cascades/x").status_code, 404)


if __name__ == "__main__":
    unittest.main()
