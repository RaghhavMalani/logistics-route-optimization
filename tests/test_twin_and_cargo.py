"""The digital twin, its policies, and the cargo layer.

The simulator is the environment every policy claim in this repository is
measured in, so the tests it most needs are about determinism and about
constraints holding. A simulator that quietly relaxed a berth's draught would
make every benchmark number meaningless while looking fine.
"""

from __future__ import annotations

import unittest

from src.portwatch_os.cargo.model import (
    CARGO_DISCLAIMER,
    Shipment,
    StorageZone,
    VesselCapacity,
    check_compatibility,
    demo_manifest,
    evaluate_connection,
    total_handling_hours,
    zones_from_state,
)
from src.portwatch_os.cargo.optimizer import opportunities, optimise
from src.portwatch_os.twin.policies import (
    ContextualBanditPolicy,
    FirstComeFirstServed,
    GreedyPolicy,
    LookaheadPolicy,
    RandomPolicy,
    bandit_context,
    build_policy,
    gang_size,
)
from src.portwatch_os.twin.promotion import (
    MIN_EVALUATION_EPISODES,
    evaluate_promotion,
    promotion_pipeline,
)
from src.portwatch_os.twin.rl import (
    EVAL_SEED_BASE,
    TRAIN_SEED_BASE,
    PortEnvironment,
    ScenarioSpec,
    benchmark,
    default_policies,
    evaluate,
    train_bandit,
)
from src.portwatch_os.twin.simulation import (
    ASSIGN_BERTH,
    ASSIGN_CRANES,
    DELAY_ARRIVAL,
    NO_ACTION,
    Action,
    SimulationConfig,
    apply_action,
    reward,
    reward_breakdown,
    simulate,
    validate_action,
    weather_derate,
    yard_friction,
)
from src.portwatch_os.twin.state import (
    ALONGSIDE,
    APPROACHING,
    DEPARTED,
    GEOMETRY_SCHEMATIC,
    WAITING,
    PortState,
    VesselCall,
    schematic_layout,
    seed_calls,
    seed_yard,
    state_from_snapshot,
)
from src.portwatch_os.ledger.store import SqliteLedgerStore

SNAPSHOT = {
    "queuePressure": 0.55,
    "capacityPressure": 0.6,
    "weatherImpact": 0.08,
    "anchorageCount": 3.0,
    "berthCount": 8,
    "capacityIndex": 0.7,
    "observedAt": "2026-08-28T06:00:00+00:00",
}


def small_state(berths=6, calls=8):
    state = schematic_layout("INMAA", berth_count=berths, capacity_index=0.7)
    seed_yard(state, 0.7)
    for index in range(calls):
        state.calls.append(
            VesselCall(
                call_id=f"C{index}", vessel_id=f"V{index}", name=f"Sim {index}",
                vessel_class="panamax", loa_m=240.0, draught_m=11.5,
                eta_hour=index * 2.0, moves=900, state=APPROACHING,
            )
        )
    return state


