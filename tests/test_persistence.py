"""Durable state: what must survive a restart does, what is broken says so.

    the ledger and the advisory register live in PORTWATCH_STATE_DIR
    a corrupt store is refused at open with its path, never replaced
    the probes name the fault; health and readiness carry them
    a ledger route answers 503 on a corrupt ledger, saying nothing was substituted
    a decision computed by another process is served from the ledger, read-only
    a scoped listing finds a tenant's rows behind other tenants' newer ones
    the assumption journal round-trips with its author and refuses an unreadable line
"""

from __future__ import annotations

import os
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from src.portwatch_os.advisories.model import AdvisoryError
from src.portwatch_os.advisories.store import AdvisoryStore, probe_advisory_store
from src.portwatch_os.finance.basis import AssumptionJournal, assumption, observation
from src.portwatch_os.ledger.store import LedgerError, SqliteLedgerStore, probe_ledger


class StoreProbeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.dir = Path(tempfile.mkdtemp(prefix="pw-state-"))

    def test_a_fresh_state_dir_opens_and_counts_zero(self):
        ledger = probe_ledger(self.dir / "ledger.db")
        self.assertTrue(ledger["ok"], ledger)
        self.assertEqual(ledger["counts"]["decisionProblems"], 0)
        self.assertTrue(ledger["durable"])
        advisories = probe_advisory_store(self.dir / "adv.db")
        self.assertTrue(advisories["ok"], advisories)
        self.assertEqual(advisories["counts"]["advisories"], 0)

    def test_a_corrupt_ledger_is_refused_with_its_path_and_left_alone(self):
        path = self.dir / "ledger.db"
        path.write_bytes(b"not a database\n" * 100)
        with self.assertRaises(LedgerError) as caught:
            SqliteLedgerStore(path)
        self.assertIn(str(path), str(caught.exception))
        probe = probe_ledger(path)
        self.assertFalse(probe["ok"])
        self.assertIn(str(path), probe["error"])
        self.assertEqual(path.read_bytes()[:14], b"not a database")          # untouched

    def test_a_corrupt_advisory_register_is_refused_the_same_way(self):
        path = self.dir / "adv.db"
        path.write_bytes(b"garbage" * 200)
        with self.assertRaises(AdvisoryError):
            AdvisoryStore(path)
        probe = probe_advisory_store(path)
        self.assertFalse(probe["ok"])
        self.assertIn("cannot be opened", probe["error"])

    def test_the_default_paths_follow_the_state_dir(self):
        import importlib

        from src.utils import config

        with mock.patch.dict(os.environ, {"PORTWATCH_STATE_DIR": str(self.dir)}):
            importlib.reload(config)
            self.assertEqual(config.STATE_DIR, self.dir)
        importlib.reload(config)
        self.assertEqual(config.STATE_DIR, config.OUTPUTS_DIR if not os.environ.get("PORTWATCH_STATE_DIR")
                         else Path(os.environ["PORTWATCH_STATE_DIR"]))


class AssumptionJournalTests(unittest.TestCase):
    def setUp(self) -> None:
        self.dir = Path(tempfile.mkdtemp(prefix="pw-journal-"))
        self.journal = AssumptionJournal(self.dir / "cost_assumptions.jsonl")

    def test_round_trip_keeps_the_author_and_the_label(self):
        self.journal.append(assumption("charter_day", 41000, "USD", entered_by="ops", note="scenario A"))
        self.journal.append(assumption("bunker_price_t", 610, "USD", entered_by="ops", scope="INNSA"))
        rates = self.journal.load()
        self.assertEqual([r.primitive for r in rates], ["charter_day", "bunker_price_t"])
        self.assertTrue(all(r.is_assumption for r in rates))
        self.assertEqual(rates[0].provenance["enteredBy"], "ops")
        self.assertEqual(rates[0].provenance["note"], "scenario A")
        self.assertEqual(rates[1].scope, "INNSA")
        self.assertEqual(self.journal.probe()["counts"]["assumptions"], 2)

    def test_only_assumptions_are_journalled(self):
        with self.assertRaises(ValueError):
            self.journal.append(observation("bunker_price_t", 600, "USD", source="Ship & Bunker",
                                            observed_at="2026-09-15T00:00:00Z"))

    def test_a_clear_is_a_marker_and_a_restart_honours_it(self):
        self.journal.append(assumption("charter_day", 41000, "USD", entered_by="ops"))
        self.journal.clear("ops")
        self.assertEqual(self.journal.load(), [])
        self.journal.append(assumption("bunker_price_t", 600, "USD", entered_by="ops"))
        self.assertEqual([r.primitive for r in self.journal.load()], ["bunker_price_t"])
        lines = self.journal.path.read_text(encoding="utf-8").strip().splitlines()
        self.assertEqual(len(lines), 3)                                       # nothing rewritten

    def test_an_unreadable_line_fails_the_probe_with_its_line_number(self):
        self.journal.append(assumption("charter_day", 41000, "USD", entered_by="ops"))
        with self.journal.path.open("a", encoding="utf-8") as handle:
            handle.write("{not json\n")
        probe = self.journal.probe()
        self.assertFalse(probe["ok"])
        self.assertIn(":2:", probe["error"])
        with self.assertRaises(ValueError):
            self.journal.load()

    def test_the_engine_reloads_the_journal_on_start(self):
        from src.portwatch_os.decision import engine as engine_module

        self.journal.append(assumption("charter_day", 39000, "USD", entered_by="ops"))
        with mock.patch("src.portwatch_os.finance.basis.AssumptionJournal", return_value=self.journal):
            engine_module.reset_engine()
            try:
                engine = engine_module.get_engine()
                found = [r for r in engine.basis.rates if r.is_assumption and r.primitive == "charter_day"]
                self.assertEqual(len(found), 1)
                self.assertEqual(found[0].value, 39000.0)
                self.assertIs(engine.assumption_journal, self.journal)
            finally:
                engine_module.reset_engine()


