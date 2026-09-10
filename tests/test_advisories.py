"""The advisory workflow and its authorisation boundary.

This is the module where a mistake reaches a ship, so almost every test here
asserts that something is *refused*: a draft the recipient can see, a controller
accepting on the vessel's behalf, a transition with no recorded reason. The
happy path is one test; the boundary is the rest.
"""

from __future__ import annotations

import unittest

from src.portwatch_os.advisories.model import (
    ACCEPTED,
    ACKNOWLEDGED,
    ADVISORY_KINDS,
    COMPLETED,
    DECLINED,
    DRAFT,
    EXPIRED,
    ISSUED,
    ISSUER,
    QUERIED,
    RECIPIENT,
    REJECTED,
    SYSTEM,
    TERMINAL_STATES,
    UNDER_REVIEW,
    WITHDRAWN,
    Advisory,
    AdvisoryError,
    allowed_transitions,
    expire_due,
    modify,
    transition,
    utc_now,
)
from src.portwatch_os.advisories.store import (
    AdvisoryStore,
    AuthorisationError,
    Principal,
    ascii_fold,
)

COMPANY = "PortWatch Demo Shipping"
PORT_ORG = "Chennai Port Authority — Control Room"


def advisory(**overrides) -> Advisory:
    base = dict(
        advisory_id="ADV-INMAA-TEST01",
        kind="arrival_window",
        port_code="INMAA",
        issuer="PortWatch decision engine",
        issuer_organisation=PORT_ORG,
        recipient_vessel_id="PWD-001",
        recipient_vessel_name="MV Konkan",
        recipient_organisation=COMPANY,
        created_at=utc_now(),
        recommendation={"recommendedArrival": "2026-09-10T18:30:00+00:00"},
        reason=(
            "Berth B4 frees at 18:10 and the queue clears by 18:30; arriving at "
            "13:30 costs about 4.6 h at anchor."
        ),
        model_confidence=0.78,
        evidence={"expectedWaitReductionHours": 4.6},
    )
    base.update(overrides)
    return Advisory(**base)


def controller(port="INMAA", actor="S. Iyer") -> Principal:
    return Principal(actor=actor, role=ISSUER, port_code=port)


def master(actor="R. Nayar", vessels=("PWD-001",)) -> Principal:
    return Principal(
        actor=actor, role=RECIPIENT, organisation=COMPANY, vessel_ids=list(vessels)
    )