class StateTests(unittest.TestCase):
    def test_the_geometry_declares_itself_schematic(self):
        state = schematic_layout("INMAA", berth_count=8)
        self.assertEqual(state.geometry_basis, GEOMETRY_SCHEMATIC)
        self.assertTrue(any("Schematic" in note for note in state.notes))
        self.assertIn("not", state.to_dict()["geometryDisclaimer"].lower())

    def test_the_layout_scales_with_the_registry_not_a_constant(self):
        small = schematic_layout("INMAA", berth_count=4, capacity_index=0.4)
        large = schematic_layout("INNSA", berth_count=20, capacity_index=0.9)
        self.assertLess(len(small.berths), len(large.berths))
        self.assertLess(len(small.cranes), len(large.cranes))
        self.assertLess(len(small.yard_blocks), len(large.yard_blocks))

    def test_berths_carry_a_mix_of_sizes(self):
        """Assuming every berth takes a 400 m hull would let the optimiser lie."""
        lengths = {b.length_m for b in schematic_layout("INNSA", berth_count=12).berths}
        self.assertGreater(len(lengths), 1)

    def test_a_crane_reaches_its_neighbours_so_allocation_is_a_decision(self):
        state = schematic_layout("INMAA", berth_count=8)
        self.assertTrue(any(len(c.serves) > 1 for c in state.cranes))

    def test_seeding_from_a_snapshot_is_deterministic(self):
        first = state_from_snapshot("INMAA", SNAPSHOT)
        second = state_from_snapshot("INMAA", SNAPSHOT)
        self.assertEqual(
            [(b.berth_id, b.free_at_hour) for b in first.berths],
            [(b.berth_id, b.free_at_hour) for b in second.berths],
        )
        self.assertEqual(
            [c.call_id for c in first.calls], [c.call_id for c in second.calls]
        )

    def test_a_seeded_state_has_something_to_schedule(self):
        state = state_from_snapshot("INMAA", SNAPSHOT)
        self.assertTrue(state.calls)
        self.assertTrue(any(c.state == WAITING for c in state.calls))

    def test_the_arrival_queue_is_seeded_from_the_observed_anchorage(self):
        light = state_from_snapshot("INMAA", {**SNAPSHOT, "anchorageCount": 0.0})
        heavy = state_from_snapshot("INMAA", {**SNAPSHOT, "anchorageCount": 9.0})
        self.assertLess(
            sum(1 for c in light.calls if c.state == WAITING),
            sum(1 for c in heavy.calls if c.state == WAITING),
        )

    def test_yard_fill_is_weighted_toward_the_quay(self):
        state = schematic_layout("INMAA", berth_count=8)
        seed_yard(state, 0.6)
        blocks = sorted(state.yard_blocks, key=lambda b: b.y)
        self.assertGreater(blocks[0].utilisation, blocks[-1].utilisation)

    def test_a_clone_cannot_contaminate_the_original(self):
        state = small_state()
        clone = state.clone()
        clone.berths[0].occupied_by = "someone"
        self.assertIsNone(state.berths[0].occupied_by)

    def test_a_berth_refuses_a_hull_it_cannot_take(self):
        berth = schematic_layout("INMAA", berth_count=8).berths[0]
        self.assertFalse(berth.can_accept(400.0, 9.0))
        self.assertFalse(berth.can_accept(150.0, 20.0))


