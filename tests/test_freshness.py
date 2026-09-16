"""The freshness coordinator: every responsibility it claims, checked.

    know the SLA                 a policy per artifact; state from the artifact's own instant
    refresh before expiry        due at fresh_for - lead, not after the SLA has lapsed
    no duplicate refreshes       a request for a running job joins it
    last known good              a failed job leaves the artifact and its instant alone
    failure is exposed           every attempt is a result with its error
    bounded backoff              attempts double their wait to a cap and stop at max_attempts
    timestamps are never moved   a stale artifact stays stale until a real refresh produces a new one
    invalidate what changed      only the dependants of a changed artifact are told

Plus the product's own jobs, probed against the real cache on disk, and the
admin routes that expose them.
"""

from __future__ import annotations

import os
import threading
import time
import unittest
from datetime import datetime, timedelta, timezone
from typing import List, Optional

from src.portwatch_os.clock import WorldClock, reset_clock, set_clock
from src.portwatch_os.freshness import (
    DUE,
    EXPIRED,
    FAILED,
    FRESH,
    IDLE,
    MISSING,
    RETRY_SCHEDULED,
    RUNNING,
    STALE,
    ArtifactProbe,
    FreshnessPolicy,
    JobOutcome,
    RefreshCoordinator,
    RefreshJob,
    RefreshResult,
)
from src.portwatch_os.telemetry import get_telemetry, reset_telemetry

WALL = datetime(2026, 9, 14, 12, 0, tzinfo=timezone.utc)


class ScriptedWall:
    def __init__(self, at: datetime) -> None:
        self.at = at

    def __call__(self) -> datetime:
        return self.at

    def advance(self, **delta) -> None:
        self.at = self.at + timedelta(**delta)


class FakeArtifact:
    """A file that remembers when it was produced and can be told to fail."""

    def __init__(self, produced_at: Optional[datetime]) -> None:
        self.produced_at = produced_at
        self.versions = 0
        self.fail_next = 0
        self.runs: List[dict] = []
        self.block: Optional[threading.Event] = None

    def probe(self) -> ArtifactProbe:
        return ArtifactProbe(observed_at=self.produced_at, detail={"versions": self.versions})

    def make_job(self, wall: ScriptedWall):
        def run(context) -> JobOutcome:
            self.runs.append({"attempt": context.attempt, "reason": context.reason, "at": context.started_at})
            if self.block is not None:
                self.block.wait(5)
            if self.fail_next > 0:
                self.fail_next -= 1
                raise ConnectionError("upstream refused")
            self.versions += 1
            self.produced_at = wall.at
            return JobOutcome(changed=True, observed_at=wall.at, detail={"version": self.versions})
        return run


POLICY = FreshnessPolicy(
    artifact="register", provider="test", fresh_for=timedelta(hours=6), lead=timedelta(hours=1),
    stale_after=timedelta(hours=72), max_attempts=3, backoff_base=timedelta(seconds=30),
    backoff_cap=timedelta(minutes=2), feeds=("world",),
)
WORLD_POLICY = FreshnessPolicy(artifact="world", provider="derived", fresh_for=timedelta(hours=72),
                               stale_after=timedelta(hours=72))
OTHER_POLICY = FreshnessPolicy(artifact="other", provider="test", fresh_for=timedelta(hours=200),
                               stale_after=timedelta(hours=300))


