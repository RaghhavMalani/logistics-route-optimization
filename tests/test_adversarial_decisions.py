"""Attacks on the decision engine. Every one must degrade or refuse safely.

Safely means: no crash, no invented number, and a written reason where the
engine could not do what it was asked. A missing input becomes an unknown
measure, an unpriced component or a Critic warning; an impossible option is
REJECTED with the rule that rejected it; a world that moved on, a window
that closed or a subject whose identity is contested is refused or
qualified at the step where a person would otherwise have trusted it.

    no feasible route            a Hormuz-only lane with a Hormuz closure
    all berths occupied          every berth held past the horizon
    port closure                 a port that declares no berths
    weather data missing         no marine grid
    weather disagreement         a grid whose cells disagree on the route
    stale AIS                    an observed hull last seen hours ago
    conflicting vessel identity  a hull with recorded identity conflicts
    unknown cost components      an empty cost basis
    invalid tariff period        a tariff row whose validity has lapsed
    FX unavailable               rates in INR, evaluation in USD, no observation
    cargo capacity exhausted     no vessel with room for the consignment
    reefer exhausted             a reefer box and no plugs anywhere
    decision deadline passed     approval after the window closed
    event expires during decision  a claim that lapses before the hull arrives
    world revision moves         approval on a world that changed since computation
"""

from __future__ import annotations

import unittest
from datetime import datetime, timedelta, timezone

from src.portwatch_os.cargo.model import Shipment, StorageZone, VesselCapacity
from src.portwatch_os.decision import DecisionActor, DecisionEngine
from src.portwatch_os.decision.critic import DecisionCritic
from src.portwatch_os.decision.model import (
    APPROVED,
    DecisionError,
    PORT_AUTHORITY,
    REJECTED,
    REVIEWED,
    SHIPPING_COMPANY,
)
from src.portwatch_os.decision.vessel import VesselDecisionError
from src.portwatch_os.finance import CostBasis, FxTable
from src.portwatch_os.finance.basis import CostRate, PUBLIC_TARIFF
from src.portwatch_os.finance.money import DAY
from src.portwatch_os.global_eye.exposure import VesselVoyage
from src.portwatch_os.global_eye.model import GlobalEvent
from src.portwatch_os.twin.state import VesselCall, WAITING, schematic_layout
from src.portwatch_os.world.branch import ObservedWorldState
from src.portwatch_os.world.build import build_world, seed_for
from src.portwatch_os.world.graph import EVENT, key
from src.portwatch_os.world.live import Revision

NOW = datetime(2026, 9, 13, 12, 0, tzinfo=timezone.utc)


def event(chokepoint="BAB_EL_MANDEB", *, horizon=72.0, first_seen=NOW, severity=0.85, confidence=0.9):
    return GlobalEvent(
        event_id=f"EV-{chokepoint}", title="closure", category="chokepoint_disruption", region="test",
        lat=12.6, lon=43.3, geolocation_basis="chokepoint", first_seen=first_seen.isoformat(),
        last_seen=first_seen.isoformat(), source_count=3, confidence=confidence, severity=severity,
        horizon_hours=horizon, chokepoints=[chokepoint],
    )


def state_for(voyages, *events, at=NOW, mode="DEMO", generation=1):
    graph = build_world(events=list(events), voyages=voyages, now=at)
    return ObservedWorldState(state_id="obs-adv", revision=Revision(mode, None, "e", "f", generation), at=at,
                              graph=graph, traffic_mode="SIMULATED_TRAFFIC")


def solve(engine, state, ev, vessel_id, *, actor=SHIPPING_COMPANY, at=NOW, **kwargs):
    return engine.solve_vessel(state, event_key=key(EVENT, ev.event_id), seed=seed_for(ev), vessel_id=vessel_id,
                               actor=DecisionActor(actor), at=at, **kwargs)


