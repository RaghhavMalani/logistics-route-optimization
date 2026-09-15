"""The WorldClock: one instant, four modes, and nobody else asks the wall.

The tests here are deliberately hostile. A clock that is right in LIVE mode
and quietly wrong in a replay is worse than no clock, because the replay is
where the product is scored. So every temporal subsystem is exercised under a
pinned clock and asked to prove it read the pin: the world builder, event
lifetimes, observation freshness, the AIS traffic state machine, scenario
branches, the decision engine inside a mission replay, the attention and
world routes, and the ledger's due-claims query. The last test reads the
source tree and refuses any wall-clock call that is not in the clock module
or carrying a written justification.
"""

from __future__ import annotations

import re
import threading
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from src.portwatch_os.clock import (
    HISTORICAL_MISSION,
    LIVE,
    REPLAY,
    SCENARIO,
    ClockError,
    ClockState,
    WorldClock,
    get_clock,
    reset_clock,
    resolve,
    set_clock,
    wall_now,
    world_now,
)

ROOT = Path(__file__).resolve().parents[1]
T0 = datetime(2021, 3, 23, 8, 0, tzinfo=timezone.utc)
WALL = datetime(2026, 9, 14, 12, 0, tzinfo=timezone.utc)


class ScriptedWall:
    """A wall the test moves by hand."""

    def __init__(self, at: datetime) -> None:
        self.at = at

    def __call__(self) -> datetime:
        return self.at

    def advance(self, seconds: float) -> None:
        self.at = self.at + timedelta(seconds=seconds)


class ClockStateTests(unittest.TestCase):
    def test_live_reads_the_wall_and_nothing_else(self):
        wall = ScriptedWall(WALL)
        clock = WorldClock(wall=wall)
        self.assertEqual(clock.mode, LIVE)
        self.assertEqual(clock.now(), WALL)
        wall.advance(90)
        self.assertEqual(clock.now(), WALL + timedelta(seconds=90))

    def test_a_frozen_replay_reads_its_anchor_however_long_the_wall_runs(self):
        wall = ScriptedWall(WALL)
        clock = WorldClock(wall=wall)
        clock.set_replay(T0, rate=0.0, by="qa")
        for _ in range(5):
            wall.advance(3600)
            self.assertEqual(clock.now(), T0)
        self.assertTrue(clock.describe()["frozen"])
        self.assertEqual(clock.describe()["offsetFromWallSeconds"],
                         round((T0 - wall.at).total_seconds(), 3))

    def test_a_running_replay_advances_at_its_rate(self):
        wall = ScriptedWall(WALL)
        clock = WorldClock(wall=wall)
        clock.set_replay(T0, rate=4.0, by="qa")
        wall.advance(15)
        self.assertEqual(clock.now(), T0 + timedelta(seconds=60))
        clock.seek(T0 + timedelta(hours=1), by="qa")
        self.assertEqual(clock.now(), T0 + timedelta(hours=1))
        wall.advance(30)
        self.assertEqual(clock.now(), T0 + timedelta(hours=1, seconds=120))

    def test_mission_and_scenario_clocks_are_frozen_and_named(self):
        wall = ScriptedWall(WALL)
        clock = WorldClock(wall=wall)
        clock.set_mission(T0, mission_id="suez-ever-given-2021", by="qa")
        wall.advance(10_000)
        self.assertEqual(clock.now(), T0)
        self.assertEqual(clock.describe()["subject"]["missionId"], "suez-ever-given-2021")
        clock.set_scenario(T0 + timedelta(hours=24), scenario_id="br-0001", by="qa")
        self.assertEqual(clock.now(), T0 + timedelta(hours=24))
        self.assertEqual(clock.mode, SCENARIO)
        self.assertEqual(clock.changes, 2)

    def test_misuse_is_refused_not_tolerated(self):
        clock = WorldClock(wall=ScriptedWall(WALL))
        with self.assertRaises(ClockError):
            ClockState(mode="WALL")
        with self.assertRaises(ClockError):
            ClockState(mode=REPLAY)                       # no anchor
        with self.assertRaises(ClockError):
            ClockState(mode=HISTORICAL_MISSION, anchor=T0, rate=1.0)  # frozen modes have no rate
        with self.assertRaises(ClockError):
            clock.set_replay(T0.replace(tzinfo=None))     # naive instants are ambiguous
        with self.assertRaises(ClockError):
            clock.set_replay(T0, rate=-1.0)
        with self.assertRaises(ClockError):
            clock.seek(T0)                                # LIVE cannot be sought

    def test_resolve_prefers_an_explicit_instant_and_reads_naive_as_utc(self):
        clock = WorldClock(wall=ScriptedWall(WALL))
        set_clock(clock)
        try:
            clock.set_mission(T0, mission_id="m")
            self.assertEqual(resolve(None), T0)
            explicit = datetime(2030, 1, 1, tzinfo=timezone.utc)
            self.assertEqual(resolve(explicit), explicit)
            self.assertEqual(resolve(datetime(2030, 1, 1)).tzinfo, timezone.utc)
        finally:
            reset_clock()