class ApiTests(unittest.TestCase):
    """Through the API: a corrupt ledger is a 503, a foreign decision is served from the ledger."""

    @classmethod
    def setUpClass(cls) -> None:
        os.environ.setdefault("PORTWATCH_LICENCE_MODE", "DEMO")
        os.environ["PORTWATCH_FRESHNESS_SCHEDULER"] = "0"
        from fastapi.testclient import TestClient

        from backend.app.main import app

        # The 503 is produced by the app's Exception handler; Starlette's
        # ServerErrorMiddleware still re-raises after sending it, and the
        # test client would turn that into an exception here.
        cls.client = TestClient(app, raise_server_exceptions=False)

    def test_health_carries_the_durable_stores_and_their_probes(self):
        body = self.client.get("/api/health").json()
        stores = body["durableStores"]
        for key in ("stateDir", "stateDirSource", "ok", "ledger", "advisories", "costAssumptions", "ephemeral"):
            self.assertIn(key, stores)
        self.assertIn("path", stores["ledger"])
        self.assertIn("counts", stores["ledger"])

    def test_a_corrupt_ledger_is_a_503_that_names_the_file_and_substitutes_nothing(self):
        from src.portwatch_os.ledger import store as ledger_store

        corrupt = Path(tempfile.mkdtemp(prefix="pw-corrupt-")) / "portwatch_ledger.db"
        corrupt.write_bytes(b"nope" * 512)
        with mock.patch.object(ledger_store, "DEFAULT_LEDGER_PATH", corrupt):
            ledger_store.reset_default_ledger()
            from src.portwatch_os.decision import engine as engine_module

            engine_module.reset_engine()
            try:
                response = self.client.get("/api/decisions/problems?limit=5")
                self.assertEqual(response.status_code, 503, response.text)
                body = response.json()
                self.assertIn(str(corrupt), body["detail"])
                self.assertIn("substituted", body["remedy"])
                health = self.client.get("/api/health").json()
                self.assertFalse(health["durableStores"]["ledger"]["ok"])
                self.assertEqual(health["status"], "degraded")
            finally:
                engine_module.reset_engine()
                ledger_store.reset_default_ledger()
        self.assertEqual(corrupt.read_bytes()[:4], b"nope")

    def test_a_decision_from_another_process_is_served_from_the_ledger_read_only(self):
        from src.portwatch_os.decision.engine import get_engine

        engine = get_engine()
        problems = engine.ledger.decision_problems(limit=1) if engine.ledger is not None else []
        if not problems:
            self.skipTest("no decision problem in the ledger to restore")
        record = problems[0]
        engine.clear()                                   # as a restart leaves it
        response = self.client.get(f"/api/decisions/problems/{record.problem_id}")
        self.assertEqual(response.status_code, 200, response.text)
        body = response.json()
        self.assertTrue(body["restoredFromLedger"])
        self.assertEqual(body["workflow"], record.workflow)
        self.assertIn("recompute", body["restoredNote"])
        moved = self.client.post(f"/api/decisions/problems/{record.problem_id}/transition",
                                 json={"target": "REVIEWED"}, headers={"X-PortWatch-Actor": "qa"})
        self.assertEqual(moved.status_code, 409, moved.text)
        self.assertIn("recompute", moved.json()["detail"])
        listed = self.client.get("/api/decisions/problems?limit=50").json()
        self.assertIn(record.problem_id, {r["decisionId"] for r in listed["problems"]})
        self.assertGreaterEqual(listed["restoredFromLedger"], 1)

    def test_a_scoped_listing_finds_a_tenant_behind_other_tenants_newer_rows(self):
        """Forty newer rows belong to one carrier and one port; the five oldest
        to another carrier. Each caller lists its own, and only its own, from
        the ledger -- the page limit is not applied before the scope."""
        from src.portwatch_os.ledger import store as ledger_store
        from src.portwatch_os.ledger.schema import DecisionProblemRecord

        state = Path(tempfile.mkdtemp(prefix="pw-scoped-")) / "portwatch_ledger.db"
        ledger = ledger_store.SqliteLedgerStore(state)

        def write(index: int, domain: str, subject: str, actor: dict) -> None:
            problem = {"decisionId": f"dec-{index:03d}", "domain": domain, "actor": actor,
                       "subject": {"id": subject, "type": "vessel" if domain == "VESSEL_ROUTING" else "port"},
                       "options": [{"id": "keep"}]}
            ledger.record_decision_problem(DecisionProblemRecord(
                problem_id=problem["decisionId"], domain=domain, subject=subject, actor=actor["role"],
                issued_at=f"2026-09-01T{index // 60:02d}:{index % 60:02d}:00+00:00",
                world_state_id="ws-test", world_revision={"fingerprint": "t"}, at=None, problem=problem,
            ))

        company = lambda org: {"role": "SHIPPING_COMPANY", "organisation": org, "portCode": None, "vesselIds": []}
        port = {"role": "PORT_AUTHORITY", "organisation": None, "portCode": "INNSA", "vesselIds": []}
        for i in range(5):                                   # the oldest five: Small Carrier
            write(i, "VESSEL_ROUTING", f"SC-{i}", company("Small Carrier"))
        for i in range(5, 35):                               # thirty newer: Big Carrier
            write(i, "VESSEL_ROUTING", f"BC-{i}", company("Big Carrier"))
        for i in range(35, 45):                              # ten newest: the port's berth plans
            write(i, "PORT_BERTHING", "INNSA", port)
        ledger.close()

        with mock.patch.object(ledger_store, "DEFAULT_LEDGER_PATH", state):
            ledger_store.reset_default_ledger()
            from src.portwatch_os.decision import engine as engine_module

            engine_module.reset_engine()
            try:
                def listing(headers: dict, limit: int = 25) -> dict:
                    response = self.client.get(f"/api/decisions/problems?limit={limit}", headers=headers)
                    self.assertEqual(response.status_code, 200, response.text)
                    return response.json()

                small = listing({"X-PortWatch-Role": "SHIPPING_COMPANY", "X-PortWatch-Org": "small carrier "})
                self.assertEqual(sorted(r["decisionId"] for r in small["problems"]),
                                 [f"dec-{i:03d}" for i in range(5)])
                self.assertEqual(small["restoredFromLedger"], 5)

                big = listing({"X-PortWatch-Role": "SHIPPING_COMPANY", "X-PortWatch-Org": "Big Carrier"})
                self.assertEqual(len(big["problems"]), 25)
                self.assertTrue(all(r["actor"]["organisation"] == "Big Carrier" for r in big["problems"]))
                self.assertEqual(big["problems"][0]["decisionId"], "dec-034")      # newest first

                harbour = listing({"X-PortWatch-Role": "PORT_AUTHORITY", "X-PortWatch-Port": "INNSA"})
                self.assertEqual({r["domain"] for r in harbour["problems"]}, {"PORT_BERTHING"})
                self.assertEqual(len(harbour["problems"]), 10)

                other_port = listing({"X-PortWatch-Role": "PORT_AUTHORITY", "X-PortWatch-Port": "INMAA"})
                self.assertEqual(other_port["problems"], [])

                national = listing({"X-PortWatch-Role": "NATIONAL_ADMIN"}, limit=50)
                self.assertEqual(len(national["problems"]), 45)
                self.assertEqual(national["problems"][0]["decisionId"], "dec-044")
            finally:
                engine_module.reset_engine()
                ledger_store.reset_default_ledger()


if __name__ == "__main__":
    unittest.main()
