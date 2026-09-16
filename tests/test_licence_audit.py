"""The licence registry, audited.

A licence registry is only worth anything if it refuses correctly, and the
refusals that matter most are the ones that feel pedantic: a source that is
probably fine, a source nobody has checked, a free tier of a product whose paid
tier is fine. Each of those is exactly where a production deployment ends up
built on a permission that turns out not to exist.

The tests below assert against the *evidence* recorded in the catalogue, so a
future change that relaxes a permission without re-reading the terms has to
change a test that quotes them.
"""

from __future__ import annotations

import unittest

from src.portwatch_os.fabric import (
    ALLOWED,
    COMMERCIAL,
    DEMO,
    GOVERNMENT,
    LicencePolicy,
    PROHIBITED,
    Provider,
    ProviderProduct,
    REQUIRES_REVIEW,
    RESEARCH,
    SignalFabric,
    TermsEvidence,
    UNKNOWN,
)
from src.portwatch_os.fabric.licence import LicenceError
from src.portwatch_os.fabric.model import AVAILABLE


def _product(product_id: str, policy: LicencePolicy, **kw) -> Provider:
    return Provider(
        provider_id=f"p-{product_id}", name=product_id.title(),
        products=(ProviderProduct(
            product_id=product_id, name=product_id, capabilities=("ais",),
            status=AVAILABLE, trust=0.9, policy=policy, **kw,
        ),),
    )


def _policy(**states) -> LicencePolicy:
    base = dict(
        commercial_use=ALLOWED, government_use=ALLOWED, redistribution=ALLOWED,
        attribution_required=False,
        evidence=TermsEvidence(checked_urls=(), reviewed_at="2026-09-12", finding="test"),
    )
    base.update(states)
    return LicencePolicy(**base)


class GlobalFishingWatchTests(unittest.TestCase):
    """Non-commercial by published terms, and the evidence is quoted."""

    def test_gfw_cannot_resolve_into_commercial_mode(self):
        resolution = SignalFabric(mode=COMMERCIAL).resolve("vessel_registry")
        self.assertFalse(resolution.available)
        self.assertIn("gfw-api", dict(resolution.rejected))

    def test_gfw_records_the_wording_it_rests_on(self):
        product = SignalFabric(mode=RESEARCH).product("gfw-api")
        self.assertEqual(product.policy.commercial_use, PROHIBITED)
        self.assertIn(
            "only available for non-commercial purposes",
            product.policy.evidence.finding,
        )
        self.assertTrue(product.policy.evidence.checked_urls)


class OpenMeteoTests(unittest.TestCase):
    """One provider, two products, opposite answers."""

    def test_the_free_endpoint_cannot_resolve_to_commercial(self):
        resolution = SignalFabric(mode=COMMERCIAL).resolve("marine")
        rejected = dict(resolution.rejected)
        self.assertIn("open-meteo-free", rejected)
        self.assertIn("prohibit", rejected["open-meteo-free"])

    def test_the_free_endpoint_quotes_its_terms(self):
        product = SignalFabric(mode=RESEARCH).product("open-meteo-free")
        self.assertEqual(product.policy.commercial_use, PROHIBITED)
        self.assertIn(
            "only use the free API services for non-commercial purposes",
            product.policy.evidence.finding,
        )
        self.assertEqual(product.policy.data_licence, "CC-BY 4.0")

    def test_the_commercial_product_is_eligible_when_configured(self):
        resolution = SignalFabric(mode=COMMERCIAL).resolve("marine")
        self.assertTrue(resolution.available)
        self.assertEqual(resolution.product.product_id, "open-meteo-customer")
        self.assertEqual(resolution.product.policy.commercial_use, ALLOWED)

    def test_research_prefers_the_free_endpoint(self):
        """Nothing is spent where nothing needs to be."""
        resolution = SignalFabric(mode=RESEARCH).resolve("marine")
        self.assertEqual(resolution.product.product_id, "open-meteo-free")

    def test_the_two_products_belong_to_one_provider(self):
        fabric = SignalFabric(mode=RESEARCH)
        provider = fabric.get("open-meteo")
        self.assertEqual(
            sorted(p.product_id for p in provider.products),
            ["open-meteo-customer", "open-meteo-free"],
        )