class PinningTests(unittest.TestCase):
    def setUp(self):
        self.wall = ScriptedWall(WALL)
        self.clock = WorldClock(wall=self.wall)
        set_clock(self.clock)

    def tearDown(self):
        reset_clock()

    def test_a_pin_is_scoped_and_restored_even_when_the_body_raises(self):
        self.assertEqual(world_now(), WALL)
        with self.clock.pin_mission(T0, mission_id="m"):
            self.assertEqual(world_now(), T0)
            self.assertTrue(self.clock.describe()["pinned"])
            with self.clock.pin_scenario(T0 + timedelta(hours=6), scenario_id="s"):
                self.assertEqual(world_now(), T0 + timedelta(hours=6))
            self.assertEqual(world_now(), T0)
        self.assertEqual(world_now(), WALL)
        with self.assertRaises(RuntimeError):
            with self.clock.pin_mission(T0, mission_id="m"):
                raise RuntimeError("boom")
        self.assertEqual(world_now(), WALL)
        self.assertFalse(self.clock.describe()["pinned"])

    def test_a_pin_does_not_move_the_process_clock_or_count_as_a_change(self):
        before = self.clock.changes
        with self.clock.pin_replay(T0, rate=0.0):
            self.assertEqual(self.clock.mode, REPLAY)
        self.assertEqual(self.clock.mode, LIVE)
        self.assertEqual(self.clock.changes, before)

    def test_a_pin_in_one_thread_is_invisible_to_another(self):
        seen = {}
        entered = threading.Event()
        release = threading.Event()

        def replaying():
            with self.clock.pin_mission(T0, mission_id="m"):
                seen["inside"] = world_now()
                entered.set()
                release.wait(5)

        worker = threading.Thread(target=replaying)
        worker.start()
        self.assertTrue(entered.wait(5))
        seen["other_thread"] = world_now()
        release.set()
        worker.join(5)
        self.assertEqual(seen["inside"], T0)
        self.assertEqual(seen["other_thread"], WALL)

    def test_seek_inside_a_pin_moves_only_the_pin(self):
        with self.clock.pin_mission(T0, mission_id="m"):
            self.clock.seek(T0 + timedelta(hours=2))
            self.assertEqual(world_now(), T0 + timedelta(hours=2))
        self.assertEqual(self.clock.mode, LIVE)