class PolicyTests(unittest.TestCase):
    def test_states_follow_the_artifacts_own_age(self):
        self.assertEqual(POLICY.state_for(None), MISSING)
        self.assertEqual(POLICY.state_for(timedelta(hours=1)), FRESH)
        self.assertEqual(POLICY.state_for(timedelta(hours=5)), DUE)          # within lead of the SLA
        self.assertEqual(POLICY.state_for(timedelta(hours=6, seconds=1)), EXPIRED)
        self.assertEqual(POLICY.state_for(timedelta(hours=73)), STALE)

    def test_backoff_doubles_to_a_cap(self):
        self.assertEqual(POLICY.backoff(1), timedelta(seconds=30))
        self.assertEqual(POLICY.backoff(2), timedelta(seconds=60))
        self.assertEqual(POLICY.backoff(3), timedelta(seconds=120))
        self.assertEqual(POLICY.backoff(9), timedelta(minutes=2))

    def test_a_policy_that_cannot_be_kept_is_refused(self):
        with self.assertRaises(ValueError):
            FreshnessPolicy(artifact="x", provider="p", fresh_for=timedelta(hours=2), stale_after=timedelta(hours=1))
        with self.assertRaises(ValueError):
            FreshnessPolicy(artifact="x", provider="p", fresh_for=timedelta(hours=2), stale_after=timedelta(hours=3),
                            lead=timedelta(hours=2))


