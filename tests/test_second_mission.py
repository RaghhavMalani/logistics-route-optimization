"""The second mission, and the comparison that proves the engine is not Suez-shaped.

Biparjoy is a cyclone over two ports, not a ship across a canal. The world
must reach the inbound hulls through the ports (WEATHER -> ROUTE -> PORT),
the engine must offer holding and diverting and refuse a routing change
that still arrives into the closure, the scorecard must use each port's own
reopening, and the comparison must read both missions the same way.
"""

from __future__ import annotations

import unittest
from datetime import timedelta

from src.portwatch_os.decision import DecisionActor, DecisionEngine
from src.portwatch_os.decision.model import SHIPPING_COMPANY
from src.portwatch_os.missions import FutureLeak, MissionReplay, compare_missions, get_mission
from src.portwatch_os.world.cascade import propagate
from src.portwatch_os.world.graph import EVENT, PORT, THREATENS, key


class BiparjoyMissionTests(unittest.TestCase):
    def setUp(self):
        self.mission = get_mission("gulf-of-kutch-biparjoy-2023")
        self.replay = MissionReplay(self.mission, DecisionEngine(capacity=64), replay_id="test")
        self.actor = DecisionActor(SHIPPING_COMPANY, vessel_ids=tuple(v.vessel_id for v in self.mission.fleet))

    def test_the_mission_is_a_port_mission_with_a_sourced_sorted_recording(self):
        self.assertEqual(self.mission.subject_kind, "port")
        self.assertIsNone(self.mission.chokepoint)
        self.assertEqual(self.mission.ports, ["INIXY", "INMUN"])
        self.assertEqual(self.mission.event_category, "cyclone")
        ids = {s.source_id for s in self.mission.sources}
        for observation in self.mission.recording:
            self.assertIn(observation.source_id, ids)
        self.assertEqual(len(self.mission.visible(self.mission.start)), 4)
        self.assertEqual(len(self.mission.hidden(self.mission.start)), 7)
        # Every unstated time says so, and the outcome names its bounds.
        self.assertTrue(all(o.time_unstated for o in self.mission.recording if "post-market" in o.text or "evening" in o.text))
        self.assertIsNone(self.mission.outcome.ships_waiting_peak, "no source states a queue; none is invented")
        for port, window in self.mission.outcome.closures.items():
            self.assertIn("note", window, port)

    def test_the_world_reaches_the_inbound_hulls_through_the_ports_not_a_strait(self):
        event = self.replay.event()
        self.assertEqual(event.chokepoints, [])
        self.assertEqual(event.threatened_ports, ["INIXY", "INMUN"])
        state = self.replay.state()
        graph = state.graph
        threatened = {e.dst for e in graph.out_edges(key(EVENT, event.event_id)) if e.kind == THREATENS}
        self.assertEqual(threatened, {key(PORT, "INIXY"), key(PORT, "INMUN")})
        from src.portwatch_os.world.build import seed_for

        cascade = propagate(graph, key(EVENT, event.event_id), seed_for(event), at=self.replay.clock)
        for hull in self.mission.fleet:
            reached = cascade.reached.get(key("vessel", hull.vessel_id))
            self.assertIsNotNone(reached, hull.name)
            risk = reached.quantities["risk"]
            self.assertTrue(risk.attrs["closure"])
            self.assertEqual(risk.attrs["port"], hull.destination_port)
            self.assertAlmostEqual(risk.attrs["hours_to_risk_area"], hull.hours_to_destination_at_start, places=1)
        # The ports carry closure risk, and the cascade says the hold is not its to guess.
        self.assertIn("risk", cascade.reached[key(PORT, "INMUN")].quantities)
        self.assertTrue(any("computed per option by the decision engine" in n for n in cascade.notes))

    def test_the_engine_offers_holding_and_diverting_and_refuses_a_routing_change(self):
        near = self.replay.decide("BPJ-001", self.actor)
        rows = {r["kind"]: r for r in near.available_actions}
        self.assertNotEqual(rows["REROUTE"]["availability"]["status"], "AVAILABLE")
        self.assertIn("closure is at INIXY itself", rows["REROUTE"]["availability"]["reason"])
        ids = {o.option_id for o in near.options}
        self.assertIn("keep_plan", ids)
        self.assertIn("slow_steam", ids)
        diversions = [o for o in near.options if o.action == "CHANGE_DESTINATION_PORT"]
        self.assertTrue(diversions)
        for option in diversions:
            self.assertNotIn(option.params["portCode"], self.mission.ports, "never divert into the same closure")
        self.assertIn("arrives at INIXY in 36 h", near.do_nothing_statement)
        far = self.replay.decide("BPJ-003", self.actor)
        far_rows = {r["kind"]: r for r in far.available_actions}
        self.assertNotEqual(far_rows["SLOW_STEAM"]["availability"]["status"], "AVAILABLE")
        self.assertIn("after the claim lapses", far_rows["SLOW_STEAM"]["availability"]["reason"])
        self.assertEqual(far.recommendation.option_id, "keep_plan")

    def test_the_future_stays_hidden_until_the_reveal_then_each_port_scores_by_its_own_reopening(self):
        with self.assertRaises(FutureLeak):
            self.replay.outcome()
        for hull in self.mission.fleet:
            self.replay.decide(hull.vessel_id, self.actor)
        revealed = self.replay.reveal()
        cards = revealed["scorecards"]
        kutch, saurashtra, bhuj = cards["BPJ-001"], cards["BPJ-002"], cards["BPJ-003"]
        self.assertEqual(kutch["forecastError"]["subject"], "INIXY")
        self.assertEqual(saurashtra["forecastError"]["subject"], "INMUN")
        self.assertAlmostEqual(kutch["forecastError"]["blockedHours"], 78.7, places=1)
        self.assertAlmostEqual(saurashtra["forecastError"]["blockedHours"], 121.0, places=1)
        self.assertTrue(kutch["forecastError"]["closedOnArrival"])
        self.assertFalse(bhuj["forecastError"]["closedOnArrival"])
        for card in (kutch, saurashtra):
            realised = card["realised"]
            self.assertIn("keep_plan", realised)
            self.assertIn("slow_steam", realised)
            diversion = next(k for k in realised if k.startswith("change_destination_port"))
            self.assertIn("onward carriage", realised[diversion]["how"])
            self.assertIsNotNone(card["regretHours"])
        self.assertTrue(any("port claim" in line for line in kutch["learned"]))

    def test_the_replay_carries_the_ports_and_places_hulls_where_their_hours_say(self):
        geography = self.replay.geography()
        self.assertEqual(geography["subjectKind"], "port")
        self.assertEqual([p["code"] for p in geography["ports"]], ["INIXY", "INMUN"])
        by_id = {h["vesselId"]: h for h in geography["hulls"]}
        self.assertIn("past BAB_EL_MANDEB", by_id["BPJ-001"]["basis"])
        self.assertIn("past HORMUZ", by_id["BPJ-002"]["basis"])
        self.assertIn("short of SUEZ", by_id["BPJ-003"]["basis"])
        self.assertEqual(by_id["BPJ-001"]["hoursToDestination"], 36.0)
        self.replay.seek(self.mission.start + timedelta(hours=10))
        self.assertEqual(self.replay.geography()["hulls"][0]["hoursToDestination"], 26.0)