class SubsystemsReadTheClockTests(unittest.TestCase):
    """Every temporal subsystem, asked to prove which instant it used."""

    def setUp(self):
        self.wall = ScriptedWall(WALL)
        self.clock = WorldClock(wall=self.wall)
        set_clock(self.clock)

    def tearDown(self):
        reset_clock()

    def test_utc_is_the_clock_not_the_wall(self):
        from src.portwatch_os.world.quantity import utc

        with self.clock.pin_mission(T0, mission_id="m"):
            self.assertEqual(utc(), T0)
        self.assertEqual(utc(), WALL)

    def test_the_world_builder_evaluates_event_lifetimes_at_the_pinned_instant(self):
        from src.portwatch_os.global_eye.model import GlobalEvent
        from src.portwatch_os.world.build import build_world
        from src.portwatch_os.world.graph import EVENT, key

        event = GlobalEvent(
            event_id="ev-2021", title="Suez blocked", category="canal_restriction", region="Suez",
            lat=30.0, lon=32.5, geolocation_basis="chokepoint",
            first_seen=T0.isoformat(), last_seen=T0.isoformat(), source_count=3,
            confidence=0.9, severity=0.9, claim="SUEZ closure holds", horizon_hours=72.0,
            chokepoints=["SUEZ"], data_source="test",
        )
        # At the wall (2026) a 72 h claim from 2021 lapsed years ago.
        lapsed = build_world(events=[event]).at(world_now())
        self.assertIsNone(lapsed.node(key(EVENT, "ev-2021")))
        # Inside the mission the same claim is live, and the graph says so.
        with self.clock.pin_mission(T0 + timedelta(hours=1), mission_id="m"):
            live = build_world(events=[event]).at(world_now())
            self.assertIsNotNone(live.node(key(EVENT, "ev-2021")))

    def test_observation_age_is_measured_against_the_clock_and_timestamps_never_move(self):
        from src.portwatch_os.fabric.observation import observe

        source_at = T0 - timedelta(hours=1)
        reading = observe(
            provider_id="test", capability="ais", value={"x": 1}, source_timestamp=source_at,
            valid_for_hours=6.0, coverage="unit", licence_mode="RESEARCH", now=T0,
        )
        with self.clock.pin_mission(T0, mission_id="m"):
            self.assertAlmostEqual(reading.age_seconds(), 3600.0)
            self.assertFalse(reading.expired())
        # Back at the wall the same reading is five years old and expired.
        self.assertGreater(reading.age_seconds(), 5 * 365 * 24 * 3600)
        self.assertTrue(reading.expired())
        # The clock never rewrote the observation to make it look current.
        self.assertEqual(reading.source_timestamp, source_at)

    def test_the_ais_state_machine_ages_its_last_observation_against_the_clock(self):
        from src.portwatch_os.fabric.ais.client import AisStreamClient

        client = AisStreamClient(api_key=None)
        client.status.last_good_observation_at = T0 - timedelta(minutes=2)
        client.status.messages_seen = 5
        with self.clock.pin_mission(T0, mission_id="m"):
            fresh = client.traffic_source(replay_chosen=False)
        aged = client.traffic_source(replay_chosen=False)
        self.assertNotEqual(fresh["mode"], aged["mode"],
                            "the same client read as current at the pin and as lapsed at the wall")

    def test_a_scenario_branch_carries_its_instant_and_pins_it_while_building(self):
        from src.portwatch_os.world.branch import Assumption, CLOSE_CHOKEPOINT, ObservedWorldState, branch
        from src.portwatch_os.world.build import build_world
        from src.portwatch_os.world.live import Revision

        at = T0 + timedelta(hours=12)
        state = ObservedWorldState(
            state_id="obs", revision=Revision("REPLAY", None, "e", "f", 0), at=at,
            graph=build_world(now=at), traffic_mode="REPLAY",
        )
        seen = {}
        from src.portwatch_os.world import branch as module

        original = module._close_chokepoint

        def spy(graph, branch_id, assumption, now):
            seen["clock"] = world_now()
            seen["mode"] = self.clock.mode
            return original(graph, branch_id, assumption, now)

        module._close_chokepoint = spy
        try:
            made = branch(state, [Assumption(kind=CLOSE_CHOKEPOINT, subject="SUEZ", value=1.0)],
                          branch_id="br-test", now=at)
        finally:
            module._close_chokepoint = original
        self.assertEqual(made.created_at, at)
        self.assertEqual(seen["clock"], at)
        self.assertEqual(seen["mode"], SCENARIO)
        self.assertEqual(self.clock.mode, LIVE)

    def test_the_decision_engine_inside_a_mission_reads_the_mission_clock(self):
        from src.portwatch_os.decision import DecisionActor, DecisionEngine
        from src.portwatch_os.decision.model import SHIPPING_COMPANY
        from src.portwatch_os.missions import MissionReplay, get_mission

        mission = get_mission("suez-ever-given-2021")
        replay = MissionReplay(mission, DecisionEngine(), replay_id="clock-test")
        actor = DecisionActor(role=SHIPPING_COMPANY, organisation="qa", vessel_ids=("MSN-001",))
        problem = replay.decide("MSN-001", actor)
        # The problem's instant and its creation stamp are the mission's, not 2026's.
        self.assertEqual(datetime.fromisoformat(problem.at), mission.start)
        created = datetime.fromisoformat(problem.created_at)
        self.assertEqual(created, mission.start)
        for option in problem.options:
            if option.evaluation is not None:
                self.assertEqual(datetime.fromisoformat(option.evaluation.computed_at), mission.start)
        # And the process clock was never moved by the replay.
        self.assertEqual(self.clock.mode, LIVE)
        self.assertEqual(world_now(), WALL)

    def test_a_mission_replay_pins_historical_mission_mode_for_its_reads(self):
        from src.portwatch_os.decision import DecisionEngine
        from src.portwatch_os.missions import MissionReplay, get_mission

        replay = MissionReplay(get_mission("suez-ever-given-2021"), DecisionEngine(), replay_id="pin-test")
        replay.seek(replay.mission.start + timedelta(hours=30))
        with replay.pinned():
            self.assertEqual(self.clock.mode, HISTORICAL_MISSION)
            self.assertEqual(world_now(), replay.clock)
            self.assertEqual(self.clock.describe()["subject"]["missionId"], "suez-ever-given-2021")
        state = replay.state()
        self.assertEqual(state.at, replay.clock)
        self.assertEqual(self.clock.mode, LIVE)

    def test_the_ledger_asks_for_due_claims_at_the_clock(self):
        from src.portwatch_os.ledger.store import SqliteLedgerStore
        from src.portwatch_os.ledger.schema import PredictionContext, PredictionRecord

        store = SqliteLedgerStore(":memory:")
        store.record_prediction(PredictionRecord(
            prediction_id="p-2021", domain="global_eye", kind="binary", target="closure_within_72h",
            subject="ev", model="test", model_version="1", issued_at=T0.isoformat(),
            valid_at=(T0 + timedelta(hours=72)).isoformat(), context=PredictionContext(region="Suez"),
            predicted_value=0.7,
        ))
        with self.clock.pin_mission(T0 + timedelta(hours=1), mission_id="m"):
            self.assertEqual(store.due_predictions(), [], "a claim 71 h from due is not due at the pin")
        self.assertEqual([p.prediction_id for p in store.due_predictions()], ["p-2021"])

    def test_the_finance_basis_prices_validity_at_the_clock(self):
        from src.portwatch_os.finance.basis import CostBasis

        from src.portwatch_os.finance.basis import PUBLIC_TARIFF, CostRate
        from src.portwatch_os.finance.money import DAY

        # A rate valid only inside the mission's month: priced at the pin, absent at the wall.
        basis = CostBasis([CostRate(
            primitive="charter_day", value=24000.0, currency="USD", unit=DAY, scope="*",
            valid_from=(T0 - timedelta(days=1)).isoformat(), valid_to=(T0 + timedelta(days=30)).isoformat(),
            source="unit test schedule", source_type=PUBLIC_TARIFF, confidence=0.9,
        )])
        with self.clock.pin_mission(T0, mission_id="m"):
            self.assertTrue(basis.to_dict()["coverage"]["charter_day"]["available"])
        self.assertFalse(basis.to_dict()["coverage"]["charter_day"]["available"])