class CoordinatorTests(unittest.TestCase):
    def setUp(self):
        self.wall = ScriptedWall(WALL)
        set_clock(WorldClock(wall=self.wall))
        reset_telemetry()
        self.coordinator = RefreshCoordinator(tick_seconds=1.0)
        self.register = FakeArtifact(produced_at=WALL - timedelta(hours=2))
        self.world_invalidations: List[str] = []
        self.other = FakeArtifact(produced_at=WALL)
        self.coordinator.register(RefreshJob(policy=POLICY, probe=self.register.probe,
                                             run=self.register.make_job(self.wall)))
        self.coordinator.register(RefreshJob(policy=WORLD_POLICY, probe=lambda: ArtifactProbe(observed_at=WALL),
                                             invalidate=self.world_invalidations.append))
        self.coordinator.register(RefreshJob(policy=OTHER_POLICY, probe=self.other.probe,
                                             run=self.other.make_job(self.wall)))

    def tearDown(self):
        self.coordinator.stop()
        reset_clock()
        reset_telemetry()

    def test_the_sla_is_known_and_reported_per_artifact(self):
        row = self.coordinator.describe("register")
        self.assertEqual(row["state"], FRESH)
        self.assertEqual(row["ageSeconds"], 7200.0)
        self.assertEqual(row["policy"]["freshForSeconds"], 6 * 3600)
        self.assertEqual(row["expiresAt"], (WALL + timedelta(hours=4)).isoformat(timespec="seconds"))
        self.assertEqual(row["job"]["state"], IDLE)

    def test_refresh_happens_before_expiry_not_after(self):
        self.assertEqual(self.coordinator.due(), [])
        self.wall.advance(hours=2, minutes=59)
        self.assertEqual(self.coordinator.due(), [], "fresh with more than the lead remaining: not due")
        self.wall.advance(minutes=2)                      # age 5 h 01 m: inside the one-hour lead
        self.assertEqual(self.coordinator.describe("register")["state"], DUE)
        started = self.coordinator.tick(wait=True)
        self.assertEqual(started, ["register"])
        self.assertEqual(self.register.versions, 1)
        self.assertEqual(self.coordinator.describe("register")["state"], FRESH)
        self.assertEqual(self.register.runs[0]["reason"], "scheduled")

    def test_a_running_job_is_joined_not_duplicated(self):
        self.register.block = threading.Event()
        self.wall.advance(hours=7)
        first = self.coordinator.request("register", reason="one")
        self.assertEqual(first, "started")
        time.sleep(0.05)
        self.assertEqual(self.coordinator.describe("register")["job"]["state"], RUNNING)
        second = self.coordinator.request("register", reason="two")
        self.assertEqual(second, "already running")
        self.assertEqual(self.coordinator.tick(), [], "the scheduler does not start a second copy either")
        self.register.block.set()
        self.coordinator.wait("register")
        self.assertEqual(self.register.versions, 1)
        self.assertEqual(len(self.register.runs), 1)

    def test_a_failed_refresh_keeps_the_last_known_good_and_its_instant(self):
        produced = self.register.produced_at
        self.wall.advance(hours=7)
        self.register.fail_next = 1
        self.coordinator.request("register", reason="qa", wait=True)
        row = self.coordinator.describe("register")
        self.assertEqual(row["observedAt"], produced.isoformat(timespec="seconds"), "the instant did not move")
        self.assertEqual(row["state"], EXPIRED, "still served, labelled from its real age")
        self.assertEqual(row["job"]["lastResult"]["ok"], False)
        self.assertIn("upstream refused", row["job"]["lastResult"]["error"])
        self.assertIsNone(row["job"]["lastGood"])
        self.assertEqual(self.register.versions, 0)

    def test_failure_is_exposed_in_every_attempts_result_and_in_telemetry(self):
        self.wall.advance(hours=7)
        self.register.fail_next = 2
        self.coordinator.request("register", reason="qa", wait=True)
        self.wall.advance(minutes=1)
        self.coordinator.tick(wait=True)
        self.wall.advance(minutes=2)
        self.coordinator.tick(wait=True)
        row = self.coordinator.describe("register")
        history = row["job"]["history"]
        self.assertEqual([h["ok"] for h in history], [False, False, True])
        self.assertEqual([h["attempt"] for h in history], [1, 2, 3])
        self.assertEqual(row["job"]["lastGood"]["attempt"], 3)
        self.assertEqual(get_telemetry().counter("freshness.failed", artifact="register"), 2.0)
        self.assertEqual(get_telemetry().counter("freshness.succeeded", artifact="register"), 1.0)
        failures = get_telemetry().snapshot()["events"]["freshness.failures"]
        self.assertEqual(len(failures), 2)

    def test_retries_back_off_and_stop_at_the_bound(self):
        self.wall.advance(hours=7)
        self.register.fail_next = 10
        self.coordinator.request("register", reason="qa", wait=True)
        row = self.coordinator.describe("register")
        self.assertEqual(row["job"]["state"], RETRY_SCHEDULED)
        # attempt 2 waits backoff(2) = 60 s
        self.assertEqual(row["job"]["nextAttemptAt"], (self.wall.at + timedelta(seconds=60)).isoformat(timespec="seconds"))
        self.assertEqual(self.coordinator.due(), [], "not due before the backoff elapses")
        self.wall.advance(seconds=59)
        self.assertEqual(self.coordinator.due(), [])
        self.wall.advance(seconds=2)
        self.assertEqual(self.coordinator.tick(wait=True), ["register"])
        row = self.coordinator.describe("register")
        # attempt 3 waits backoff(3) = 120 s, the cap
        self.assertEqual(row["job"]["nextAttemptAt"], (self.wall.at + timedelta(seconds=120)).isoformat(timespec="seconds"))
        self.wall.advance(seconds=121)
        self.assertEqual(self.coordinator.tick(wait=True), ["register"])
        row = self.coordinator.describe("register")
        self.assertEqual(row["job"]["state"], FAILED, "three attempts, all failed: the cycle is over")
        self.assertEqual(row["job"]["attemptsThisCycle"], 3)
        # Held off a full cap before the scheduler may try a new cycle.
        self.wall.advance(seconds=60)
        self.assertEqual(self.coordinator.tick(wait=True), [])
        self.wall.advance(seconds=61)
        self.assertEqual(self.coordinator.tick(wait=True), ["register"])
        self.assertEqual(len(self.register.runs), 4)
        # An operator's request resets the bound: they asked.
        self.register.fail_next = 0
        self.coordinator.request("register", reason="operator", wait=True, requested=True)
        self.assertEqual(self.coordinator.describe("register")["job"]["state"], IDLE)
        self.assertEqual(self.register.versions, 1)

    def test_stale_is_never_converted_to_fresh_by_moving_a_timestamp(self):
        self.wall.advance(hours=80)
        self.assertEqual(self.coordinator.describe("register")["state"], STALE)
        self.register.fail_next = 10
        for _ in range(3):
            self.coordinator.request("register", reason="qa", wait=True, requested=True)
            self.assertEqual(self.coordinator.describe("register")["state"], STALE)
            self.assertEqual(self.coordinator.describe("register")["ageSeconds"], 82 * 3600.0)
        self.register.fail_next = 0
        self.coordinator.request("register", reason="qa", wait=True, requested=True)
        self.assertEqual(self.coordinator.describe("register")["state"], FRESH)
        self.assertEqual(self.coordinator.describe("register")["ageSeconds"], 0.0)

    def test_only_the_dependants_of_a_changed_artifact_are_invalidated(self):
        self.wall.advance(hours=7)
        self.coordinator.request("register", reason="qa", wait=True)
        self.assertEqual(self.world_invalidations, ["register"])
        self.assertEqual(self.coordinator.describe("world")["job"]["invalidatedBy"], ["register"])
        self.assertEqual(self.coordinator.describe("other")["job"]["invalidatedBy"], [])
        self.assertEqual(get_telemetry().counter("freshness.invalidations", artifact="world", source="register"), 1.0)
        # A refresh that found nothing new invalidates nobody.
        self.coordinator.record("register").job.run = lambda ctx: JobOutcome(changed=False, observed_at=self.wall.at)
        self.coordinator.request("register", reason="qa", wait=True, requested=True)
        self.assertEqual(self.world_invalidations, ["register"])

    def test_a_derived_artifact_is_never_scheduled(self):
        self.wall.advance(hours=100)
        self.assertNotIn("world", self.coordinator.due())
        self.assertEqual(self.coordinator.request("world", reason="qa"), "not refreshable")

    def test_a_disabled_job_says_why_and_never_runs(self):
        self.coordinator.record("other").job.eligibility = lambda: "no key configured"
        self.wall.advance(hours=5)
        self.assertNotIn("other", self.coordinator.due())
        self.assertEqual(self.coordinator.request("other", reason="qa"), "disabled: no key configured")
        self.assertEqual(self.coordinator.describe("other")["job"]["state"], "DISABLED")
        self.assertEqual(self.other.runs, [])

    def test_the_scheduler_thread_runs_due_jobs_on_its_own(self):
        self.wall.advance(hours=7)
        self.coordinator.tick_seconds = 0.05
        self.coordinator.start()
        deadline = time.time() + 5
        while self.register.versions == 0 and time.time() < deadline:
            time.sleep(0.02)
        self.coordinator.stop()
        self.assertEqual(self.register.versions, 1)
        self.assertFalse(self.coordinator.running)

    def test_the_status_summary_counts_every_state(self):
        status = self.coordinator.status()
        self.assertEqual(status["summary"][FRESH], 3)
        self.assertEqual({r["artifact"] for r in status["artifacts"]}, {"register", "world", "other"})