class SimulationTests(unittest.TestCase):
    def test_the_same_inputs_give_byte_identical_metrics(self):
        """Two policies can only be compared if the world is identical."""
        config = SimulationConfig(horizon_hours=24.0, seed=7, record_trace=False)
        first = simulate(small_state(), GreedyPolicy(), config, snapshot_hours=())
        second = simulate(small_state(), GreedyPolicy(), config, snapshot_hours=())
        self.assertEqual(first.metrics, second.metrics)

    def test_the_state_passed_in_is_never_mutated(self):
        state = small_state()
        before = [c.state for c in state.calls]
        simulate(state, GreedyPolicy(), SimulationConfig(horizon_hours=24.0))
        self.assertEqual([c.state for c in state.calls], before)

    def test_an_infeasible_berthing_is_refused_and_recorded(self):
        state = small_state()
        state.calls[0].loa_m = 900.0

        def greedy_but_wrong(current: PortState):
            return [
                Action(kind=ASSIGN_BERTH, call_id="C0", berth_id=current.berths[0].berth_id)
            ]

        result = simulate(
            state, greedy_but_wrong, SimulationConfig(horizon_hours=6.0)
        )
        self.assertTrue(result.rejected_actions)
        self.assertIn("cannot accept", result.rejected_actions[0]["rejectedBecause"])

    def test_a_run_ends_with_no_hard_constraint_violation(self):
        result = simulate(
            small_state(), GreedyPolicy(), SimulationConfig(horizon_hours=48.0)
        )
        self.assertEqual(result.violations, [])

    def test_a_berth_cannot_take_two_vessels(self):
        state = small_state()
        # A berth the hull actually fits. B1 is the smallest on the quay, so
        # assigning a 240 m panamax there is refused on compatibility long
        # before occupancy is ever reached -- which would test the wrong rule.
        call = state.calls[0]
        berth = next(
            b.berth_id for b in state.berths
            if b.can_accept(call.loa_m, call.draught_m, call.cargo_type)
        )

        def double_book(current: PortState):
            return [
                Action(kind=ASSIGN_BERTH, call_id="C0", berth_id=berth),
                Action(kind=ASSIGN_BERTH, call_id="C1", berth_id=berth),
            ]

        result = simulate(state, double_book, SimulationConfig(horizon_hours=12.0))
        self.assertEqual(result.violations, [])
        self.assertTrue(
            any("occupied" in r["rejectedBecause"] for r in result.rejected_actions)
        )

    def test_an_arrival_cannot_be_restaggered_after_it_has_arrived(self):
        state = small_state()
        state.calls[0].state = WAITING
        problem = validate_action(
            state, Action(kind=DELAY_ARRIVAL, call_id="C0", hours=4.0)
        )
        self.assertIsNotNone(problem)
        self.assertIn("before the vessel arrives", problem)

    def test_an_arrival_shift_beyond_the_envelope_is_refused(self):
        state = small_state()
        problem = validate_action(
            state, Action(kind=DELAY_ARRIVAL, call_id="C0", hours=96.0)
        )
        self.assertIn("48", problem)

    def test_cranes_stop_rather_than_slow_in_severe_weather(self):
        self.assertEqual(weather_derate(0.9), 0.0)
        self.assertGreater(weather_derate(0.1), 0.7)

    def test_a_congested_yard_slows_the_quay(self):
        self.assertEqual(yard_friction(0.5), 1.0)
        self.assertLess(yard_friction(0.99), 0.6)

    def test_snapshots_are_taken_at_the_requested_horizons(self):
        result = simulate(
            small_state(), GreedyPolicy(),
            SimulationConfig(horizon_hours=24.0), snapshot_hours=(2, 6, 12, 24),
        )
        self.assertEqual(sorted(result.snapshots), [2, 6, 12, 24])

    def test_the_reward_breakdown_sums_to_the_reward(self):
        result = simulate(
            small_state(), GreedyPolicy(), SimulationConfig(horizon_hours=36.0)
        )
        breakdown = reward_breakdown(result)
        self.assertAlmostEqual(breakdown["total"], round(reward(result), 3), places=2)

    def test_waiting_costs_and_completing_pays(self):
        idle = simulate(
            small_state(calls=8), lambda _: [Action(kind=NO_ACTION)],
            SimulationConfig(horizon_hours=48.0),
        )
        working = simulate(
            small_state(calls=8), GreedyPolicy(), SimulationConfig(horizon_hours=48.0)
        )
        self.assertGreater(reward(working), reward(idle))


class PolicyTests(unittest.TestCase):
    def setUp(self):
        self.environment = PortEnvironment(
            ScenarioSpec(arrivals=16, berth_count=6, horizon_hours=48.0)
        )

    def test_the_gang_scales_with_the_hull(self):
        feeder = VesselCall("c", "v", "n", "feeder", 170.0, 9.0, 0.0, 400)
        neo = VesselCall("c", "v", "n", "neo_panamax", 366.0, 15.0, 0.0, 3000)
        self.assertLess(gang_size(feeder), gang_size(neo))

    def test_every_registered_policy_builds_and_names_itself(self):
        for policy_id in ("fcfs", "random", "greedy", "lookahead", "bandit"):
            policy = build_policy(policy_id)
            self.assertEqual(policy.policy_id, policy_id)
            self.assertTrue(policy.description)

    def test_an_unknown_policy_names_the_known_ones(self):
        with self.assertRaises(KeyError) as caught:
            build_policy("magic")
        self.assertIn("greedy", str(caught.exception))

    def test_an_optimiser_beats_the_incumbent_rule(self):
        """The measured claim the product makes about port optimisation."""
        result = benchmark(
            self.environment, [FirstComeFirstServed(), GreedyPolicy()], episodes=12
        )
        improvement = result.improvement("greedy")
        self.assertIsNotNone(improvement)
        self.assertGreater(improvement, 0.0)

    def test_the_incumbent_rule_beats_random(self):
        result = benchmark(
            self.environment, [FirstComeFirstServed(), RandomPolicy()], episodes=12
        )
        self.assertLess(result.improvement("random"), 0.0)

    def test_no_policy_produces_a_violation_or_an_infeasible_action(self):
        for policy in default_policies():
            scored = evaluate(self.environment, policy, episodes=6)
            self.assertEqual(scored.violations, 0, policy.name)
            self.assertEqual(scored.rejected_actions, 0, policy.name)

    def test_the_bandit_context_is_discrete_and_bounded(self):
        state = small_state()
        context = bandit_context(state)
        self.assertEqual(len(context), 3)
        for value in context:
            self.assertIn(value, (0, 1, 2))

    def test_a_frozen_bandit_stops_exploring(self):
        learner, _ = train_bandit(self.environment, episodes=12)
        frozen = learner.freeze()
        self.assertFalse(frozen.explore)
        self.assertEqual(len(frozen.table), len(learner.table))

    def test_a_bandit_table_round_trips(self):
        learner, _ = train_bandit(self.environment, episodes=12)
        restored = ContextualBanditPolicy()
        restored.load_table(learner.to_dict()["table"])
        self.assertEqual(set(restored.table), set(learner.table))