class ApiReadsTheClockTests(unittest.TestCase):
    ADMIN = {"X-PortWatch-Role": "NATIONAL_ADMIN", "X-PortWatch-Actor": "qa"}

    def setUp(self):
        from fastapi.testclient import TestClient

        from backend.app.main import app

        self.wall = ScriptedWall(WALL)
        self.clock = WorldClock(wall=self.wall)
        set_clock(self.clock)
        self.client = TestClient(app)

    def tearDown(self):
        reset_clock()

    def test_the_clock_route_moves_every_route_that_omits_at(self):
        body = self.client.get("/api/world/clock").json()
        self.assertEqual(body["mode"], LIVE)
        moved = self.client.post(
            "/api/world/clock", json={"mode": "REPLAY", "at": T0.isoformat(), "rate": 0, "reason": "qa"},
            headers=self.ADMIN,
        )
        self.assertEqual(moved.status_code, 200, moved.text)
        self.assertEqual(moved.json()["now"], T0.isoformat(timespec="seconds"))
        self.assertEqual(moved.json()["setBy"], "qa")
        for path in ("/api/world/state", "/api/world/cascades", "/api/attention"):
            response = self.client.get(path, headers=self.ADMIN)
            self.assertEqual(response.status_code, 200, f"{path}: {response.text}")
            self.assertEqual(datetime.fromisoformat(response.json()["at"]), T0, path)
        # An explicit instant is a query, and still wins.
        explicit = self.client.get("/api/world/state", params={"at": (T0 + timedelta(hours=5)).isoformat()})
        self.assertEqual(datetime.fromisoformat(explicit.json()["at"]), T0 + timedelta(hours=5))

    def test_only_national_command_may_move_the_clock_and_must_be_named(self):
        refused = self.client.post("/api/world/clock", json={"mode": "LIVE"},
                                   headers={"X-PortWatch-Role": "SHIPPING_COMPANY", "X-PortWatch-Actor": "qa"})
        self.assertEqual(refused.status_code, 403)
        unnamed = self.client.post("/api/world/clock", json={"mode": "LIVE"},
                                   headers={"X-PortWatch-Role": "NATIONAL_ADMIN"})
        self.assertEqual(unnamed.status_code, 401)
        bad = self.client.post("/api/world/clock", json={"mode": "HISTORICAL_MISSION", "at": T0.isoformat()},
                               headers=self.ADMIN)
        self.assertEqual(bad.status_code, 400)
        self.assertEqual(self.clock.mode, LIVE)

    def test_health_reports_both_the_wall_and_the_world(self):
        self.client.post("/api/world/clock", json={"mode": "HISTORICAL_MISSION", "at": T0.isoformat(),
                                                   "missionId": "suez-ever-given-2021"}, headers=self.ADMIN)
        body = self.client.get("/api/health").json()
        self.assertEqual(datetime.fromisoformat(body["serverTimeUtc"]), WALL)
        self.assertEqual(body["worldClock"]["mode"], HISTORICAL_MISSION)
        self.assertEqual(datetime.fromisoformat(body["worldClock"]["now"]), T0)