class ProductJobsTests(unittest.TestCase):
    """The real artifacts, probed on disk. No network; no job is run."""

    def setUp(self):
        os.environ["PORTWATCH_LICENCE_MODE"] = "DEMO"
        reset_telemetry()

    def tearDown(self):
        reset_telemetry()

    def test_every_product_artifact_has_a_policy_a_probe_and_a_rationale(self):
        from src.portwatch_os.freshness.jobs import install_product_jobs

        coordinator = install_product_jobs(RefreshCoordinator())
        names = coordinator.artifacts()
        for expected in ("events", "marine", "port_forecast", "macro", "port_weather", "news", "traffic", "world"):
            self.assertIn(expected, names)
        for row in coordinator.status()["artifacts"]:
            self.assertTrue(row["policy"]["rationale"], f"{row['artifact']} has no rationale")
            self.assertIn(row["state"], ("MISSING", "FRESH", "DUE", "EXPIRED", "STALE", "NOT_APPLICABLE", "SIMULATED"))

    def test_the_register_probe_reads_the_bundles_own_instant(self):
        from src.portwatch_os.freshness.jobs import NEWS_BUNDLE, probe_events

        if not NEWS_BUNDLE.exists():
            self.skipTest("no news bundle on this machine")
        probe = probe_events()
        self.assertIsNotNone(probe.observed_at)
        self.assertIn("events", probe.detail)

    def test_traffic_under_the_replay_is_simulated_and_not_a_job(self):
        from src.portwatch_os.freshness.jobs import probe_traffic, traffic_eligibility

        if os.getenv("AISSTREAM_API_KEY"):
            self.skipTest("a live key is configured")
        self.assertEqual(probe_traffic().override_state, "SIMULATED")
        self.assertIsNotNone(traffic_eligibility())

    def test_invalidating_the_world_drops_the_held_builds(self):
        from src.portwatch_os.freshness.jobs import invalidate_world
        from src.portwatch_os.world.build import build_world
        from src.portwatch_os.world.live import Revision, get_live_world, reset_live_world

        reset_live_world()
        live = get_live_world()
        revision = Revision("DEMO", None, "e", "f", 0)
        live.graph(revision, build=lambda: (build_world(), []), now=WALL)
        self.assertEqual(live.status()["heldBuilds"], 1)
        invalidate_world("events")
        self.assertEqual(live.status()["heldBuilds"], 0)
        self.assertEqual(get_telemetry().counter("world.invalidations", by_artifact="events"), 1.0)
        reset_live_world()