class RoutingAttacks(unittest.TestCase):
    def test_no_feasible_route_is_stated_not_invented(self):
        """A Gulf hull facing Hormuz: the lane has no alternative routing."""
        hull = VesselVoyage("GULF-1", "MT Gulf", "GULF_IND", "INNSA", {"HORMUZ": 12.0}, service_speed_kn=14.0)
        closure = event("HORMUZ")
        problem = solve(DecisionEngine(), state_for([hull], closure), closure, "GULF-1")
        reroute = problem.option("reroute")
        rows = {r["kind"]: r for r in problem.available_actions}
        # Either the action was never offered, with the reason, or it was rejected by a named constraint.
        if reroute is None:
            self.assertNotEqual(rows["REROUTE"]["availability"]["status"], "AVAILABLE")
            self.assertTrue(rows["REROUTE"]["availability"]["reason"])
        else:
            self.assertEqual(reroute.status, REJECTED)
            self.assertTrue(reroute.rejected_by)
        self.assertIsNotNone(problem.baseline, "doing nothing is still computed")
        for option in problem.options:
            if option.feasible:
                for measure in option.evaluation.objectives.values():
                    self.assertTrue(measure.available or measure.unknown_because)

    def test_an_event_that_expires_before_arrival_is_said_to_lapse_not_modelled_past_its_claim(self):
        hull = VesselVoyage("FAR-1", "MV Far", "EUR_IND", "INNSA", {"SUEZ": 200.0, "BAB_EL_MANDEB": 230.0})
        closure = event("BAB_EL_MANDEB", horizon=48.0)
        problem = solve(DecisionEngine(), state_for([hull], closure), closure, "FAR-1")
        risk = problem.baseline.measure("risk")
        self.assertEqual(risk.value, 0.0)
        self.assertTrue(risk.attrs.get("arrivalAfterClaimHorizon"))
        self.assertIn("persistence beyond the claim horizon is not modelled", risk.attrs.get("note", ""))
        self.assertEqual(problem.recommendation.option_id, "keep_plan")
        # And a hull that is not on the event's lane at all is refused outright.
        elsewhere = VesselVoyage("ELSE-1", "MV Elsewhere", "SEA_IND", "INMAA", {"MALACCA": 20.0})
        with self.assertRaises(VesselDecisionError) as caught:
            solve(DecisionEngine(), state_for([elsewhere], closure), closure, "ELSE-1")
        self.assertIn("not reached", str(caught.exception))

    def test_an_event_that_expires_during_the_decision_is_refused_at_approval(self):
        """Computed while the claim was live; approved after the option closed."""
        hull = VesselVoyage("NEAR-1", "MV Near", "EUR_IND", "INNSA", {"SUEZ": 6.0, "BAB_EL_MANDEB": 36.0},
                            service_speed_kn=18.0)
        closure = event("BAB_EL_MANDEB", horizon=72.0)
        engine = DecisionEngine()
        problem = solve(engine, state_for([hull], closure), closure, "NEAR-1")
        self.assertIsNotNone(problem.decision_deadline, "a hull six hours from the branch has a deadline")
        deadline = datetime.fromisoformat(problem.decision_deadline)
        engine.transition(problem.decision_id, REVIEWED, actor="ops", now=NOW)
        late = deadline + timedelta(hours=3)
        with self.assertRaises(DecisionError) as caught:
            engine.transition(problem.decision_id, APPROVED, actor="ops",
                              option_id=problem.recommendation.option_id, now=late)
        self.assertIn("closed", str(caught.exception))
        # An explicit acknowledgement is recorded, never assumed.
        engine.transition(problem.decision_id, APPROVED, actor="ops", option_id=problem.recommendation.option_id,
                          now=late, acknowledge_moved_world=True)
        self.assertEqual(engine.get(problem.decision_id).workflow, APPROVED)

    def test_a_deadline_already_passed_blocks_the_option_in_the_critic(self):
        hull = VesselVoyage("PAST-1", "MV Past", "EUR_IND", "INNSA", {"SUEZ": 6.0, "BAB_EL_MANDEB": 36.0})
        closure = event("BAB_EL_MANDEB")
        problem = solve(DecisionEngine(), state_for([hull], closure), closure, "PAST-1")
        option = next(o for o in problem.options if o.feasible and not o.is_baseline)
        option.provenance["closesInHours"] = -1.5
        verdict = DecisionCritic().review_option(option, problem, now=NOW)
        window = next(c for c in verdict.checks if c.name == "decision_window")
        self.assertFalse(window.passed)
        self.assertEqual(window.severity, "blocking")
        self.assertIn("closed", window.detail)


