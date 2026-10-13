"""Server-owned accounts and revocable opaque sessions. No public provisioning API."""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import secrets
import sqlite3
import uuid
from threading import BoundedSemaphore
from datetime import timedelta
from pathlib import Path

from fastapi import HTTPException

from src.portwatch_os.clock import wall_now
from src.portwatch_os.ledger.store import LedgerError
from src.portwatch_os.roles import PORT_AUTHORITY, is_workspace_role
from src.utils import port_registry
from src.utils.config import STATE_DIR

_PASSWORD_SLOTS = BoundedSemaphore(2)


def password_hash(password: str, salt: bytes) -> str:
    # OWASP scrypt minimum: N=2**17, r=8, p=1; explicit OpenSSL memory ceiling.
    with _PASSWORD_SLOTS:
        return hashlib.scrypt(password.encode(), salt=salt, n=2**17, r=8, p=1,
                              maxmem=256*1024*1024, dklen=32).hex()


class AuthStore:
    def __init__(self, path: Path | None = None):
        self.path = path or Path(os.getenv("PORTWATCH_AUTH_DB") or STATE_DIR / "identity.db")

    def _open(self):
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            conn = sqlite3.connect(self.path, timeout=10)
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA foreign_keys=ON")
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS accounts (
                    id TEXT PRIMARY KEY, email TEXT UNIQUE NOT NULL, salt TEXT NOT NULL,
                    password_hash TEXT NOT NULL, profile TEXT NOT NULL, enabled INTEGER NOT NULL);
                CREATE TABLE IF NOT EXISTS sessions (
                    token_hash TEXT PRIMARY KEY, account_id TEXT NOT NULL REFERENCES accounts(id),
                    issued_at REAL NOT NULL, expires_at REAL NOT NULL, last_seen REAL NOT NULL);
                CREATE TABLE IF NOT EXISTS login_attempts (scope TEXT NOT NULL, at REAL NOT NULL);
                CREATE INDEX IF NOT EXISTS attempts_scope ON login_attempts(scope, at);
            """)
            return conn
        except (OSError, sqlite3.DatabaseError) as exc:
            if "conn" in locals():
                conn.close()
            raise LedgerError("identity store cannot be opened") from exc

    def provision(self, email: str, password: str, *, role: str, display_name: str,
                  ports: tuple[str, ...] = (), organisation: str = "", vessel_ids: tuple[str, ...] = ()) -> dict:
        if not is_workspace_role(role) or len(password) < 12 or len(password) > 256:
            raise ValueError("use a workspace role and a password of 12–256 characters")
        if not email.strip() or "@" not in email or not display_name.strip():
            raise ValueError("email and display name are required")
        members = []
        for code in ports:
            port = port_registry.resolve(code)
            if port is None:
                raise ValueError(f"port is not registered: {code}")
            if port.locode not in members:
                members.append(port.locode)
        if role == PORT_AUTHORITY and not members:
            raise ValueError("port authority accounts require server-assigned port membership")
        salt = secrets.token_bytes(16)
        hashed = password_hash(password, salt)
        conn = self._open()
        try:
            with conn:
                old = conn.execute("SELECT id FROM accounts WHERE email=?", (email.strip().lower(),)).fetchone()
                account_id = old[0] if old else str(uuid.uuid4())
                profile = {"id": account_id, "email": email.strip().lower(), "displayName": display_name.strip(),
                           "role": role, "portCode": members[0] if members else None, "portCodes": members,
                           "organisation": organisation, "companyId": organisation or None, "vesselIds": list(vessel_ids)}
                conn.execute("INSERT INTO accounts VALUES (?,?,?,?,?,1) ON CONFLICT(id) DO UPDATE SET "
                             "salt=excluded.salt,password_hash=excluded.password_hash,profile=excluded.profile,enabled=1",
                             (account_id, profile["email"], salt.hex(), hashed, json.dumps(profile)))
                conn.execute("DELETE FROM sessions WHERE account_id=?", (account_id,))
                return profile
        finally:
            conn.close()

    def login(self, email: str, password: str, address: str) -> dict:
        # wall-clock: credential throttling and session expiry cannot follow replay time.
        now = wall_now()
        stamp = now.timestamp()
        email = email.strip().lower()
        # Hash keys so the throttle table does not expose unknown submitted email addresses.
        account_scope = "account:" + hashlib.sha256(email.encode()).hexdigest()
        address_scope = "address:" + hashlib.sha256(address.encode()).hexdigest()
        conn = self._open()
        try:
            with conn:
                conn.execute("BEGIN IMMEDIATE")
                conn.execute("DELETE FROM login_attempts WHERE at<?", (stamp-900,))
                conn.execute("DELETE FROM sessions WHERE expires_at<=? OR last_seen<=?", (stamp, stamp-1800))
                for scope, maximum in ((account_scope, 5), (address_scope, 30)):
                    count = conn.execute("SELECT COUNT(*) FROM login_attempts WHERE scope=?", (scope,)).fetchone()[0]
                    if count >= maximum:
                        raise HTTPException(429, "Too many sign-in attempts; retry after 15 minutes", headers={"Retry-After": "900"})
                conn.executemany("INSERT INTO login_attempts VALUES (?,?)", ((account_scope, stamp), (address_scope, stamp)))
            row = conn.execute("SELECT * FROM accounts WHERE email=?", (email,)).fetchone()
            if not conn.execute("SELECT 1 FROM accounts LIMIT 1").fetchone():
                raise HTTPException(503, "No verified accounts provisioned; a server administrator must configure identity")
            salt = bytes.fromhex(row["salt"]) if row else bytes(16)
            candidate = password_hash(password, salt)
            expected = row["password_hash"] if row else "0"*64
            if not hmac.compare_digest(candidate, expected) or not row or not row["enabled"]:
                raise HTTPException(401, "Invalid email or password")
            token = secrets.token_urlsafe(32)
            expires = now + timedelta(hours=8)
            with conn:
                conn.execute("BEGIN IMMEDIATE")
                current = conn.execute("SELECT password_hash,enabled FROM accounts WHERE id=?", (row["id"],)).fetchone()
                if not current or not current["enabled"] or current["password_hash"] != row["password_hash"]:
                    raise HTTPException(401, "Invalid email or password")
                conn.execute("DELETE FROM login_attempts WHERE scope=?", (account_scope,))
                conn.execute("INSERT INTO sessions VALUES (?,?,?,?,?)",
                             (self.digest(token), row["id"], stamp, expires.timestamp(), stamp))
            return {"user": json.loads(row["profile"]), "mode": "production", "accessToken": token,
                    "issuedAt": now.isoformat(), "expiresAt": expires.isoformat()}
        finally:
            conn.close()

    @staticmethod
    def digest(token: str) -> str:
        return hashlib.sha256(token.encode()).hexdigest()

    def session(self, token: str) -> dict:
        if not token or len(token) > 128:
            raise HTTPException(401, "A verified session is required", headers={"WWW-Authenticate": "Bearer"})
        # wall-clock: authentication is independent of simulation and replay clocks.
        stamp = wall_now().timestamp()
        conn = self._open()
        try:
            row = conn.execute("SELECT a.profile,a.enabled,s.issued_at,s.expires_at,s.last_seen FROM sessions s "
                               "JOIN accounts a ON a.id=s.account_id WHERE s.token_hash=?", (self.digest(token),)).fetchone()
            if not row or not row["enabled"] or row["expires_at"] <= stamp or row["last_seen"] <= stamp-1800:
                raise HTTPException(401, "Session is invalid, expired or revoked", headers={"WWW-Authenticate": "Bearer"})
            with conn:
                conn.execute("UPDATE sessions SET last_seen=? WHERE token_hash=?", (stamp, self.digest(token)))
            return {"user": json.loads(row["profile"]), "issuedAt": row["issued_at"], "expiresAt": row["expires_at"]}
        finally:
            conn.close()

    def revoke(self, token: str) -> None:
        conn = self._open()
        try:
            with conn:
                conn.execute("DELETE FROM sessions WHERE token_hash=?", (self.digest(token),))
        finally:
            conn.close()

    def probe(self) -> dict:
        try:
            conn = self._open()
            try:
                ok = conn.execute("PRAGMA quick_check").fetchone()[0] == "ok"
                configured = bool(conn.execute("SELECT 1 FROM accounts WHERE enabled=1 LIMIT 1").fetchone())
                return {"ok": ok, "configured": configured, "path": str(self.path),
                        "error": None if ok else "Identity store integrity check failed"}
            finally:
                conn.close()
        except LedgerError as exc:
            return {"ok": False, "configured": False, "path": str(self.path), "error": str(exc)}


def get_auth_store() -> AuthStore:
    return AuthStore()