class AdminRoutesTests(unittest.TestCase):
    ADMIN = {"X-PortWatch-Role": "NATIONAL_ADMIN", "X-PortWatch-Actor": "qa"}

    def setUp(self):
        os.environ["PORTWATCH_LICENCE_MODE"] = "DEMO"
        os.environ["PORTWATCH_FRESHNESS_SCHEDULER"] = "0"
        from fastapi.testclient import TestClient

        from backend.app.main import app

        self.client = TestClient(app)

    def test_freshness_is_national_command_only_and_carries_no_secret(self):
        refused = self.client.get("/api/admin/freshness", headers={"X-PortWatch-Role": "PORT_AUTHORITY"})
        self.assertEqual(refused.status_code, 403)
        body = self.client.get("/api/admin/freshness", headers=self.ADMIN).json()
        self.assertIn("artifacts", body)
        self.assertIn("summary", body)
        text = str(body)
        for name in ("AISSTREAM_API_KEY", "OPEN_METEO_API_KEY"):
            value = os.getenv(name)
            if value:
                self.assertNotIn(value, text)

    def test_a_refresh_request_must_be_named_and_is_attributed(self):
        unnamed = self.client.post("/api/admin/freshness/world/refresh", headers={"X-PortWatch-Role": "NATIONAL_ADMIN"})
        self.assertEqual(unnamed.status_code, 401)
        missing = self.client.post("/api/admin/freshness/nothing/refresh", headers=self.ADMIN)
        self.assertEqual(missing.status_code, 404)
        derived = self.client.post("/api/admin/freshness/world/refresh", headers=self.ADMIN)
        self.assertEqual(derived.status_code, 200)
        self.assertEqual(derived.json()["outcome"], "not refreshable")

    def test_diagnostics_carry_world_traffic_and_clock_state(self):
        self.client.get("/api/world/state")
        body = self.client.get("/api/admin/diagnostics", headers=self.ADMIN).json()
        for key in ("counters", "gauges", "timers", "events", "world", "worldClock", "traffic", "freshness"):
            self.assertIn(key, body)
        self.assertTrue(any(k.startswith("api.latency") for k in body["timers"]))

    def test_readiness_judges_the_running_configuration(self):
        body = self.client.get("/api/admin/readiness", headers=self.ADMIN).json()
        self.assertEqual(body["mode"], "DEMO")
        self.assertEqual(body["modeSource"], "env")
        names = {c["name"] for c in body["checks"]}
        for expected in ("licence_mode", "credentials", "provider:marine", "traffic_honesty",
                         "storage:data/cache", "freshness:events", "world_clock"):
            self.assertIn(expected, names)
        commercial = self.client.get("/api/admin/readiness", params={"mode": "COMMERCIAL"}, headers=self.ADMIN).json()
        self.assertEqual(commercial["mode"], "COMMERCIAL")
        if not os.getenv("OPEN_METEO_API_KEY"):
            self.assertIn("credentials", commercial["refusals"])