class WorldAttacks(unittest.TestCase):
    def test_a_moved_world_refuses_approval_until_acknowledged(self):
        hull = VesselVoyage("MV-1", "MV One", "EUR_IND", "INNSA", {"SUEZ": 20.0, "BAB_EL_MANDEB": 46.0})
        closure = event("BAB_EL_MANDEB")
        engine = DecisionEngine()
        before = state_for([hull], closure, generation=1)
        problem = solve(engine, before, closure, "MV-1")
        engine.transition(problem.decision_id, REVIEWED, actor="ops", now=NOW)
        moved = state_for([hull], closure, generation=2).summary()["revision"]
        with self.assertRaises(DecisionError) as caught:
            engine.transition(problem.decision_id, APPROVED, actor="ops", option_id=problem.recommendation.option_id,
                              now=NOW, current_revision=moved)
        self.assertIn("moved on", str(caught.exception))
        self.assertIn("observed hulls moved", str(caught.exception))
        # Same revision: no complaint.
        same = before.summary()["revision"]
        engine.transition(problem.decision_id, APPROVED, actor="ops", option_id=problem.recommendation.option_id,
                          now=NOW, current_revision=same)
        history = engine.get(problem.decision_id).workflow_history[-1]
        self.assertNotIn("movedWorldAcknowledged", history)

    def test_an_acknowledged_moved_world_is_written_into_the_history(self):
        hull = VesselVoyage("MV-2", "MV Two", "EUR_IND", "INNSA", {"SUEZ": 20.0, "BAB_EL_MANDEB": 46.0})
        closure = event("BAB_EL_MANDEB")
        engine = DecisionEngine()
        problem = solve(engine, state_for([hull], closure, generation=1), closure, "MV-2")
        engine.transition(problem.decision_id, REVIEWED, actor="ops", now=NOW)
        moved = state_for([hull], closure, generation=7).summary()["revision"]
        engine.transition(problem.decision_id, APPROVED, actor="ops", option_id=problem.recommendation.option_id,
                          now=NOW, current_revision=moved, acknowledge_moved_world=True)
        history = engine.get(problem.decision_id).workflow_history[-1]
        self.assertTrue(history["movedWorldAcknowledged"])
        self.assertEqual(history["computedOn"]["observedGeneration"], 1)
        self.assertEqual(history["approvedOn"]["observedGeneration"], 7)

    def test_a_replayed_world_never_counts_as_moved(self):
        from src.portwatch_os.decision.engine import revision_moved

        self.assertIsNone(revision_moved({"mode": "REPLAY", "fingerprint": "a"}, {"mode": "DEMO", "fingerprint": "b"}))
        self.assertIsNone(revision_moved({"mode": "DEMO", "fingerprint": "a"}, None))