class StateMachineTests(unittest.TestCase):
    def test_a_draft_cannot_be_issued_without_review(self):
        """The human step is a transition, not a convention."""
        record = advisory()
        with self.assertRaises(AdvisoryError) as caught:
            transition(record, ISSUED, actor="S. Iyer", actor_role=ISSUER)
        self.assertIn("not a legal advisory transition", str(caught.exception))

    def test_the_error_names_what_is_available_instead(self):
        record = advisory()
        with self.assertRaises(AdvisoryError) as caught:
            transition(record, ACCEPTED, actor="S. Iyer", actor_role=ISSUER)
        self.assertIn("under_review", str(caught.exception))

    def test_an_issuer_cannot_accept_on_the_recipients_behalf(self):
        record = advisory()
        transition(record, UNDER_REVIEW, actor="S. Iyer", actor_role=ISSUER)
        transition(record, ISSUED, actor="S. Iyer", actor_role=ISSUER)
        with self.assertRaises(AdvisoryError) as caught:
            transition(record, ACCEPTED, actor="S. Iyer", actor_role=ISSUER)
        self.assertIn("reserved for the recipient", str(caught.exception))

    def test_a_recipient_cannot_issue(self):
        record = advisory()
        with self.assertRaises(AdvisoryError):
            transition(record, UNDER_REVIEW, actor="R. Nayar", actor_role=RECIPIENT)

    def test_a_rejection_must_record_a_reason(self):
        record = advisory()
        transition(record, UNDER_REVIEW, actor="S. Iyer", actor_role=ISSUER)
        with self.assertRaises(AdvisoryError) as caught:
            transition(record, REJECTED, actor="S. Iyer", actor_role=ISSUER)
        self.assertIn("must record a reason", str(caught.exception))

    def test_declining_is_a_normal_terminal_state(self):
        record = advisory()
        transition(record, UNDER_REVIEW, actor="S. Iyer", actor_role=ISSUER)
        transition(record, ISSUED, actor="S. Iyer", actor_role=ISSUER)
        transition(
            record, DECLINED, actor="R. Nayar", actor_role=RECIPIENT,
            reason="master's discretion given the sea state on the approach",
        )
        self.assertIn(record.state, TERMINAL_STATES)
        self.assertTrue(record.is_terminal)

    def test_every_transition_names_an_actor(self):
        record = advisory()
        with self.assertRaises(AdvisoryError):
            transition(record, UNDER_REVIEW, actor="", actor_role=ISSUER)

    def test_the_full_happy_path_runs(self):
        record = advisory()
        transition(record, UNDER_REVIEW, actor="S. Iyer", actor_role=ISSUER)
        transition(record, ISSUED, actor="S. Iyer", actor_role=ISSUER)
        transition(record, ACKNOWLEDGED, actor="R. Nayar", actor_role=RECIPIENT)
        transition(record, ACCEPTED, actor="R. Nayar", actor_role=RECIPIENT)
        transition(record, COMPLETED, actor="S. Iyer", actor_role=ISSUER)
        self.assertEqual(record.state, COMPLETED)
        self.assertEqual(len(record.audit), 5)

    def test_the_audit_trail_records_who_when_and_why(self):
        record = advisory()
        transition(record, UNDER_REVIEW, actor="S. Iyer", actor_role=ISSUER)
        transition(
            record, REJECTED, actor="S. Iyer", actor_role=ISSUER,
            reason="pilot unavailable in the recommended window",
        )
        last = record.audit[-1]
        self.assertEqual(last.actor, "S. Iyer")
        self.assertEqual(last.actor_role, ISSUER)
        self.assertIn("pilot", last.reason)
        self.assertTrue(last.at)

    def test_only_the_clock_may_expire_an_advisory(self):
        record = advisory(valid_until="2020-01-01T00:00:00+00:00")
        transition(record, UNDER_REVIEW, actor="S. Iyer", actor_role=ISSUER)
        transition(record, ISSUED, actor="S. Iyer", actor_role=ISSUER)
        # A caller cannot claim the SYSTEM role through the store; the model
        # allows it only so the clock can drive it.
        expired = expire_due([record], now=utc_now())
        self.assertEqual(len(expired), 1)
        self.assertEqual(record.state, EXPIRED)
        self.assertEqual(record.audit[-1].actor_role, SYSTEM)

    def test_an_advisory_within_its_validity_is_not_expired(self):
        record = advisory(valid_until="2099-01-01T00:00:00+00:00")
        transition(record, UNDER_REVIEW, actor="S. Iyer", actor_role=ISSUER)
        transition(record, ISSUED, actor="S. Iyer", actor_role=ISSUER)
        self.assertEqual(expire_due([record], now=utc_now()), [])

    def test_available_transitions_are_filtered_by_role(self):
        record = advisory()
        transition(record, UNDER_REVIEW, actor="S. Iyer", actor_role=ISSUER)
        transition(record, ISSUED, actor="S. Iyer", actor_role=ISSUER)
        recipient_options = {t.target for t in allowed_transitions(record.state, RECIPIENT)}
        self.assertIn(ACCEPTED, recipient_options)
        self.assertNotIn(WITHDRAWN, recipient_options)


class ValidationTests(unittest.TestCase):
    def test_an_advisory_must_carry_the_field_its_kind_requires(self):
        record = advisory(recommendation={"somethingElse": 1})
        problems = record.validate()
        self.assertTrue(any("recommendedArrival" in p for p in problems))

    def test_an_advisory_must_carry_a_reason_a_master_can_evaluate(self):
        self.assertTrue(any("reason" in p for p in advisory(reason="no").validate()))

    def test_an_unknown_kind_is_refused(self):
        self.assertTrue(any("unknown advisory kind" in p for p in advisory(kind="vibes").validate()))

    def test_every_kind_declares_what_it_must_carry(self):
        for spec in ADVISORY_KINDS.values():
            self.assertTrue(spec.required_field)
            self.assertTrue(spec.description)


class ModificationTests(unittest.TestCase):
    def test_a_controller_edit_keeps_the_original(self):
        """"The model said 18:30 and the controller made it 19:15" is a signal."""
        record = advisory()
        transition(record, UNDER_REVIEW, actor="S. Iyer", actor_role=ISSUER)
        modify(
            record, {"recommendedArrival": "2026-09-10T19:15:00+00:00"},
            actor="S. Iyer", reason="pilot availability at 18:30 is tight",
        )
        self.assertEqual(
            record.modified_from["recommendedArrival"], "2026-09-10T18:30:00+00:00"
        )
        self.assertEqual(
            record.recommendation["recommendedArrival"], "2026-09-10T19:15:00+00:00"
        )

    def test_an_issued_advisory_cannot_be_edited_in_place(self):
        record = advisory()
        transition(record, UNDER_REVIEW, actor="S. Iyer", actor_role=ISSUER)
        transition(record, ISSUED, actor="S. Iyer", actor_role=ISSUER)
        with self.assertRaises(AdvisoryError) as caught:
            modify(record, {"recommendedArrival": "x"}, actor="S. Iyer", reason="oops")
        self.assertIn("withdraw it and", str(caught.exception))

    def test_a_modification_must_record_why(self):
        record = advisory()
        with self.assertRaises(AdvisoryError):
            modify(record, {"recommendedArrival": "x"}, actor="S. Iyer", reason="")


