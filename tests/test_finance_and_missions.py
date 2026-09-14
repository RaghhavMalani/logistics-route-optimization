"""The financial twin and the historical mission engine.

Money: two currencies never add without an FX observation; a rate never
applies to the wrong unit; an assumption is labelled on every figure it
touches; a public tariff carries its citation and prices only inside its
validity; an unknown component keeps the total unknown rather than zero.

Missions: the recording is sorted and sourced; the replay serves only what
was knowable at its clock and refuses the rest until the reveal; the world
built at the clock carries no later claim; the scorecard scores the
recommendation against the revealed outcome and applies the outcome to
every option so "would another have been better" is answered from facts.

The API: a company is refused the advisory handoff and told why; a port
authority's approved staggering becomes DRAFT advisories under the store's
own authorisation; the mission routes keep the future hidden.
"""

from __future__ import annotations

import os
import unittest
from datetime import datetime, timedelta, timezone

from src.portwatch_os.decision import DecisionActor, DecisionEngine
from src.portwatch_os.decision.model import SHIPPING_COMPANY
from src.portwatch_os.finance import (
    CostBasis,
    CurrencyMismatch,
    DimensionError,
    FxObservation,
    FxTable,
    FxUnavailable,
    Money,
    Pricer,
    Quantity,
    Rate,
    assumption,
    avoidable_cost,
    basis_with_public_tariffs,
    load_public_tariffs,
)
from src.portwatch_os.finance.money import DAY, GRT, HOUR, TEU, TONNE
from src.portwatch_os.finance.tariffs import TariffError, parse_schedule
from src.portwatch_os.ledger.store import SqliteLedgerStore
from src.portwatch_os.missions import FutureLeak, MissionError, MissionReplay, get_mission
from src.portwatch_os.missions.model import Mission, Observation, Outcome, Source
from src.portwatch_os.world.graph import EVENT, key

NOW = datetime(2026, 9, 13, 12, 0, tzinfo=timezone.utc)


# --------------------------------------------------------------------------
# money
# --------------------------------------------------------------------------