class DataAttacks(unittest.TestCase):
    def test_weather_missing_is_an_unknown_measure_and_a_critic_warning(self):
        hull = VesselVoyage("WX-1", "MV Weather", "EUR_IND", "INNSA", {"SUEZ": 20.0, "BAB_EL_MANDEB": 46.0})
        closure = event("BAB_EL_MANDEB")
        problem = solve(DecisionEngine(), state_for([hull], closure), closure, "WX-1", grid=None)
        option = problem.recommendation and problem.option(problem.recommendation.option_id)
        self.assertIsNotNone(option)
        weather = option.measure("weather")
        self.assertIsNotNone(weather)
        self.assertFalse(weather.available)
        self.assertTrue(weather.unknown_because)
        verdict = DecisionCritic().review_option(option, problem, now=NOW)
        check = next(c for c in verdict.checks if c.name == "weather_confidence")
        self.assertFalse(check.passed)
        self.assertIn("weather", check.remedy or check.detail)

    def test_weather_disagreement_lowers_confidence_rather_than_averaging_it_away(self):
        """A grid whose cells disagree wildly along the route must not produce a
        confident single wave figure."""
        from src.portwatch_os.fabric.marine import MarineForecastCell, MarineGrid
        from src.portwatch_os.world.route_exposure import sample_route

        fetched = NOW - timedelta(minutes=10)
        cells = []
        # Two neighbouring points, one benign and one violent, at every hour of the run.
        for hour in range(0, 48):
            valid = NOW + timedelta(hours=hour)
            cells.append(MarineForecastCell(lat=12.0, lon=44.0, valid_at=valid, fetched_at=fetched, wave_height_m=0.4,
                                            requested=(12.0, 44.0), label="calm"))
            cells.append(MarineForecastCell(lat=13.0, lon=45.0, valid_at=valid, fetched_at=fetched, wave_height_m=9.0,
                                            requested=(13.0, 45.0), label="violent"))
        grid = MarineGrid(cells)
        profile = sample_route([(12.0, 44.0), (12.5, 44.5), (13.0, 45.0)], grid=grid, departs_at=NOW, speed_kn=16.0)
        payload = profile.to_dict()
        # The worst cell is reported as the worst, not averaged with the calm one,
        # and the profile carries the confidence the disagreement leaves it with.
        self.assertGreaterEqual(float(payload["maxWaveM"] or 0.0), 9.0)
        self.assertLess(float(payload["meanWaveM"]), 9.0, "the mean is not the worst; both are reported")
        self.assertLessEqual(float(payload["confidence"]), 0.5, "a sampled heuristic never claims more than 0.5")
        self.assertIn("HEAVY", " ".join(payload["flags"]).upper())

    def test_stale_ais_qualifies_the_subject_in_the_critic(self):
        hull = VesselVoyage("OBS-1", "MMSI 419000001", "EUR_IND", "INNSA", {"SUEZ": 20.0, "BAB_EL_MANDEB": 46.0},
                            source="OBSERVED_AIS", destination_confidence=0.6, lane_confidence=0.7,
                            timing_confidence=0.6, lat=30.1, lon=32.5,
                            observed_at=(NOW - timedelta(hours=5)).isoformat(), mmsi="419000001")
        closure = event("BAB_EL_MANDEB")
        problem = solve(DecisionEngine(), state_for([hull], closure), closure, "OBS-1")
        self.assertEqual(problem.evidence["subject"]["source"], "OBSERVED_AIS")
        option = problem.option(problem.recommendation.option_id)
        verdict = DecisionCritic().review_option(option, problem, now=NOW)
        check = next(c for c in verdict.checks if c.name == "subject_provenance")
        self.assertFalse(check.passed)
        self.assertIn("5.0 h old", check.detail)

    def test_conflicting_identity_qualifies_every_option(self):
        hull = VesselVoyage("OBS-2", "MMSI 419000002", "EUR_IND", "INNSA", {"SUEZ": 20.0, "BAB_EL_MANDEB": 46.0},
                            source="OBSERVED_AIS", destination_confidence=0.6, lane_confidence=0.7,
                            timing_confidence=0.6, lat=30.1, lon=32.5, observed_at=NOW.isoformat(),
                            mmsi="419000002", identity_conflicts=2)
        closure = event("BAB_EL_MANDEB")
        state = state_for([hull], closure)
        self.assertEqual(state.graph.node(key("vessel", "OBS-2")).attrs["identity_conflicts"], 2)
        problem = solve(DecisionEngine(), state, closure, "OBS-2")
        self.assertEqual(problem.evidence["subject"]["identityConflicts"], 2)
        for option in problem.options:
            if not option.feasible:
                continue
            verdict = DecisionCritic().review_option(option, problem, now=NOW)
            check = next(c for c in verdict.checks if c.name == "subject_provenance")
            self.assertFalse(check.passed, option.option_id)
            self.assertIn("contested", check.detail)

    def test_the_fusion_engine_records_an_identity_conflict_rather_than_resolving_it(self):
        from src.portwatch_os.fabric.ais.messages import AisObservation
        from src.portwatch_os.fusion.engine import FusionEngine
        from src.portwatch_os.world.observed import observed_voyages

        engine = FusionEngine()
        engine.register_fleet_vessel(vessel_id="F-1", name="MV Konkan", imo="9876543")
        static = AisObservation(provider_id="aisstream", message_type="ShipStaticData", mmsi="419001234",
                                lat=12.6, lon=43.3, source_timestamp=NOW, ingested_at=NOW, imo="9876543",
                                name="MV KONKAN", callsign="VTKK")
        engine.ingest_ais(static, now=NOW)
        rival = AisObservation(provider_id="aisstream", message_type="ShipStaticData", mmsi="419001234",
                               lat=12.6, lon=43.3, source_timestamp=NOW + timedelta(minutes=1),
                               ingested_at=NOW + timedelta(minutes=1), imo="1111111", name="MV KONKAN")
        outcome = engine.ingest_ais(rival, now=NOW + timedelta(minutes=1))
        self.assertTrue(outcome.conflicts, "a differing IMO claim is a recorded conflict")
        hulls = [v for v in engine.vessels() if "419001234" in (v.mmsis or [])]
        self.assertTrue(hulls)
        self.assertEqual(hulls[0].imo, "9876543", "the held identity was not overwritten by the claim")