class DeploymentValidatorTests(unittest.TestCase):
    """The validator refuses a misleading configuration and a broken feed."""

    def _validate(self, mode, env, traffic):
        from unittest.mock import patch

        from src.portwatch_os.deployment import validate

        with patch("src.portwatch_os.fabric.ais_mode", return_value=traffic):
            return validate(mode=mode, env=env)

    def test_an_unstated_licence_mode_is_refused(self):
        from src.portwatch_os.deployment import resolve_mode

        mode, source, problem = resolve_mode(None, env={})
        self.assertEqual((mode, source), ("COMMERCIAL", "default"))
        self.assertIsNotNone(problem)

    def test_a_refused_ais_credential_fails_readiness(self):
        report = self._validate("RESEARCH", {"PORTWATCH_LICENCE_MODE": "RESEARCH", "AISSTREAM_API_KEY": "refused"}, {
            "mode": "UNAVAILABLE", "providerId": None,
            "statement": "AISStream refused the configured credential",
            "health": {"health": "AUTH_FAILED", "lastError": "invalid key; check AISSTREAM_API_KEY.",
                       "lastGoodObservationAt": None},
        })
        by_name = {c.name: c for c in report.checks}
        self.assertEqual(by_name["traffic_honesty"].status, "PASS")
        self.assertEqual(by_name["traffic_feed"].status, "FAIL")
        self.assertIn("refused", by_name["traffic_feed"].detail)
        self.assertFalse(report.ready)
        self.assertIn("traffic_feed", [c.name for c in report.refusals])

    def test_a_configured_feed_that_has_delivered_nothing_warns(self):
        report = self._validate("RESEARCH", {"PORTWATCH_LICENCE_MODE": "RESEARCH", "AISSTREAM_API_KEY": "k"}, {
            "mode": "UNAVAILABLE", "providerId": None,
            "statement": "a live provider is configured and no valid observation has arrived yet",
            "health": {"health": "DISCONNECTED", "lastError": None, "lastGoodObservationAt": None},
        })
        by_name = {c.name: c for c in report.checks}
        self.assertEqual(by_name["traffic_feed"].status, "WARN")
        self.assertNotIn("traffic_feed", [c.name for c in report.refusals])

    def test_the_chosen_replay_raises_no_feed_check(self):
        report = self._validate("DEMO", {"PORTWATCH_LICENCE_MODE": "DEMO"}, {
            "mode": "SIMULATED_TRAFFIC", "providerId": "ais-replay",
            "statement": "positions are a deterministic replay",
            "health": {"health": "DISCONNECTED", "lastError": None, "lastGoodObservationAt": None},
        })
        names = {c.name for c in report.checks}
        self.assertIn("traffic_honesty", names)
        self.assertNotIn("traffic_feed", names)

    def test_live_without_an_observation_is_a_lie_and_fails(self):
        report = self._validate("RESEARCH", {"PORTWATCH_LICENCE_MODE": "RESEARCH", "AISSTREAM_API_KEY": "k"}, {
            "mode": "LIVE_AIS", "providerId": "aisstream", "statement": "claimed",
            "health": {"health": "LIVE", "lastError": None, "lastGoodObservationAt": None},
        })
        by_name = {c.name: c for c in report.checks}
        self.assertEqual(by_name["traffic_honesty"].status, "FAIL")
        self.assertFalse(report.ready)


if __name__ == "__main__":
    unittest.main()