class AisStreamTests(unittest.TestCase):
    """Follows the evidence: no terms were found, so nothing is asserted."""

    def test_aisstream_is_requires_review_not_prohibited(self):
        product = SignalFabric(mode=RESEARCH).product("aisstream-websocket")
        self.assertEqual(product.policy.commercial_use, REQUIRES_REVIEW)
        self.assertNotEqual(product.policy.commercial_use, PROHIBITED)

    def test_aisstream_records_what_was_checked_and_that_it_said_nothing(self):
        product = SignalFabric(mode=RESEARCH).product("aisstream-websocket")
        evidence = product.policy.evidence
        self.assertGreaterEqual(len(evidence.checked_urls), 3)
        self.assertIn("No terms of use", evidence.finding)
        self.assertIsNone(evidence.terms_url)

    def test_aisstream_is_refused_for_commercial_because_unverified(self):
        resolution = SignalFabric(mode=COMMERCIAL).resolve("ais")
        reason = dict(resolution.rejected)["aisstream-websocket"]
        self.assertIn("requires review", reason)
        self.assertIn("not a permission", reason)

    def test_aisstream_serves_research_and_demo(self):
        for mode in (RESEARCH, DEMO):
            self.assertEqual(
                SignalFabric(mode=mode).resolve("ais").product.product_id,
                "aisstream-websocket",
                mode,
            )


class UnverifiedPermissionTests(unittest.TestCase):
    """Neither REQUIRES_REVIEW nor UNKNOWN is a yes."""

    def test_requires_review_cannot_silently_resolve_for_commercial(self):
        fabric = SignalFabric(
            [_product("maybe", _policy(commercial_use=REQUIRES_REVIEW))],
            mode=COMMERCIAL,
        )
        resolution = fabric.resolve("ais")
        self.assertFalse(resolution.available)
        self.assertIn("requires review", dict(resolution.rejected)["maybe"])

    def test_unknown_cannot_silently_resolve_for_commercial(self):
        fabric = SignalFabric(
            [_product("unchecked", _policy(commercial_use=UNKNOWN))],
            mode=COMMERCIAL,
        )
        resolution = fabric.resolve("ais")
        self.assertFalse(resolution.available)
        self.assertIn("nobody has checked", dict(resolution.rejected)["unchecked"])

    def test_unknown_still_serves_research(self):
        """Research is where you find out. Refusing it would be circular."""
        fabric = SignalFabric(
            [_product("unchecked", _policy(commercial_use=UNKNOWN))],
            mode=RESEARCH,
        )
        self.assertTrue(fabric.resolve("ais").available)

    def test_government_needs_both_use_and_redistribution(self):
        fabric = SignalFabric(
            [_product("half", _policy(government_use=ALLOWED, redistribution=REQUIRES_REVIEW))],
            mode=GOVERNMENT,
        )
        resolution = fabric.resolve("ais")
        self.assertFalse(resolution.available)
        self.assertIn("redistribution", dict(resolution.rejected)["half"])

    def test_a_permission_outside_the_four_states_is_refused(self):
        with self.assertRaises(LicenceError):
            _policy(commercial_use="probably")


class EvidenceTests(unittest.TestCase):
    """Every policy in the catalogue carries a reviewed date and a finding."""

    def test_every_product_carries_evidence(self):
        for product in SignalFabric(mode=RESEARCH).products():
            evidence = product.policy.evidence
            self.assertTrue(evidence.reviewed_at, product.product_id)
            self.assertTrue(evidence.finding, product.product_id)

    def test_every_prohibition_quotes_the_terms_it_rests_on(self):
        """A prohibition without wording cannot be re-verified when terms change."""
        for product in SignalFabric(mode=RESEARCH).products():
            if product.policy.commercial_use == PROHIBITED:
                self.assertTrue(
                    product.policy.evidence.checked_urls,
                    f"{product.product_id} prohibits commercial use with no URL checked",
                )
                self.assertIn('"', product.policy.evidence.finding, product.product_id)

    def test_the_licence_surface_is_four_state_on_the_wire(self):
        payload = SignalFabric(mode=RESEARCH).product("aisstream-websocket").to_dict()
        self.assertEqual(payload["policy"]["commercialUse"], REQUIRES_REVIEW)
        self.assertIn("evidence", payload["policy"])
        self.assertEqual(payload["policy"]["evidence"]["reviewedAt"], "2026-09-12")


if __name__ == "__main__":
    unittest.main()