class MoneyAttacks(unittest.TestCase):
    def _problem(self, basis=None, fx=None, currency="USD"):
        hull = VesselVoyage("MONEY-1", "MV Money", "EUR_IND", "INNSA", {"SUEZ": 20.0, "BAB_EL_MANDEB": 46.0},
                            service_speed_kn=18.0)
        closure = event("BAB_EL_MANDEB")
        engine = DecisionEngine(basis=basis or CostBasis(), fx=fx or FxTable(), currency=currency)
        return solve(engine, state_for([hull], closure), closure, "MONEY-1")

    def test_unknown_cost_components_keep_the_total_unknown_never_zero(self):
        problem = self._problem()
        for option in problem.options:
            if not option.feasible:
                continue
            financial = option.evaluation.financial
            self.assertTrue(financial["unknown"], option.option_id)
            self.assertIsNone(financial.get("total"), option.option_id)
            for component in financial["components"]:
                if component["state"] == "UNKNOWN":
                    self.assertTrue(component["reason"])
                    self.assertIsNone(component.get("money"))
            cost = option.measure("cost")
            self.assertFalse(cost.available)

    def test_a_lapsed_tariff_period_is_reported_as_lapsed_and_not_used(self):
        lapsed = CostRate(primitive="charter_day", value=30000.0, currency="USD", unit=DAY, scope="*",
                          valid_from="2024-01-01T00:00:00+00:00", valid_to="2024-12-31T23:59:59+00:00",
                          source="old charter schedule", source_type=PUBLIC_TARIFF, confidence=0.9)
        basis = CostBasis([lapsed])
        found = basis.lookup("charter_day", at=NOW)
        self.assertIsNone(found.rate)
        self.assertIn("outside its validity", found.reason)
        problem = self._problem(basis=basis)
        option = problem.option(problem.recommendation.option_id)
        delay = next(c for c in option.evaluation.financial["components"] if c["key"] == "delay")
        self.assertEqual(delay["state"], "UNKNOWN")
        self.assertIn("validity", delay["reason"])

    def test_fx_unavailable_leaves_the_figure_in_its_own_currency_or_unknown(self):
        inr = CostRate(primitive="charter_day", value=2_400_000.0, currency="INR", unit=DAY, scope="*",
                       valid_from=None, valid_to=None, source="INR charter basis", source_type=PUBLIC_TARIFF,
                       confidence=0.9)
        problem = self._problem(basis=CostBasis([inr]), fx=FxTable(), currency="USD")
        option = problem.option(problem.recommendation.option_id)
        financial = option.evaluation.financial
        delay = next(c for c in financial["components"] if c["key"] == "delay")
        # Either the component stayed unknown because no FX observation exists,
        # or it is priced in INR and the USD total is unknown. Never a silent conversion.
        if delay["state"] == "UNKNOWN":
            self.assertRegex(delay["reason"].lower(), "fx|exchange|inr")
        else:
            self.assertEqual(delay["money"]["currency"], "INR")
            self.assertIsNone(financial.get("total"))
        text = str(financial)
        self.assertNotIn("83.", text, "no invented INR/USD rate anywhere in the evaluation")