class NobodyElseAsksTheWallTests(unittest.TestCase):
    """The rule, enforced by reading the code."""

    DOMAIN = ("src/portwatch_os", "backend/app", "portwatch")
    FORBIDDEN = re.compile(r"datetime\.now\(|datetime\.utcnow\(|\btime\.time\(\)|date\.today\(\)")

    def _files(self):
        for base in self.DOMAIN:
            root = ROOT / base
            if not root.exists():
                continue
            for path in root.rglob("*.py"):
                if "__pycache__" in path.parts:
                    continue
                yield path

    def test_no_domain_module_reads_the_wall_directly(self):
        offenders = []
        for path in self._files():
            if path.name == "clock.py" and path.parent.name == "portwatch_os":
                continue
            for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
                if self.FORBIDDEN.search(line) and not line.strip().startswith("#"):
                    offenders.append(f"{path.relative_to(ROOT)}:{number}: {line.strip()}")
        self.assertEqual(offenders, [], "wall-clock reads outside the WorldClock:\n" + "\n".join(offenders))

    def test_every_wall_read_carries_a_written_justification(self):
        unjustified = []
        for path in self._files():
            if path.name == "clock.py" and path.parent.name == "portwatch_os":
                continue
            lines = path.read_text(encoding="utf-8").splitlines()
            for index, line in enumerate(lines):
                if "wall_now(" not in line or "import" in line:
                    continue
                window = " ".join(lines[max(0, index - 2): index + 1])
                if "# wall-clock:" not in window:
                    unjustified.append(f"{path.relative_to(ROOT)}:{index + 1}: {line.strip()}")
        self.assertEqual(unjustified, [], "wall_now() without a '# wall-clock:' reason:\n" + "\n".join(unjustified))

    def test_wall_now_is_aware_utc(self):
        self.assertEqual(wall_now().tzinfo, timezone.utc)
        self.assertEqual(get_clock().wall().tzinfo, timezone.utc)


if __name__ == "__main__":
    unittest.main()