class VisibilityTests(unittest.TestCase):
    def setUp(self):
        self.store = AdvisoryStore(":memory:")
        self.record = self.store.create(advisory(), principal=controller())

    def test_a_draft_is_invisible_to_its_recipient(self):
        """Without this the human approval step is theatre."""
        self.assertFalse(self.record.visible_to_recipient)
        self.assertFalse(master().may_see(self.record))

    def test_the_issuing_controller_sees_their_own_draft(self):
        self.assertTrue(controller().may_see(self.record))

    def test_a_controller_at_another_port_does_not_see_it(self):
        self.assertFalse(controller(port="INNSA").may_see(self.record))

    def test_the_recipient_sees_it_once_it_is_issued(self):
        self.store.act(self.record.advisory_id, UNDER_REVIEW, principal=controller())
        issued = self.store.act(self.record.advisory_id, ISSUED, principal=controller())
        self.assertTrue(master().may_see(issued))

    def test_another_carrier_never_sees_it(self):
        self.store.act(self.record.advisory_id, UNDER_REVIEW, principal=controller())
        issued = self.store.act(self.record.advisory_id, ISSUED, principal=controller())
        other = Principal(
            actor="Someone Else", role=RECIPIENT, organisation="Other Line Ltd",
        )
        self.assertFalse(other.may_see(issued))

    def test_a_recipient_view_hides_the_ports_internal_review_trail(self):
        self.store.act(self.record.advisory_id, UNDER_REVIEW, principal=controller())
        issued = self.store.act(self.record.advisory_id, ISSUED, principal=controller())
        states = {e["to_state"] for e in issued.to_dict(for_recipient=True)["audit"]}
        self.assertNotIn(DRAFT, states)
        self.assertNotIn(UNDER_REVIEW, states)

    def test_national_command_sees_everything(self):
        admin = Principal(actor="A. Deshmukh", role=ISSUER, is_admin=True)
        self.assertTrue(admin.may_see(self.record))


