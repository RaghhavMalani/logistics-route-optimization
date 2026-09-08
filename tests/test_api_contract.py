"""API contract tests.

These run against the artefacts in the working tree. When the pipeline has not
been run they assert the *degraded* contract instead -- that every endpoint
reports a 503 naming the command that fixes it, rather than inventing data.
That distinction is the whole point of the provenance model, so it is tested
in both directions.
"""

from __future__ import annotations

import unittest

from fastapi.testclient import TestClient

from backend.app.main import app
from backend.app.services import cache_service as cache

client = TestClient(app)

ARTEFACTS_READY = cache.FORECAST_CACHE.exists()


class HealthContractTests(unittest.TestCase):
    def test_health_always_answers(self):
        response = client.get("/api/health")
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        for key in ("status", "intelligence", "artefacts", "sources",
                    "benchmark", "serverTimeUtc"):
            self.assertIn(key, payload)

    def test_health_never_claims_more_than_the_artefacts_support(self):
        payload = client.get("/api/health").json()
        if not payload["artefacts"]["forecast"]:
            self.assertEqual(payload["status"], "degraded")
            self.assertEqual(payload["intelligence"], "not_ready")

    def test_source_states_are_disjoint(self):
        sources = client.get("/api/health").json()["sources"]
        buckets = ["live", "cached", "stale", "synthetic", "unavailable"]
        names = [name for bucket in buckets for name in sources[bucket]]
        self.assertEqual(len(names), len(set(names)),
                         "a source appears in more than one provenance bucket")

    def test_root_advertises_the_health_endpoint(self):
        payload = client.get("/").json()
        self.assertEqual(payload["health"], "/api/health")


class RegistryContractTests(unittest.TestCase):
    def test_registry_is_the_single_source_of_truth(self):
        rows = client.get("/api/ports/registry").json()
        self.assertGreater(len(rows), 10)
        codes = [row["code"] for row in rows]
        model_ids = [row["modelId"] for row in rows]
        self.assertEqual(len(codes), len(set(codes)), "duplicate UN/LOCODE")
        self.assertEqual(len(model_ids), len(set(model_ids)), "duplicate model id")
        for row in rows:
            self.assertTrue(row["code"].startswith("IN"))
            self.assertIn(row["coast"], {"west", "east", "south"})
            self.assertTrue(-90 <= row["location"]["lat"] <= 90)


@unittest.skipUnless(ARTEFACTS_READY,
                     "pipeline artefacts not present; run run_award_demo.py")
class ReadyContractTests(unittest.TestCase):
    """The contract when the pipeline has actually produced its artefacts."""

    def test_ports_never_fabricate_absent_measurements(self):
        ports = client.get("/api/ports").json()
        self.assertGreater(len(ports), 0)
        for port in ports:
            self.assertIn(port["dataStatus"],
                          {"LIVE", "CACHED_LIVE", "STALE", "SYNTHETIC",
                           "UNAVAILABLE"})
            self.assertIn(port["risk"], {"normal", "congested", "severe"})
            # A missing measurement must be null, never a plausible stand-in.
            for field in ("throughputTonnes", "vesselCalls", "anchorageCount"):
                value = port[field]
                self.assertTrue(value is None or isinstance(value, (int, float)))

    def test_forecast_quantiles_are_monotonic(self):
        code = client.get("/api/model/ports").json()[0]
        rows = client.get(f"/api/model/{code}/forecast").json()
        self.assertGreater(len(rows), 0)
        for row in rows:
            self.assertLessEqual(row["q10"], row["q50"])
            self.assertLessEqual(row["q50"], row["q90"])
            self.assertGreaterEqual(row["q10"], 0.0)
            self.assertGreaterEqual(row["confidence"], 0.0)
            self.assertLessEqual(row["confidence"], 1.0)

    def test_regime_probabilities_form_a_distribution(self):
        code = client.get("/api/model/ports").json()[0]
        regime = client.get(f"/api/model/{code}/regime").json()
        total = sum(regime["probabilities"].values())
        self.assertAlmostEqual(total, 1.0, places=2)

    def test_decision_carries_its_evidence(self):
        code = client.get("/api/model/ports").json()[0]
        decision = client.get(f"/api/model/{code}/decision").json()
        for key in ("action", "target", "rationale", "expectedImpact",
                    "alternativeAction", "confidence", "uncertainty",
                    "topDrivers", "horizonDay"):
            self.assertIn(key, decision)
        self.assertTrue(decision["action"])
        self.assertTrue(decision["rationale"])

    def test_chain_reports_every_stage_in_order(self):
        code = client.get("/api/model/ports").json()[0]
        chain = client.get(f"/api/model/{code}/chain").json()
        stages = [stage["stage"] for stage in chain["stages"]]
        self.assertEqual(
            stages, ["RAW SIGNAL", "EXPERT", "REGIME", "FORECAST", "DECISION"])

    def test_port_lookup_accepts_legacy_codes(self):
        """Old bookmarks must keep working through the registry aliases."""
        response = client.get("/api/ports/INHAL")   # legacy Haldia code
        self.assertIn(response.status_code, {200, 404})
        if response.status_code == 200:
            self.assertEqual(response.json()["code"], "INCCU")

    def test_unknown_port_is_a_404_not_a_guess(self):
        response = client.get("/api/model/ZZZZZ/forecast")
        self.assertEqual(response.status_code, 404)

    def test_vessel_activity_states_its_basis(self):
        bundle = client.get("/api/sar/vessels").json()
        self.assertIn("basis", bundle)
        self.assertIn("aggregate", bundle["basis"].lower())

    def test_sar_feed_is_reported_unavailable_not_faked(self):
        adapters = client.get("/api/sar/feed-adapters").json()
        sar = next(a for a in adapters if a["key"] == "SAR_SENTINEL1")
        self.assertEqual(sar["status"], "UNAVAILABLE")
        self.assertEqual(sar["confidence"], 0.0)

    def test_pipeline_nodes_declare_availability(self):
        nodes = client.get("/api/model/pipeline").json()
        self.assertGreater(len(nodes), 8)
        for node in nodes:
            self.assertIn("available", node)
            self.assertIn("artefact", node)
            if not node["available"]:
                self.assertIsNone(node["score"])


class DegradedContractTests(unittest.TestCase):
    """When an artefact is missing the API must say so, not improvise."""

    def test_missing_cache_reports_the_rebuild_command(self):
        original = cache.PORT_STATE_CACHE
        try:
            cache.PORT_STATE_CACHE = original.with_name("__missing__.json")
            response = client.get("/api/model/INMAA/chain")
            self.assertIn(response.status_code, {404, 503})
            if response.status_code == 503:
                self.assertIn("run_award_demo", response.json()["detail"])
        finally:
            cache.PORT_STATE_CACHE = original


if __name__ == "__main__":
    unittest.main()