class PromotionTests(unittest.TestCase):
    def setUp(self):
        self.environment = PortEnvironment(
            ScenarioSpec(arrivals=16, berth_count=6, horizon_hours=48.0)
        )
        self.store = SqliteLedgerStore(":memory:")

    def test_training_and_evaluation_seeds_never_overlap(self):
        """A policy evaluated on its training scenarios measures memorisation."""
        learner, training = train_bandit(self.environment, episodes=20)
        scored = evaluate(self.environment, learner.freeze(), episodes=8)
        self.assertFalse(set(training.seeds) & set(scored.seeds))
        self.assertGreater(EVAL_SEED_BASE - TRAIN_SEED_BASE, 100_000)

    def test_a_policy_that_only_beats_the_baseline_is_not_promoted(self):
        """The check that matters: beating FCFS is not enough to ship."""
        result = benchmark(self.environment, default_policies(), episodes=32)
        decision = evaluate_promotion(
            result, "random", training_seeds=[TRAIN_SEED_BASE]
        )
        self.assertFalse(decision.passed)

    def test_promotion_needs_enough_held_out_episodes(self):
        result = benchmark(self.environment, default_policies(), episodes=8)
        decision = evaluate_promotion(
            result, "greedy", training_seeds=[TRAIN_SEED_BASE]
        )
        self.assertIn("sufficient_episodes", decision.failed_checks)
        self.assertIn(str(MIN_EVALUATION_EPISODES), decision.reasons["sufficient_episodes"])

    def test_an_unproven_seed_range_fails_the_leakage_check(self):
        result = benchmark(self.environment, default_policies(), episodes=32)
        decision = evaluate_promotion(result, "greedy", training_seeds=None)
        self.assertIn("held_out_seeds", decision.failed_checks)

    def test_the_pipeline_records_a_rejection_with_its_reasons(self):
        learner, training = train_bandit(self.environment, episodes=40)
        result = benchmark(
            self.environment, default_policies(learner.freeze()), episodes=32
        )
        record, decision = promotion_pipeline(
            self.store, result, candidate_policy_id="bandit", name="Bandit",
            version="0.1.0", environment="test", training=training.to_dict(),
            training_seeds=training.seeds,
        )
        self.assertIn(record.state, ("rejected", "evaluating"))
        self.assertTrue(record.evaluation)
        if record.state == "rejected":
            self.assertTrue(record.rejection_reason)

    def test_an_automated_pipeline_cannot_approve_on_its_own_behalf(self):
        learner, training = train_bandit(self.environment, episodes=20)
        result = benchmark(
            self.environment, default_policies(learner.freeze()), episodes=32
        )
        record, _ = promotion_pipeline(
            self.store, result, candidate_policy_id="bandit", name="Bandit",
            version="0.1.0", environment="test", training=training.to_dict(),
            training_seeds=training.seeds,
        )
        self.assertNotEqual(record.state, "approved")


