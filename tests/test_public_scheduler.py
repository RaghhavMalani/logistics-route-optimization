from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

import pytest

from src.portwatch_os.clock import WorldClock, get_clock, reset_clock, set_clock
from src.portwatch_os.freshness import RefreshCoordinator
from src.portwatch_os.freshness.jobs import install_product_jobs
from src.portwatch_os.freshness.public_ports import public_port_jobs
from src.portwatch_os.intelligence.public_ports import PublicPilot, stamp

NOW = datetime(2026, 10, 7, 10, tzinfo=timezone.utc)
FIXTURES = Path(__file__).parent/"fixtures"/"public_ports"


@pytest.fixture
def setup(tmp_path, monkeypatch):
    class Wall:
        at = NOW
        def __call__(self):
            return self.at
    wall = Wall()
    set_clock(WorldClock(wall=wall))
    monkeypatch.setenv("PORTWATCH_PUBLIC_PORT_AUTOREFRESH", "1")
    store = PublicPilot(tmp_path)
    def fetch(url):
        if url.endswith("/traffic/"):
            return b'<a href="https://www.paradipport.gov.in/uploads/2026/10/dtr0610.pdf">report</a>'
        filename = "paradip-2026-10-06.pdf" if "paradip" in url else "chennai-eta-2026-10-07.pdf" if url.endswith("eta.pdf") else "chennai-position-2026-10-07.pdf"
        return (FIXTURES/filename).read_bytes()
    with patch("src.portwatch_os.intelligence.public_ports.fetch", side_effect=fetch):
        yield store, wall, fetch
    store.close()
    reset_clock()


def test_backend_jobs_collect_preserve_restart_cadence_and_independent_retry(setup):
    store, wall, fetch = setup
    coordinator = RefreshCoordinator()
    for job in public_port_jobs(lambda: store):
        coordinator.register(job)
    assert coordinator.tick(wait=True) == ["public_ports_INPRT", "public_ports_INMAA"]
    original = store.workspace("INMAA", wall.at)
    assert original["counts"]["frozen"] > 0
    first_seen = [(s["snapshotId"], s["firstSeenAt"]) for s in original["snapshots"]]
    frozen = [(c["caseId"], c["etaAt"], c["frozenAt"]) for c in original["cases"]]
    cohort = original["cohorts"]
    assert coordinator.tick(wait=True) == []
    wall.at += timedelta(hours=1)
    coordinator.request("public_ports_INMAA", reason="verified manual refresh", wait=True)
    repeated = store.workspace("INMAA", wall.at)
    assert first_seen == [(s["snapshotId"], s["firstSeenAt"]) for s in repeated["snapshots"]]
    assert frozen == [(c["caseId"], c["etaAt"], c["frozenAt"]) for c in repeated["cases"]]
    assert cohort == repeated["cohorts"]
    assert coordinator.record("public_ports_INMAA").last_result.changed is False
    restarted = RefreshCoordinator()
    for job in public_port_jobs(lambda: store):
        restarted.register(job)
    assert restarted.due() == []
    wall.at += timedelta(hours=3)
    def fail_chennai(url):
        if "chennai" in url:
            raise OSError("Source unavailable")
        return fetch(url)
    with patch("src.portwatch_os.intelligence.public_ports.fetch", side_effect=fail_chennai):
        assert restarted.tick(wait=True) == ["public_ports_INPRT", "public_ports_INMAA"]
    assert restarted.record("public_ports_INPRT").last_result.ok
    assert not restarted.record("public_ports_INMAA").last_result.ok
    assert restarted.describe("public_ports_INMAA")["job"]["state"] == "RETRY_SCHEDULED"
    assert store.collection_status("INMAA", wall.at)["lastSuccessfulCollectionAt"] == stamp(NOW+timedelta(hours=1))
    assert store.collection_status("INMAA", wall.at)["lastRun"]["errors"]
    assert store.workspace("INMAA", NOW)["counts"] == original["counts"]
    assert store.collection_status("INMAA", NOW)["lastRun"]["errors"] == []


def test_registration_background_start_and_replay_pause(setup, monkeypatch):
    import time
    store, wall, _ = setup
    installed = install_product_jobs(RefreshCoordinator())
    assert {"public_ports_INPRT", "public_ports_INMAA", "vesselfinder_INPRT", "vesselfinder_INMAA"} <= set(installed.artifacts())
    coordinator = RefreshCoordinator(tick_seconds=.02)
    for job in public_port_jobs(lambda: store):
        coordinator.register(job)
    with get_clock().pin_replay(NOW):
        assert coordinator.tick(wait=True) == []
    monkeypatch.setenv("PORTWATCH_PUBLIC_PORT_AUTOREFRESH", "0")
    assert coordinator.tick(wait=True) == []
    monkeypatch.setenv("PORTWATCH_PUBLIC_PORT_AUTOREFRESH", "1")
    coordinator.start()
    try:
        deadline = time.monotonic()+10
        while time.monotonic() < deadline and not all(coordinator.record(a).last_result for a in coordinator.artifacts()):
            time.sleep(.02)
        assert all(coordinator.record(a).last_result.ok for a in coordinator.artifacts())
    finally:
        coordinator.stop()