class PortAttacks(unittest.TestCase):
    def test_all_berths_occupied_leaves_every_wait_unknown_and_says_so(self):
        state = schematic_layout("INMAA", berth_count=2, capacity_index=0.7)
        for berth in state.berths:
            berth.occupied_by = f"seed-{berth.berth_id}"
            berth.free_at_hour = 500.0
        state.calls = [
            VesselCall("C-1", "V-1", "Waiting one", "panamax", 250.0, 12.0, -2.0, 400, state=WAITING, arrived_hour=-2.0),
            VesselCall("C-2", "V-2", "Waiting two", "panamax", 250.0, 12.0, -1.0, 400, state=WAITING, arrived_hour=-1.0),
        ]
        problem = DecisionEngine().solve_port(state, actor=DecisionActor(PORT_AUTHORITY, port_code="INMAA"), at=NOW,
                                              world_state_id="obs", world_revision={}, horizon_hours=24.0)
        baseline = problem.baseline
        wait = baseline.measure("port_wait")
        self.assertFalse(wait.available)
        self.assertIn("no call completed", wait.unknown_because)
        self.assertIn("no call completes", problem.do_nothing_statement)
        if problem.recommendation is not None:
            self.assertNotEqual(problem.recommendation.critic.get("verdict"), "PASS")

    def test_a_closed_port_is_refused_with_the_reason(self):
        from src.portwatch_os.decision.port import PortDecisionError

        state = schematic_layout("INMAA", berth_count=2, capacity_index=0.7)
        state.berths = []
        state.calls = [VesselCall("C-1", "V-1", "Arrival", "panamax", 250.0, 12.0, 2.0, 400)]
        with self.assertRaises(PortDecisionError) as caught:
            DecisionEngine().solve_port(state, actor=DecisionActor(PORT_AUTHORITY, port_code="INMAA"), at=NOW,
                                        world_state_id="obs", world_revision={})
        self.assertIn("no berths", str(caught.exception))


class CargoAttacks(unittest.TestCase):
    def _zones(self):
        return [StorageZone(zone_id="Z-1", name="Yard", free_teu=100.0, capacity_teu=200.0, reefer_plugs_free=0,
                            accepts_hazardous=True, accepts_oog=True)]

    def test_capacity_exhausted_rejects_every_vessel_option_with_the_rule(self):
        shipment = Shipment(shipment_id="S-1", teu=8.0, cargo_class="dry", destination_port="SGSIN",
                            inbound_vessel_id="IN-1", booked_vessel_id="OUT-1", available_hour=2.0, yard_block_id="Z-1")
        vessels = [
            VesselCapacity(vessel_id="OUT-1", name="Booked", available_teu=0.0, onward_ports=["SGSIN"], departure_hour=12.0),
            VesselCapacity(vessel_id="OUT-2", name="Alternative", available_teu=4.0, onward_ports=["SGSIN"], departure_hour=18.0),
        ]
        problem = DecisionEngine().solve_cargo(shipment, vessels, self._zones(), actor=DecisionActor(SHIPPING_COMPANY),
                                               at=NOW, port_code="INMAA", world_state_id="obs", world_revision={})
        vessel_options = [o for o in problem.options if o.params.get("vesselId")]
        self.assertTrue(vessel_options)
        for option in vessel_options:
            self.assertEqual(option.status, REJECTED, option.option_id)
            self.assertTrue(any("teu" in c.detail.lower() or "capacity" in c.detail.lower() for c in option.rejected_by),
                            [c.detail for c in option.rejected_by])
        self.assertIsNone(problem.recommendation)

    def test_reefer_exhausted_is_a_named_rejection_not_a_warm_box(self):
        shipment = Shipment(shipment_id="S-2", teu=2.0, cargo_class="reefer", destination_port="SGSIN",
                            inbound_vessel_id="IN-1", booked_vessel_id="OUT-1", available_hour=2.0, yard_block_id="Z-1")
        vessels = [
            VesselCapacity(vessel_id="OUT-1", name="Booked", available_teu=50.0, available_reefer_plugs=0,
                           onward_ports=["SGSIN"], departure_hour=12.0),
            VesselCapacity(vessel_id="OUT-2", name="Alternative", available_teu=50.0, available_reefer_plugs=0,
                           onward_ports=["SGSIN"], departure_hour=20.0),
        ]
        problem = DecisionEngine().solve_cargo(shipment, vessels, self._zones(), actor=DecisionActor(SHIPPING_COMPANY),
                                               at=NOW, port_code="INMAA", world_state_id="obs", world_revision={})
        for option in problem.options:
            self.assertEqual(option.status, REJECTED, option.option_id)
            self.assertTrue(any("reefer" in c.detail.lower() or "plug" in c.detail.lower() for c in option.rejected_by),
                            [c.detail for c in option.rejected_by])
        self.assertIsNone(problem.recommendation)


if __name__ == "__main__":
    unittest.main()