class CargoTests(unittest.TestCase):
    def setUp(self):
        self.zone = StorageZone(
            zone_id="Y1", name="Yard A1", free_teu=500, capacity_teu=800,
            reefer_plugs_free=200, accepts_hazardous=True,
        )
        self.vessel = VesselCapacity(
            vessel_id="V1", name="MV Onward", available_teu=400,
            available_reefer_plugs=100, accepts_hazardous=False,
            onward_ports=["SGSIN", "MYPKG"], departure_hour=40.0,
            load_cutoff_hour=36.0,
        )

    def _shipment(self, **kwargs):
        base = dict(
            shipment_id="S1", teu=80.0, cargo_class="dry",
            destination_port="SGSIN", available_hour=4.0,
        )
        base.update(kwargs)
        return Shipment(**base)

    def test_a_feasible_transfer_is_accepted(self):
        connection = evaluate_connection(self._shipment(), self.vessel, zone=self.zone)
        self.assertTrue(connection.feasible, connection.reasons)
        self.assertGreater(connection.window.slack_hours, 0)

    def test_a_destination_the_vessel_does_not_call_at_is_refused(self):
        connection = evaluate_connection(
            self._shipment(destination_port="NLRTM"), self.vessel, zone=self.zone
        )
        self.assertFalse(connection.feasible)
        self.assertTrue(any("does not call at" in r for r in connection.reasons))

    def test_capacity_is_a_hard_limit(self):
        connection = evaluate_connection(
            self._shipment(teu=900.0), self.vessel, zone=self.zone
        )
        self.assertFalse(connection.feasible)
        self.assertTrue(any("TEU free" in r for r in connection.reasons))

    def test_a_reefer_needs_a_plug_on_both_the_ship_and_the_yard(self):
        connection = evaluate_connection(
            self._shipment(teu=150.0, cargo_class="reefer"), self.vessel, zone=self.zone
        )
        self.assertFalse(connection.feasible)
        self.assertTrue(any("reefer plugs" in r for r in connection.reasons))

    def test_hazardous_cargo_needs_a_certified_vessel(self):
        connection = evaluate_connection(
            self._shipment(cargo_class="hazardous"), self.vessel, zone=self.zone
        )
        self.assertFalse(connection.feasible)
        self.assertTrue(any("IMDG" in r for r in connection.reasons))

    def test_missing_the_cut_off_is_refused_and_says_by_how_much(self):
        connection = evaluate_connection(
            self._shipment(available_hour=60.0), self.vessel, zone=self.zone
        )
        self.assertFalse(connection.feasible)
        self.assertTrue(any("short by" in r for r in connection.reasons))

    def test_every_reason_is_collected_not_just_the_first(self):
        """A planner asking "why not" needs all of them at once."""
        connection = evaluate_connection(
            self._shipment(teu=900.0, cargo_class="hazardous", destination_port="NLRTM"),
            self.vessel, zone=self.zone,
        )
        self.assertGreaterEqual(len(connection.reasons), 3)

    def test_a_direct_transfer_skips_the_yard_moves(self):
        shipment = self._shipment(inbound_vessel_id="INB-1")
        self.vessel.berth_id = "B1"
        with_yard = total_handling_hours(shipment, self.zone)
        direct = total_handling_hours(shipment, None)
        self.assertLess(direct, with_yard)

    def test_a_vessel_with_no_sailing_time_cannot_be_checked(self):
        vessel = VesselCapacity(
            vessel_id="V2", name="MV Unknown", available_teu=400,
            onward_ports=["SGSIN"],
        )
        connection = evaluate_connection(self._shipment(), vessel, zone=self.zone)
        self.assertFalse(connection.feasible)
        self.assertTrue(any("no sailing time" in r for r in connection.reasons))

    def test_the_demo_manifest_is_deterministic_and_declares_itself(self):
        first = demo_manifest("INMAA", shipments=20)
        second = demo_manifest("INMAA", shipments=20)
        self.assertEqual(
            [s.shipment_id for s in first], [s.shipment_id for s in second]
        )
        self.assertIn("No commercial manifest feed", CARGO_DISCLAIMER)

    def test_the_plan_never_commits_more_than_a_vessel_can_take(self):
        shipments = [
            self._shipment(shipment_id=f"S{i}", teu=150.0) for i in range(10)
        ]
        plan = optimise("INMAA", shipments, [self.vessel], [self.zone])
        placed = sum(a.teu for a in plan.assignments)
        self.assertLessEqual(placed, self.vessel.available_teu)

    def test_an_unplaced_shipment_carries_its_reason(self):
        shipments = [
            self._shipment(shipment_id=f"S{i}", teu=150.0) for i in range(10)
        ]
        plan = optimise("INMAA", shipments, [self.vessel], [self.zone])
        self.assertTrue(plan.unplaced)
        for row in plan.unplaced:
            self.assertTrue(row.reasons)

    def test_the_plan_reports_the_value_it_could_not_capture(self):
        shipments = [
            self._shipment(shipment_id=f"S{i}", teu=200.0) for i in range(8)
        ]
        plan = optimise("INMAA", shipments, [self.vessel], [self.zone])
        self.assertGreater(plan.foregone_value, 0)
        self.assertTrue(any("greedy" in n for n in plan.notes))

    def test_the_plan_never_claims_to_be_optimal(self):
        plan = optimise("INMAA", [self._shipment()], [self.vessel], [self.zone])
        self.assertIn("Not proven optimal", plan.to_dict()["method"])

    def test_opportunities_do_not_commit_capacity(self):
        """A carrier evaluating connections must not reserve slots by looking.

        Four 80 TEU consignments against one vessel with 400 TEU free: a plan
        would place at most five, but every one of them is individually feasible,
        so all four appear as opportunities.
        """
        shipments = [
            self._shipment(shipment_id=f"S{i}", teu=80.0) for i in range(4)
        ]
        rows = opportunities(shipments, [self.vessel], [self.zone])
        self.assertEqual(len(rows), 4)

    def test_zones_read_the_twin_rather_than_a_second_yard_model(self):
        state = schematic_layout("INMAA", berth_count=6)
        seed_yard(state, 0.5)
        zones = zones_from_state(state)
        self.assertEqual(len(zones), len(state.yard_blocks))
        self.assertAlmostEqual(zones[0].capacity_teu, state.yard_blocks[0].capacity_teu)

    def test_a_far_block_costs_more_transfer_time(self):
        state = schematic_layout("INMAA", berth_count=8)
        zones = zones_from_state(state)
        near = min(zones, key=lambda z: z.quay_transfer_minutes_per_teu)
        far = max(zones, key=lambda z: z.quay_transfer_minutes_per_teu)
        self.assertLess(
            near.quay_transfer_minutes_per_teu, far.quay_transfer_minutes_per_teu
        )