class MoneyTests(unittest.TestCase):
    def test_currencies_do_not_add_without_fx(self):
        with self.assertRaises(CurrencyMismatch):
            Money(1, "USD") + Money(1, "INR")
        with self.assertRaises(FxUnavailable):
            FxTable().total([Money(1, "USD"), Money(83, "INR")], currency="USD")
        table = FxTable([FxObservation("USD", "INR", 83.0, "2026-09-13T00:00:00Z", "test reference rate")])
        total, used = table.total([Money(1, "USD"), Money(83, "INR")], currency="USD")
        self.assertAlmostEqual(total.amount, 2.0)
        self.assertEqual([o.source for o in used], ["test reference rate"])

    def test_rates_refuse_the_wrong_unit_and_convert_only_time(self):
        charter = Rate(41000, "USD", DAY)
        self.assertAlmostEqual((charter * Quantity(12, HOUR)).amount, 20500.0)
        with self.assertRaises(DimensionError):
            charter * Quantity(3, TONNE)
        with self.assertRaises(DimensionError):
            Quantity(3, TEU).converted(DAY)
        with self.assertRaises(DimensionError):
            Rate(1.0, "USD", "furlong")

    def test_unknown_is_not_zero_in_a_total(self):
        basis = CostBasis([assumption("charter_day", 41000, "USD", entered_by="operator")])
        pricer = Pricer(basis, at=NOW, currency="USD")
        components = [
            pricer.priced("delay", "Cost of delay", "charter_day", Quantity(24, HOUR)),
            pricer.priced("fuel", "Fuel difference", "bunker_price_t", Quantity(10, TONNE)),   # no basis
            pricer.zero("action", "Cost of action", "no direct charge"),
        ]
        evaluation = pricer.evaluation(components)
        states = {c.key: c.state for c in evaluation.components}
        self.assertEqual(states, {"delay": "KNOWN", "fuel": "UNKNOWN", "action": "ZERO"})
        self.assertIsNone(evaluation.total)
        self.assertAlmostEqual(evaluation.partial_total.amount, 41000.0)
        self.assertTrue(evaluation.assumption)
        self.assertEqual(evaluation.to_dict()["label"], "ASSUMPTION")
        comparison = avoidable_cost(evaluation, evaluation)
        self.assertFalse(comparison["available"])
        self.assertIn("Fuel difference", comparison["reason"])

    def test_an_assumption_must_name_who_entered_it(self):
        with self.assertRaises(ValueError):
            assumption("charter_day", 1.0, "USD", entered_by="")

    def test_public_tariffs_are_cited_and_lapse(self):
        schedules = {s.schedule_id: s for s in load_public_tariffs()}
        jnpa = schedules["jnpa-sor-2026-27"]
        self.assertEqual(jnpa.source_type, "PUBLIC_TARIFF")
        self.assertEqual(jnpa.reuse, "REQUIRES_REVIEW")
        for rate in jnpa.rates:
            self.assertTrue(rate.provenance["verbatim"])
            self.assertTrue(rate.provenance["sha256"])
            self.assertTrue(rate.provenance["url"].startswith("https://www.jnport.gov.in/"))
        chennai = schedules["chpa-indexed-sor-2025-26"]
        self.assertTrue(any("successor" in n.lower() or "PROPOSED" in n for n in chennai.notes))
        basis = basis_with_public_tariffs()
        self.assertIsNone(basis.lookup("port_dues_grt", at=NOW, scope="INMAA", vessel_status="foreign",
                                       vessel_type="container").rate)
        dues = basis.lookup("port_dues_grt", at=NOW, scope="INNSA", vessel_status="foreign",
                            vessel_type="container").rate
        self.assertEqual(dues.value, 0.1558)
        pilotage = basis.lookup("pilotage_grt", at=NOW, scope="INNSA", vessel_status="foreign", gt=45000).rate
        self.assertAlmostEqual(pilotage.charge_for_grt(45000).amount, 10393 + 0.2776 * 15000, places=2)

    def test_a_tariff_row_without_its_citation_is_refused(self):
        with self.assertRaises(TariffError):
            parse_schedule({
                "scheduleId": "x", "title": "x", "scope": "INNSA",
                "provenance": {"url": "https://example.invalid", "retrievedAt": "2026-09-13T00:00:00Z", "sha256": "0"},
                "rates": [{"primitive": "port_dues_grt", "value": 1.0, "currency": "USD"}],
            })


# --------------------------------------------------------------------------
# missions
# --------------------------------------------------------------------------


def engine():
    return DecisionEngine(basis=basis_with_public_tariffs(), ledger=SqliteLedgerStore(":memory:"))


