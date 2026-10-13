import os
import tempfile
import unittest
from datetime import timedelta
from pathlib import Path
from unittest.mock import patch

from fastapi import HTTPException
from fastapi.testclient import TestClient
from backend.app.auth_store import AuthStore, get_auth_store
from backend.app.identity import identity_mode
from backend.app.main import app
from src.portwatch_os.clock import wall_now


class VerifiedIdentityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.template = tempfile.TemporaryDirectory()
        cls.template_path = Path(cls.template.name)/"identity.db"
        cls.password = "test-only-verified-password"
        AuthStore(cls.template_path).provision("port@test.invalid", cls.password, role="PORT_AUTHORITY",
                                             display_name="Port Controller", ports=("JNPT",))

    @classmethod
    def tearDownClass(cls):
        cls.template.cleanup()

    def setUp(self):
        import shutil
        self.tmp = tempfile.TemporaryDirectory()
        self.store = AuthStore(Path(self.tmp.name)/"identity.db")
        shutil.copyfile(self.template_path, self.store.path)
        self.patch = patch("backend.app.auth_store.get_auth_store", return_value=self.store)
        self.patch.start()
        self.mode = patch.dict(os.environ, {"PORTWATCH_IDENTITY_MODE": "verified"})
        self.mode.start()
        app.dependency_overrides[get_auth_store] = lambda: self.store
        self.client = TestClient(app)

    def tearDown(self):
        self.client.close()
        self.patch.stop()
        self.mode.stop()
        app.dependency_overrides.pop(get_auth_store, None)
        self.tmp.cleanup()

    def login(self):
        response = self.client.post("/api/auth/login", json={"email": "port@test.invalid", "password": self.password})
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.headers["cache-control"], "no-store")
        return response.json()

    def test_default_and_unknown_modes_fail_closed(self):
        with patch.dict(os.environ, {}, clear=True):
            self.assertEqual(identity_mode(), "verified")
        with patch.dict(os.environ, {"PORTWATCH_IDENTITY_MODE": "typo"}):
            self.assertEqual(identity_mode(), "verified")
        self.assertEqual(self.client.get("/api/auth/session", headers={"X-PortWatch-Role": "NATIONAL_ADMIN"}).status_code, 401)

    def test_verified_workflow_preserves_unicode_membership_and_ignores_claims(self):
        from backend.app.identity import Identity, current_identity, may_see_decision
        from backend.app.routes.decisions import _actor
        from backend.app.routes.advisories import principal_from_request
        who = Identity(role="SHIPPING_COMPANY", actor="server-id", organisation="Shipping — भारत", verified=True)
        token = current_identity.set(who)
        try:
            actor = _actor("NATIONAL_ADMIN", "forged organisation", "INMAA", "forged-vessel")
            self.assertEqual(actor.organisation, who.organisation)
            self.assertTrue(may_see_decision(who, actor.to_dict(), {}, "VESSEL_ROUTING"))
            principal = principal_from_request("forged actor", "NATIONAL_ADMIN", "INMAA", "forged organisation", None)
            self.assertEqual(principal.actor, who.actor)
            self.assertEqual(principal.organisation, who.organisation)
            self.assertFalse(principal.is_admin)
        finally:
            current_identity.reset(token)

    def test_login_session_and_logout_use_server_membership_and_revoke_token(self):
        session = self.login()
        headers = {"Authorization": "Bearer "+session["accessToken"], "X-PortWatch-Role": "NATIONAL_ADMIN", "X-PortWatch-Port": "INMAA"}
        verified = self.client.get("/api/auth/session", headers=headers)
        self.assertEqual(verified.json()["user"]["role"], "PORT_AUTHORITY")
        self.assertEqual(verified.json()["user"]["portCodes"], ["INNSA"])
        self.assertEqual(self.client.get("/api/admin/diagnostics", headers=headers).status_code, 403)
        self.assertEqual(self.client.post("/api/auth/logout", headers=headers).status_code, 204)
        self.assertEqual(self.client.get("/api/auth/session", headers=headers).status_code, 401)

    def test_expired_idle_and_disabled_sessions_are_refused(self):
        for field in ("expires_at", "last_seen", "enabled"):
            session = self.store.login("port@test.invalid", self.password, "test")
            conn = self.store._open()
            with conn:
                if field == "enabled":
                    conn.execute("UPDATE accounts SET enabled=0")
                else:
                    conn.execute(f"UPDATE sessions SET {field}=0")
            conn.close()
            with self.assertRaises(HTTPException) as caught:
                self.store.session(session["accessToken"])
            self.assertEqual(caught.exception.status_code, 401)

    def test_passwords_and_tokens_are_never_stored_in_plaintext(self):
        session = self.login()
        data = self.store.path.read_bytes()
        self.assertNotIn(self.password.encode(), data)
        self.assertNotIn(session["accessToken"].encode(), data)

    def test_invalid_credentials_are_generic_and_rate_limited(self):
        for attempt in range(6):
            response = self.client.post("/api/auth/login", json={"email": "unknown@test.invalid", "password": "incorrect"})
            self.assertEqual(response.status_code, 401 if attempt < 5 else 429, response.text)
        self.assertEqual(response.headers["retry-after"], "900")

    def test_client_cannot_assign_role_or_ports_at_login(self):
        response = self.client.post("/api/auth/login", json={"email": "port@test.invalid", "password": self.password,
                                                          "role": "NATIONAL_ADMIN", "portCodes": ["INMAA"]})
        self.assertEqual(response.status_code, 422)

    def test_account_update_revokes_prior_sessions(self):
        old = self.login()
        self.store.provision("port@test.invalid", self.password, role="PORT_AUTHORITY", display_name="Updated", ports=("INMAA",))
        self.assertEqual(self.client.get("/api/auth/session", headers={"Authorization": "Bearer "+old["accessToken"]}).status_code, 401)
        self.assertEqual(self.login()["user"]["portCodes"], ["INMAA"])

    def test_password_reset_during_verification_cannot_mint_a_new_session(self):
        from backend.app.auth_store import password_hash
        def reset_during_hash(password, salt):
            result = password_hash(password, salt)
            conn = self.store._open()
            with conn:
                conn.execute("UPDATE accounts SET password_hash=?", ("0"*64,))
            conn.close()
            return result
        with patch("backend.app.auth_store.password_hash", side_effect=reset_during_hash):
            response = self.client.post("/api/auth/login", json={"email": "port@test.invalid", "password": self.password})
        self.assertEqual(response.status_code, 401)

    def test_auth_expiry_is_independent_of_replay_clock(self):
        session = self.login()
        # wall-clock: make authentication's expiry move forward even if replay moves back.
        with patch("backend.app.auth_store.wall_now", return_value=wall_now()+timedelta(hours=9)):
            response = self.client.get("/api/auth/session", headers={"Authorization": "Bearer "+session["accessToken"]})
        self.assertEqual(response.status_code, 401)

    def test_cors_preflight_does_not_require_identity(self):
        response = self.client.options("/api/auth/session", headers={"Origin": "http://localhost:4173", "Access-Control-Request-Method": "GET"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers["access-control-allow-origin"], "http://localhost:4173")

    def test_corrupt_identity_store_is_reported_and_sessions_survive_reopen(self):
        session = self.login()
        reopened = AuthStore(self.store.path)
        self.assertTrue(reopened.probe()["configured"])
        self.assertEqual(reopened.session(session["accessToken"])["user"]["portCode"], "INNSA")
        self.store.path.write_bytes(b"corrupt identity fixture")
        self.assertFalse(reopened.probe()["ok"])

    def test_identity_refusals_are_readable_by_allowed_cross_origin_frontend(self):
        response = self.client.get("/api/auth/session", headers={"Origin": "http://localhost:4173"})
        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.headers["access-control-allow-origin"], "http://localhost:4173")