class CraneResourceTests(unittest.TestCase):
    """Cranes are physical: one crane, one berth, and only while cargo is worked."""

    def _berthed(self):
        state = small_state()
        call = state.calls[0]
        berth = next(
            b for b in state.berths
            if b.can_accept(call.loa_m, call.draught_m, call.cargo_type)
            and len(b.crane_ids) >= 2
        )
        apply_action(
            state, Action(kind=ASSIGN_BERTH, call_id="C0", berth_id=berth.berth_id)
        )
        return state, call, berth

    def test_a_vessel_cannot_be_berthed_with_another_berths_crane(self):
        state, call, berth = self._berthed()
        target = next(
            c for c in state.calls
            if c.call_id != "C0" and c.state == APPROACHING
        )
        # A berth this hull actually fits, or the action is refused on
        # compatibility long before the crane rule is ever reached.
        other = next(
            b for b in state.berths
            if b.berth_id != berth.berth_id and b.crane_ids
            and b.occupied_by is None
            and b.can_accept(target.loa_m, target.draught_m, target.cargo_type)
        )
        problem = validate_action(state, Action(
            kind=ASSIGN_BERTH, call_id=target.call_id, berth_id=other.berth_id,
            crane_ids=[berth.crane_ids[0]],
        ))
        self.assertIsNotNone(problem)
        self.assertIn("cannot reach", problem)

    def test_cranes_cannot_be_assigned_to_a_call_that_is_not_working(self):
        state, call, berth = self._berthed()
        call.state = DEPARTED           # gone, but it keeps the berth it worked
        problem = validate_action(state, Action(
            kind=ASSIGN_CRANES, call_id="C0", crane_ids=list(berth.crane_ids[:1]),
        ))
        self.assertIsNotNone(problem)
        self.assertIn("not working cargo", problem)

    def test_adding_a_crane_actually_brings_the_berth_free_sooner(self):
        """The re-plan used to divide the new workload by itself.

        That ratio is 1.0 for every input, so changing the crane set never moved
        free_at_hour and the simulator reported the same completion whether one
        crane worked the ship or four.
        """
        state, call, berth = self._berthed()
        apply_action(state, Action(
            kind=ASSIGN_CRANES, call_id="C0", crane_ids=[berth.crane_ids[0]],
        ))
        with_one = berth.free_at_hour
        apply_action(state, Action(
            kind=ASSIGN_CRANES, call_id="C0", crane_ids=list(berth.crane_ids[:2]),
        ))
        self.assertLess(berth.free_at_hour, with_one)