class MissionTests(unittest.TestCase):
    def test_the_chronology_is_sorted_sourced_and_has_a_hidden_future(self):
        mission = get_mission("suez-ever-given-2021")
        instants = [o.at for o in mission.recording]
        self.assertEqual(instants, sorted(instants))
        ids = {s.source_id for s in mission.sources}
        self.assertTrue(all(o.source_id in ids for o in mission.recording))
        self.assertTrue(all(s.url.startswith("https://") and s.retrieved_at for s in mission.sources))
        self.assertEqual(len(mission.visible(mission.start)), 2)
        self.assertEqual(len(mission.hidden(mission.start)), 9)
        self.assertTrue(all(v.name.endswith("(illustrative)") for v in mission.fleet))

    def test_a_mission_without_a_source_is_refused(self):
        with self.assertRaises(MissionError):
            Mission(
                mission_id="m", name="m", start_timestamp="2021-01-01T00:00:00Z", chokepoint="SUEZ",
                event_category="canal_restriction", event_title="t",
                sources=[Source("s", "s", "https://x", "k", "2026-01-01T00:00:00Z")],
                recording=[Observation("2021-01-01T00:00:00Z", "report", "x", "missing-source")],
                fleet=[], outcome=Outcome("2021-01-02T00:00:00Z", "2021-01-01T00:00:00Z", "2021-01-03",
                                           "2021-01-03T23:59:00Z", None, None, "", ["s"]),
                evaluation_window_hours=24.0,
            )

    def test_the_replay_serves_nothing_from_the_future_until_revealed(self):
        replay = MissionReplay(get_mission("suez-ever-given-2021"), engine())
        self.assertEqual(len(replay.observations()), 2)
        with self.assertRaises(FutureLeak):
            replay.hidden()
        with self.assertRaises(FutureLeak):
            replay.outcome()
        # The event as built carries only the visible claim: severity from the
        # grounding report, confidence from the morning corroboration, and a
        # claim horizon -- never the reopening, which is five days away.
        event = replay.event()
        self.assertEqual(event.first_seen, "2021-03-23T08:00:00Z")
        self.assertEqual(event.confidence, 0.85)
        state = replay.state()
        node = state.graph.node(key(EVENT, event.event_id))
        self.assertEqual(node.interval.end, replay.clock + timedelta(hours=72))
        # Seeking forward reveals only what had happened by then.
        replay.seek(replay.mission.start + timedelta(hours=60))
        self.assertEqual(len(replay.observations()), 4)
        self.assertEqual(replay.mission.claim_at(replay.clock)["status"], "suspended")
        self.assertNotIn("reopened", [o["claim"].get("status") for o in replay.observations()])

    def test_the_scorecard_scores_every_option_against_the_revealed_outcome(self):
        replay = MissionReplay(get_mission("suez-ever-given-2021"), engine())
        problem = replay.decide("MSN-001", DecisionActor(SHIPPING_COMPANY))
        self.assertEqual(problem.evidence["replay"]["missionId"], "suez-ever-given-2021")
        self.assertIn("source_freshness", [c["name"] for c in problem.baseline.critic["checks"]])
        recommended = problem.recommendation.option_id
        replay.choose("MSN-001", recommended, actor="ops")
        out = replay.reveal(actor="ops")
        card = out["scorecards"]["MSN-001"]
        self.assertEqual(card["forecastError"]["blockedHours"], 155.3)
        self.assertGreater(card["forecastError"]["persistenceErrorHours"], 0)      # the 72 h claim undershot
        self.assertTrue(card["forecastError"]["closedOnArrival"])
        self.assertIn("keep_plan", card["realised"])
        self.assertIn("reroute", card["realised"])
        self.assertEqual(card["selected"], recommended)
        self.assertIsNotNone(card["regretHours"])
        self.assertIn(card["realisedBest"], card["realised"])
        self.assertTrue(card["learned"])
        # After the reveal the future is readable, and nothing new can be decided.
        self.assertEqual(len(replay.hidden()), 9)
        with self.assertRaises(MissionError):
            replay.decide("MSN-002", DecisionActor(SHIPPING_COMPANY))
        # And the learning pass sees the counterfactuals the reveal wrote.
        from src.portwatch_os.decision.learning import score_history

        report = score_history(replay.engine.ledger.decision_problems())
        self.assertEqual(report["resolved"], 1)
        self.assertIsNotNone(report["rankingAccuracy"])
        self.assertIsNotNone(report["meanRegret"])


# --------------------------------------------------------------------------
# the API
# --------------------------------------------------------------------------


class ApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        os.environ.setdefault("PORTWATCH_LICENCE_MODE", "DEMO")
        from fastapi.testclient import TestClient

        from backend.app.main import app
        from backend.app.routes.missions import reset_replays
        from src.portwatch_os.decision.engine import reset_engine

        reset_engine()
        reset_replays()
        cls.client = TestClient(app)
        cls.company = {"X-PortWatch-Role": "SHIPPING_COMPANY", "X-PortWatch-Actor": "ops.desk",
                       "X-PortWatch-Org": "PortWatch Demo Shipping"}
        cls.port = {"X-PortWatch-Role": "PORT_AUTHORITY", "X-PortWatch-Actor": "controller.n",
                    "X-PortWatch-Port": "INMAA"}

    def test_the_catalogue_and_critic_are_served(self):
        body = self.client.get("/api/decisions/actions").json()
        self.assertGreaterEqual(len(body["actions"]), 20)
        self.assertIn("ISSUE_ADVISORY", {a["kind"] for a in body["actions"]})
        self.assertEqual(body["workflow"]["COMPUTED"], ["REVIEWED"])
        self.assertIn("claim_horizon", body["critic"]["checks"])

    def test_a_port_option_is_handed_into_the_advisory_boundary(self):
        r = self.client.post("/api/decisions/problems",
                             json={"domain": "port", "portCode": "INMAA", "bunchArrivals": 3, "mode": "DEMO"},
                             headers=self.port)
        self.assertEqual(r.status_code, 200, r.text)
        problem = r.json()
        self.assertEqual(problem["domain"], "PORT_BERTHING")
        self.assertIn("assumedBunching", problem["evidence"])
        did = problem["decisionId"]
        stagger = next(o for o in problem["options"] if o["action"] == "SHIFT_ARRIVAL_SLOT")
        self.client.post(f"/api/decisions/problems/{did}/transition", json={"target": "REVIEWED"}, headers=self.port)
        r = self.client.post(f"/api/decisions/problems/{did}/transition",
                             json={"target": "APPROVED", "optionId": stagger["optionId"]}, headers=self.port)
        self.assertEqual(r.json()["workflow"], "APPROVED")
        r = self.client.post(f"/api/decisions/problems/{did}/handoff", json={}, headers=self.port)
        self.assertEqual(r.status_code, 200, r.text)
        body = r.json()
        self.assertEqual(body["decision"]["workflow"], "PROPOSED")
        self.assertTrue(body["advisories"])
        self.assertTrue(all(a["state"] == "draft" and a["kind"] == "arrival_window" for a in body["advisories"]))
        self.assertTrue(all(a["evidence"]["decisionId"] == did for a in body["advisories"]))
        # A draft is not visible to its recipient until a controller issues it.
        r = self.client.get("/api/advisories", headers=self.company)
        ids = {a["advisoryId"] for a in r.json().get("advisories", [])}
        self.assertFalse(ids & {a["advisoryId"] for a in body["advisories"]})

    def test_a_company_cannot_use_the_advisory_door(self):
        r = self.client.post("/api/decisions/problems",
                             json={"domain": "cargo", "portCode": "INNSA", "mode": "DEMO"}, headers=self.company)
        self.assertEqual(r.status_code, 200, r.text)
        problem = r.json()
        did = problem["decisionId"]
        chosen = problem["recommendation"]["optionId"]
        self.client.post(f"/api/decisions/problems/{did}/transition", json={"target": "REVIEWED"}, headers=self.company)
        self.client.post(f"/api/decisions/problems/{did}/transition",
                         json={"target": "APPROVED", "optionId": chosen}, headers=self.company)
        r = self.client.post(f"/api/decisions/problems/{did}/handoff", json={}, headers=self.company)
        self.assertEqual(r.status_code, 403)
        self.assertIn("record the outcome", r.json()["detail"])
        r = self.client.post(f"/api/decisions/problems/{did}/transition", json={"target": "APPROVED"},
                             headers={"X-PortWatch-Role": "SHIPPING_COMPANY"})
        self.assertEqual(r.status_code, 401)                                  # unnamed actor

    def test_a_port_authority_holds_a_cargo_decision_as_an_advisory_to_the_booking_party(self):
        """The port cannot move a consignment; it gets the shipping company's
        options, each marked as reaching the booking only through an advisory."""
        r = self.client.post("/api/decisions/problems",
                             json={"domain": "cargo", "portCode": "INNSA", "mode": "DEMO"}, headers=self.port)
        self.assertEqual(r.status_code, 200, r.text)
        problem = r.json()
        self.assertEqual(problem["actor"]["role"], "PORT_AUTHORITY")
        self.assertEqual(problem["evidence"]["execution"],
                         {"by": "SHIPPING_COMPANY", "requestedBy": "PORT_AUTHORITY", "mechanism": "ISSUE_ADVISORY"})
        rows = {a["kind"]: a for a in problem["availableActions"]}
        self.assertTrue(rows["KEEP_CONNECTION"]["requiresAdvisory"])
        self.assertEqual(rows["TRANSFER_TO_VESSEL"]["evaluatedFor"], "SHIPPING_COMPANY")
        self.assertTrue(any("advisory" in n for n in problem["notes"]))
        self.assertGreaterEqual(len([o for o in problem["options"] if o["status"] == "FEASIBLE"]), 1)

    def test_a_vessel_decision_takes_scenario_rates_and_a_tonnage_and_labels_them(self):
        events = self.client.get("/api/global-eye/events").json()["events"]
        queue = self.client.get("/api/attention").json()["items"]
        item = next((i for i in queue if i["subjectType"] == "vessel" and i.get("actionable")), None)
        if item is None:
            self.skipTest("no actionable hull in the demo register at this instant")
        event_id = item["cascadeId"].split(":")[-1]
        self.assertTrue(any(e["eventId"] == event_id for e in events))
        body = {"domain": "vessel", "eventId": event_id, "vesselId": item["subjectId"], "mode": "DEMO",
                "assumptions": [{"primitive": "charter_day", "value": 28000, "currency": "USD"}],
                "vesselAssumptions": {"grt": 52000}}
        r = self.client.post("/api/decisions/problems", json=body, headers=self.company)
        self.assertEqual(r.status_code, 200, r.text)
        problem = r.json()
        self.assertEqual(problem["evidence"]["attributeAssumptions"]["grt"]["label"], "ASSUMPTION")
        baseline = next(o for o in problem["options"] if o["isBaseline"])
        components = {c["key"]: c for c in baseline["evaluation"]["financial"]["components"]}
        self.assertEqual(components["port"]["state"], "KNOWN")
        self.assertTrue(components["port"]["isAssumption"])
        self.assertLess(components["port"]["money"]["amount"], 100000)       # one call, not GT squared
        self.assertEqual(baseline["evaluation"]["financial"]["label"], "ASSUMPTION")
        r = self.client.post("/api/decisions/problems", json={**body, "vesselAssumptions": {"grt": -1}},
                             headers=self.company)
        self.assertEqual(r.status_code, 400)

    def test_finance_routes_label_assumptions_and_refuse_nothing_silently(self):
        r = self.client.get("/api/finance/basis?scope=INNSA")
        coverage = r.json()["coverage"]
        self.assertTrue(coverage["berth_hire_grt_hour"]["available"])
        self.assertFalse(coverage["charter_day"]["available"])
        self.assertIn("no vessel charter rate", coverage["charter_day"]["reason"])
        r = self.client.post("/api/finance/assumptions",
                             json={"primitive": "charter_day", "value": 41000, "currency": "USD"}, headers=self.company)
        self.assertEqual(r.json()["label"], "ASSUMPTION")
        r = self.client.post("/api/finance/assumptions", json={"primitive": "charter_day", "value": 1})
        self.assertEqual(r.status_code, 401)
        r = self.client.get("/api/finance/tariffs")
        self.assertEqual({s["scheduleId"] for s in r.json()["schedules"]},
                         {"jnpa-sor-2026-27", "chpa-indexed-sor-2025-26"})
        self.client.post("/api/finance/assumptions/clear", headers=self.company)

    def test_mission_routes_keep_the_future_hidden(self):
        r = self.client.post("/api/missions/suez-ever-given-2021/replay", json={})
        self.assertEqual(r.status_code, 200)
        self.assertIsNone(r.json()["outcome"])
        self.assertIsNone(r.json()["hidden"])
        self.assertEqual(r.json()["hiddenCount"], 9)
        self.assertEqual(self.client.get("/api/missions/suez-ever-given-2021/outcome").status_code, 403)
        r = self.client.post("/api/missions/suez-ever-given-2021/decide", json={"vesselId": "MSN-001"},
                             headers=self.company)
        self.assertEqual(r.status_code, 200, r.text)
        problem = r.json()
        self.assertTrue(problem["evidence"]["replay"]["hiddenObservations"] > 0)
        r = self.client.post("/api/missions/suez-ever-given-2021/choose",
                             json={"vesselId": "MSN-001", "optionId": "keep_plan"}, headers=self.company)
        self.assertEqual(r.status_code, 200, r.text)
        r = self.client.post("/api/missions/suez-ever-given-2021/reveal", headers=self.company)
        card = r.json()["scorecards"]["MSN-001"]
        self.assertEqual(card["selected"], "keep_plan")
        self.assertIsNotNone(card["happened"]["reopenedAt"])
        self.assertEqual(self.client.get("/api/missions/suez-ever-given-2021/outcome").status_code, 200)
        r = self.client.get("/api/decisions/learning")
        self.assertTrue(r.json()["available"])


if __name__ == "__main__":
    unittest.main()