class AuthorisationTests(unittest.TestCase):
    def setUp(self):
        self.store = AdvisoryStore(":memory:")
        self.record = self.store.create(advisory(), principal=controller())

    def test_a_store_always_lands_a_new_advisory_in_draft(self):
        """A payload claiming to be ISSUED must not skip the workflow."""
        forced = advisory(advisory_id="ADV-INMAA-FORCED", state=ISSUED)
        stored = self.store.create(forced, principal=controller())
        self.assertEqual(stored.state, DRAFT)

    def test_a_malformed_advisory_is_refused_by_the_store(self):
        with self.assertRaises(AdvisoryError):
            self.store.create(
                advisory(advisory_id="ADV-BAD", recommendation={}), principal=controller()
            )

    def test_a_controller_cannot_act_on_another_ports_advisory(self):
        with self.assertRaises(AuthorisationError):
            self.store.act(
                self.record.advisory_id, UNDER_REVIEW, principal=controller(port="INNSA")
            )

    def test_a_carrier_cannot_respond_to_another_carriers_advisory(self):
        self.store.act(self.record.advisory_id, UNDER_REVIEW, principal=controller())
        self.store.act(self.record.advisory_id, ISSUED, principal=controller())
        other = Principal(actor="X", role=RECIPIENT, organisation="Other Line Ltd")
        with self.assertRaises(AuthorisationError):
            self.store.act(self.record.advisory_id, ACCEPTED, principal=other)

    def test_a_principal_cannot_claim_the_system_role(self):
        with self.assertRaises(AuthorisationError):
            Principal(actor="clock", role=SYSTEM)

    def test_a_principal_must_be_named(self):
        with self.assertRaises(AuthorisationError):
            Principal(actor="", role=ISSUER)

    def test_a_carrier_matches_on_organisation_when_it_names_no_vessels(self):
        """A fleet desk has authority over the organisation, not one hull."""
        self.store.act(self.record.advisory_id, UNDER_REVIEW, principal=controller())
        self.store.act(self.record.advisory_id, ISSUED, principal=controller())
        desk = Principal(actor="M. Fernandes", role=RECIPIENT, organisation=COMPANY)
        accepted = self.store.act(
            self.record.advisory_id, ACCEPTED, principal=desk
        )
        self.assertEqual(accepted.state, ACCEPTED)

    def test_an_ascii_folded_organisation_still_matches(self):
        """An em-dash cannot survive an HTTP header, so both sides fold."""
        self.assertEqual(
            ascii_fold("Chennai Port Authority — Control Room"),
            "Chennai Port Authority - Control Room",
        )
        record = self.store.create(
            advisory(advisory_id="ADV-FOLD", recipient_organisation=PORT_ORG),
            principal=controller(),
        )
        self.store.act(record.advisory_id, UNDER_REVIEW, principal=controller())
        self.store.act(record.advisory_id, ISSUED, principal=controller())
        folded = Principal(
            actor="S. Iyer", role=RECIPIENT,
            organisation="Chennai Port Authority - Control Room",
        )
        self.assertTrue(folded.may_see(self.store.require(record.advisory_id)))

    def test_the_register_survives_a_round_trip(self):
        self.store.act(self.record.advisory_id, UNDER_REVIEW, principal=controller())
        reloaded = self.store.require(self.record.advisory_id)
        self.assertEqual(reloaded.state, UNDER_REVIEW)
        self.assertEqual(len(reloaded.audit), 2)
        self.assertEqual(
            reloaded.recommendation["recommendedArrival"],
            "2026-09-10T18:30:00+00:00",
        )

    def test_expiry_takes_no_caller_identity(self):
        record = self.store.create(
            advisory(advisory_id="ADV-EXP", valid_until="2020-01-01T00:00:00+00:00"),
            principal=controller(),
        )
        self.store.act(record.advisory_id, UNDER_REVIEW, principal=controller())
        self.store.act(record.advisory_id, ISSUED, principal=controller())
        expired = self.store.expire_due()
        self.assertEqual([a.advisory_id for a in expired], [record.advisory_id])

    def test_counts_report_the_register_by_state(self):
        self.assertEqual(self.store.counts(controller()), {DRAFT: 1})


class ScopeTests(unittest.TestCase):
    """A principal that names no scope is not a principal.

    Every authorisation check in the store compares the advisory against the
    principal's scope. A principal carrying no scope therefore passed every
    comparison vacuously, which is how an unscoped issuer came to see -- and act
    on -- every port's traffic.
    """

    def test_an_issuer_must_name_the_port_it_controls(self):
        with self.assertRaises(AuthorisationError):
            Principal(actor="S. Iyer", role=ISSUER)

    def test_a_recipient_must_name_an_organisation_or_a_vessel(self):
        with self.assertRaises(AuthorisationError):
            Principal(actor="R. Nayar", role=RECIPIENT)

    def test_national_command_is_the_only_unscoped_principal(self):
        admin = Principal(actor="A. Deshmukh", role=ISSUER, is_admin=True)
        self.assertTrue(admin.is_admin)


class VisibilityBudgetTests(unittest.TestCase):
    """The caller's limit counts rows the caller may see."""

    def setUp(self):
        self.store = AdvisoryStore(":memory:")
        # One advisory for our carrier, buried under newer traffic belonging to
        # other ports that this recipient is not entitled to.
        self.store.create(
            advisory(advisory_id="ADV-MINE"), principal=controller(),
        )
        self.store.act("ADV-MINE", UNDER_REVIEW, principal=controller())
        self.store.act("ADV-MINE", ISSUED, principal=controller())
        for n in range(25):
            other_port = f"INX{n:02d}"
            self.store.create(
                advisory(advisory_id=f"ADV-OTHER-{n}", port_code=other_port),
                principal=controller(port=other_port),
            )

    def test_an_authorised_advisory_is_not_squeezed_out_by_traffic(self):
        rows = self.store.visible_to(master(), limit=5)
        self.assertEqual([a.advisory_id for a in rows], ["ADV-MINE"])

    def test_counts_describe_only_the_authorised_population(self):
        self.assertEqual(self.store.counts(master()), {ISSUED: 1})

    def test_a_recipient_cannot_read_another_ports_audit_trail(self):
        with self.assertRaises(AuthorisationError):
            self.store.audit_trail("ADV-OTHER-0", master())

    def test_a_recipient_reads_the_trail_of_its_own_advisory(self):
        trail = self.store.audit_trail("ADV-MINE", master())
        self.assertTrue(trail)


if __name__ == "__main__":
    unittest.main()