class ComparisonTests(unittest.TestCase):
    def test_both_missions_are_read_the_same_way_and_deterministically(self):
        first = compare_missions(engine=DecisionEngine(capacity=64))
        second = compare_missions(engine=DecisionEngine(capacity=64))
        self.assertEqual([m["missionId"] for m in first["missions"]],
                         ["suez-ever-given-2021", "gulf-of-kutch-biparjoy-2023"])
        keys = [row["key"] for row in first["table"]]
        for expected in ("forecastHorizonHours", "predictionErrorHours", "regret.meanHours",
                         "calibration.meanBrier", "dataCompleteness.statedTimeShare"):
            self.assertIn(expected, keys)
        for row in first["table"]:
            self.assertEqual(set(row["values"]), {"suez-ever-given-2021", "gulf-of-kutch-biparjoy-2023"})
        strip = lambda out: [(m["missionId"], m["regret"], m["calibration"], [h.get("recommended") for h in m["hulls"]])  # noqa: E731
                             for m in out["missions"]]
        self.assertEqual(strip(first), strip(second))
        suez, kutch = first["missions"]
        self.assertEqual(suez["subjectKind"], "chokepoint")
        self.assertEqual(kutch["subjectKind"], "port")
        self.assertEqual(suez["forecastHorizonHours"], 72.0)
        self.assertEqual(kutch["forecastHorizonHours"], 96.0)
        self.assertTrue(suez["dataCompleteness"]["queueFigureStated"])
        self.assertFalse(kutch["dataCompleteness"]["queueFigureStated"])

    def test_the_comparison_is_served(self):
        import os

        from fastapi.testclient import TestClient

        from backend.app.main import app

        os.environ["PORTWATCH_FRESHNESS_SCHEDULER"] = "0"
        with TestClient(app) as client:
            listed = client.get("/api/missions").json()["missions"]
            self.assertEqual({m["subjectKind"] for m in listed}, {"chokepoint", "port"})
            body = client.get("/api/missions/compare").json()
            self.assertEqual(len(body["missions"]), 2)
            self.assertTrue(body["table"])
            again = client.get("/api/missions/compare").json()
            self.assertEqual(body["table"], again["table"])


if __name__ == "__main__":
    unittest.main()