class PlanCapacityTests(unittest.TestCase):
    """A plan is only worth anything if it respects the ship and the yard.

    Per-shipment compatibility is checked against the vessel's *original*
    capacity, so the only thing standing between a plan and an overloaded vessel
    is the running budget the assignment loop keeps.
    """

    def _shipment(self, **kwargs):
        base = dict(
            shipment_id="S1", teu=10.0, cargo_class="dry",
            destination_port="SGSIN", available_hour=4.0,
        )
        base.update(kwargs)
        return Shipment(**base)

    def test_a_plan_never_exceeds_the_vessels_deadweight(self):
        # Three 400 t shipments, 900 t of deadweight free: TEU and plugs stay
        # healthy throughout, so deadweight is the only thing that can refuse
        # the third.
        vessel = VesselCapacity(
            vessel_id="V1", name="MV Onward", available_teu=1000,
            available_reefer_plugs=100, available_deadweight_t=900.0,
            onward_ports=["SGSIN"], departure_hour=40.0, load_cutoff_hour=36.0,
        )
        zone = StorageZone(
            zone_id="Y1", name="Yard A1", free_teu=5000, capacity_teu=8000,
            reefer_plugs_free=500,
        )
        shipments = [
            self._shipment(shipment_id=f"S{i}", weight_t=400.0) for i in range(3)
        ]
        plan = optimise("INMAA", shipments, [vessel], [zone])
        loaded = sum(
            s.weight_t for s in shipments
            if s.shipment_id in {a.shipment_id for a in plan.assignments}
        )
        self.assertLessEqual(loaded, 900.0)
        self.assertEqual(len(plan.assignments), 2)

    def test_a_plan_never_exceeds_a_yard_blocks_reefer_plugs(self):
        # One block with 30 plugs and three 20 TEU reefers. TEU is ample, so
        # only a residual plug budget can stop the block being oversubscribed.
        vessel = VesselCapacity(
            vessel_id="V1", name="MV Onward", available_teu=1000,
            available_reefer_plugs=500,
            onward_ports=["SGSIN"], departure_hour=40.0, load_cutoff_hour=36.0,
        )
        zone = StorageZone(
            zone_id="Y1", name="Yard A1", free_teu=5000, capacity_teu=8000,
            reefer_plugs_free=30,
        )
        shipments = [
            self._shipment(shipment_id=f"R{i}", teu=20.0, cargo_class="reefer")
            for i in range(3)
        ]
        plan = optimise("INMAA", shipments, [vessel], [zone])
        in_block = [a for a in plan.assignments if a.zone_id == "Y1"]
        self.assertLessEqual(sum(int(a.teu) for a in in_block), 30)


if __name__ == "__main__":
    unittest.main()
