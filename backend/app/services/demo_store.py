"""Visitor-owned demonstration worlds, separate from every operational store.

Opaque demo credentials never enter AuthStore or current_identity. Every write
holds one SQLite transaction and addresses only its authenticated session row.
No production singleton, collector, clock, model or ledger is overridden.
"""
import hashlib
import json
import os
import secrets
import sqlite3
from datetime import datetime, timedelta, timezone
from functools import lru_cache
from pathlib import Path

from fastapi import HTTPException
from src.portwatch_os.clock import wall_now

ROLES = ("SHIPPING_COMPANY", "VESSEL_OPERATOR", "PORT_AUTHORITY", "NATIONAL_ADMIN")
LABELS = dict(zip(ROLES, ("Company", "Vessel", "Port", "Admin")))


def utc_now():
    # wall-clock: real credential expiry and visitor action receipts cannot move with a replay seek.
    return wall_now()


def seed_world(at):
    return {"version": "role-demo-v1", "epoch": at, "meaning": "FICTIONAL DEMONSTRATION; not observed AIS, berth records or operational outcomes.",
        "organisation": "PortWatch Demo Shipping", "portCode": "INNSA", "selectedVessel": "PWD-001",
        "event": {"id": "demo-suez-restriction", "title": "Assumed Suez restriction", "source": "DEMO_SCENARIO", "chokepoint": "SUEZ", "closureHours": 72},
        "fleet": [
            {"id": "PWD-001", "name": "PW Meridian", "laneCode": "EUR_IND", "portCode": "INNSA", "hoursToRisk": 24, "etaHours": 180, "lat": 33.5, "lon": 26.9, "cargo": "640 TEU · scheduled inland connection", "status": "Approaching restriction", "mmsi": None},
            {"id": "PWD-002", "name": "PW Coromandel", "laneCode": "EUR_IND", "portCode": "INNSA", "hoursToRisk": -8, "etaHours": 140, "lat": 29.3, "lon": 32.8, "cargo": "420 TEU · refrigerated cargo", "status": "Committed passage", "mmsi": None},
            {"id": "PWD-003", "name": "PW Konkan", "laneCode": "GULF_IND", "portCode": "INNSA", "hoursToRisk": 36, "etaHours": 84, "lat": 25.6, "lon": 53.4, "cargo": "300 TEU · feeder connection", "status": "Approaching Hormuz", "mmsi": None}],
        "comparisons": [], "proposal": None, "portComparison": None, "advisories": [], "history": []}


class DemoStore:
    def __init__(self, path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            db.execute("CREATE TABLE IF NOT EXISTS sessions (id TEXT PRIMARY KEY, token_hash TEXT UNIQUE NOT NULL, role TEXT NOT NULL, issued TEXT NOT NULL, expires TEXT NOT NULL, world TEXT NOT NULL)")

    def connect(self):
        db = sqlite3.connect(self.path, timeout=15)
        db.row_factory = sqlite3.Row
        return db

    def create(self, role):
        if role not in ROLES:
            raise HTTPException(422, "Choose one of the four demonstration roles")
        now = utc_now()
        token = "pw_demo_" + secrets.token_urlsafe(32)
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            db.execute("DELETE FROM sessions WHERE expires <= ?", (now.isoformat(),))
            if db.execute("SELECT COUNT(*) FROM sessions").fetchone()[0] >= 128:
                raise HTTPException(429, "Demo capacity is occupied; try again when a session expires")
            db.execute("INSERT INTO sessions VALUES (?,?,?,?,?,?)", (secrets.token_hex(16), self.digest(token), role, now.isoformat(), (now+timedelta(hours=12)).isoformat(), json.dumps(seed_world(now.isoformat()))))
        return self.session(token) | {"accessToken": token}

    @staticmethod
    def digest(token):
        return hashlib.sha256(token.encode()).hexdigest()

    def row(self, db, token):
        if not token.startswith("pw_demo_") or len(token) > 120:
            raise HTTPException(401, "A valid demo session is required")
        row = db.execute("SELECT * FROM sessions WHERE token_hash=?", (self.digest(token),)).fetchone()
        if not row or datetime.fromisoformat(row["expires"]) <= utc_now():
            raise HTTPException(401, "Demo session expired; open a new demo from the entry screen")
        return row

    def session(self, token):
        with self.connect() as db:
            row = self.row(db, token)
        role = row["role"]
        selected_port = json.loads(row["world"]).get("portCode", "INNSA")
        if selected_port not in ("INNSA", "INPRT", "INMAA"): selected_port = "INNSA"
        return {"mode": "demo", "demoId": row["id"], "issuedAt": row["issued"], "expiresAt": row["expires"],
            "user": {"id": "demo-"+LABELS[role].lower(), "email": LABELS[role].lower()+"@portwatch.demo", "displayName": LABELS[role]+" demonstrator", "role": role,
                "organisation": "PortWatch Demo Shipping" if role in ROLES[:2] else "Demo Paradip planning desk" if selected_port == "INPRT" else "Demo JNPA planning desk", "companyId": "portwatch-demo-shipping" if role in ROLES[:2] else None,
                "portCode": selected_port if role == "PORT_AUTHORITY" else None, "vesselIds": ["PWD-001"] if role == "VESSEL_OPERATOR" else []}}

    def read(self, token):
        with self.connect() as db:
            row = self.row(db, token)
            return json.loads(row["world"])

    def update(self, token, action, allowed=ROLES):
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row = self.row(db, token)
            if row["role"] not in allowed:
                raise HTTPException(403, "This demo action belongs to another role")
            world = json.loads(row["world"])
            result = action(world)
            encoded = json.dumps(world, allow_nan=False)
            if len(encoded.encode()) > 1_500_000:
                raise HTTPException(409, "Demo history capacity reached; reset your sandbox")
            db.execute("UPDATE sessions SET world=? WHERE id=?", (encoded, row["id"]))
            return result

    def switch(self, token, role):
        if role not in ROLES:
            raise HTTPException(422, "Unknown demo role")
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row = self.row(db, token)
            db.execute("UPDATE sessions SET role=? WHERE id=?", (role, row["id"]))
            if role == "VESSEL_OPERATOR":
                world = json.loads(row["world"])
                world["selectedVessel"] = "PWD-001"
                db.execute("UPDATE sessions SET world=? WHERE id=?", (json.dumps(world), row["id"]))
        return self.session(token) | {"accessToken": token}

    def revoke(self, token):
        with self.connect() as db:
            self.row(db, token)
            db.execute("DELETE FROM sessions WHERE token_hash=?", (self.digest(token),))


@lru_cache(maxsize=1)
def get_demo_store():
    root = Path(os.environ.get("PORTWATCH_STATE_DIR") or Path(__file__).resolve().parents[3]/"outputs")
    return DemoStore(root/"demo"/"sessions.sqlite3")
