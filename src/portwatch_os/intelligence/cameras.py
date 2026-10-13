"""Durable, scoped camera registry. Registration never implies a live feed."""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, field_validator, model_validator

from src.portwatch_os.clock import wall_now, world_now
from src.portwatch_os.ledger.store import LedgerError
from src.utils import port_registry
from src.utils.config import STATE_DIR


class EvidenceConflict(LedgerError):
    """An existing immutable observation id was submitted again."""


class Camera(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str = Field(pattern=r"^[a-zA-Z0-9_-]{1,80}$")
    portCode: str
    name: str = Field(min_length=1, max_length=120)
    lat: float = Field(ge=-90, le=90, allow_inf_nan=False)
    lon: float = Field(ge=-180, le=180, allow_inf_nan=False)
    coverage: str = Field(min_length=1, max_length=400)
    viewpoint: str = Field(default="berth", pattern=r"^(berth|gate|anchorage|channel|yard)$")
    mediaUrl: HttpUrl | None = None
    feedType: str = Field(default="image", pattern=r"^(image|mjpeg|mp4|webm|hls)$")
    access: str = Field(default="port_authority", pattern=r"^(public|port_authority)$")
    source: str = Field(min_length=1, max_length=200)
    rightsBasis: str = Field(min_length=1, max_length=500)
    enabled: bool = True
    poseBasis: str = Field(default="operator_supplied", pattern=r"^(operator_supplied|surveyed|estimated)$")

    @field_validator("portCode")
    @classmethod
    def valid_port(cls, value: str) -> str:
        port = port_registry.resolve(value)
        if port is None:
            raise ValueError("camera must reference a registered port")
        return port.locode

    @model_validator(mode="after")
    def browser_url(self):
        if self.mediaUrl is not None:
            if self.mediaUrl.scheme != "https" or self.mediaUrl.username or self.mediaUrl.password:
                raise ValueError("camera media must use HTTPS without credentials in the URL")
        return self


class CameraEvidence(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str = Field(pattern=r"^[a-zA-Z0-9_-]{1,80}$")
    cameraId: str
    observedAt: str
    kind: str = Field(pattern=r"^(berth_occupied|vessel_movement|gate_queue|crane_activity|possible_interruption)$")
    confidence: float = Field(ge=0, le=1, allow_inf_nan=False)
    summary: str = Field(min_length=1, max_length=600)
    source: str = Field(min_length=1, max_length=200)
    method: str = Field(default="operator_review", pattern=r"^(operator_review|computer_vision)$")
    modelVersion: str | None = Field(default=None, max_length=120)
    reviewed: bool = False
    frameSha256: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")
    roi: tuple[int, int, int, int] | None = None
    frameThroughAt: str | None = None

    @model_validator(mode="after")
    def valid_evidence(self):
        from src.portwatch_os.learning.weather_feedback import instant
        if instant(self.observedAt) > world_now():
            raise ValueError("camera evidence cannot come from the future")
        if self.frameThroughAt is not None and not instant(self.observedAt) <= instant(self.frameThroughAt) <= world_now():
            raise ValueError("frame interval must follow its start and be in the past")
        if self.roi is not None and (min(self.roi) < 0 or self.roi[2] <= self.roi[0] or self.roi[3] <= self.roi[1]):
            raise ValueError("ROI requires valid left/top/right/bottom bounds")
        if self.method == "computer_vision" and not (self.modelVersion and self.frameSha256 and self.roi):
            raise ValueError("computer vision evidence requires a model version, frame hash and ROI")
        if self.method == "computer_vision" and self.frameThroughAt is None:
            self.frameThroughAt = self.observedAt
        return self


class CameraRegistry:
    def __init__(self, path: Path | None = None):
        self.path = path or STATE_DIR / "intelligence.db"

    def _open(self):
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            conn = sqlite3.connect(self.path, timeout=10)
            conn.execute("PRAGMA foreign_keys=ON")
            if conn.execute("PRAGMA quick_check").fetchone()[0] != "ok":
                raise LedgerError("camera registry failed its integrity check")
            conn.execute("CREATE TABLE IF NOT EXISTS cameras (id TEXT PRIMARY KEY, record TEXT NOT NULL)")
            conn.execute("CREATE TABLE IF NOT EXISTS camera_evidence (id TEXT PRIMARY KEY, camera_id TEXT NOT NULL REFERENCES cameras(id), record TEXT NOT NULL)")
            conn.commit()
            return conn
        except (OSError, sqlite3.DatabaseError, LedgerError) as exc:
            if "conn" in locals():
                conn.close()
            raise LedgerError(f"camera registry cannot be opened: {exc}") from exc

    def cameras(self) -> list[dict]:
        conn = self._open()
        try:
            return [json.loads(row[0]) for row in conn.execute("SELECT record FROM cameras ORDER BY id")]
        finally:
            conn.close()

    def get(self, camera_id: str) -> dict | None:
        return next((row for row in self.cameras() if row["id"] == camera_id), None)

    def register(self, camera: Camera, actor: str) -> dict:
        # wall-clock: registry changes are operator audit stamps
        stamp = wall_now().isoformat()
        record = {**camera.model_dump(mode="json"), "registeredBy": actor, "updatedAt": stamp,
                  "health": "DISABLED" if not camera.enabled else "UNVERIFIED" if camera.mediaUrl else "UNCONFIGURED",
                  "lastFrameAt": None, "healthNote": "No feed health or frame timestamp has been verified."}
        conn = self._open()
        try:
            with conn:
                conn.execute("INSERT INTO cameras VALUES (?,?) ON CONFLICT(id) DO UPDATE SET record=excluded.record",
                             (camera.id, json.dumps(record)))
            return record
        finally:
            conn.close()

    def record_evidence(self, evidence: CameraEvidence, actor: str) -> dict:
        camera = self.get(evidence.cameraId)
        if camera is None:
            raise ValueError("camera is not registered")
        # wall-clock: preserve who recorded the observation and when
        record = {**evidence.model_dump(), "portCode": camera["portCode"], "coverage": camera["coverage"],
                  "recordedBy": actor, "recordedAt": wall_now().isoformat(),
                  "operationalUse": "reviewed_evidence" if evidence.reviewed else "needs_review"}
        conn = self._open()
        try:
            with conn:
                existing = conn.execute("SELECT record FROM camera_evidence WHERE id=?", (evidence.id,)).fetchone()
                if existing:
                    raise EvidenceConflict("camera evidence is immutable; use a new observation id")
                conn.execute("INSERT INTO camera_evidence VALUES (?,?,?)", (evidence.id, evidence.cameraId, json.dumps(record)))
            return record
        finally:
            conn.close()

    def evidence(self, camera_ids: set[str]) -> list[dict]:
        conn = self._open()
        try:
            rows = [json.loads(r[0]) for r in conn.execute("SELECT record FROM camera_evidence")]
            from src.portwatch_os.learning.weather_feedback import instant
            now = world_now()
            return sorted([r for r in rows if r["cameraId"] in camera_ids
                           and instant(r["observedAt"]) <= now and r.get("recordedAt")
                           and instant(r["recordedAt"]) <= now],
                          key=lambda r: r["observedAt"], reverse=True)[:200]
        finally:
            conn.close()

    def probe(self) -> dict:
        try:
            conn = self._open()
            conn.close()
            return {"ok": True, "path": str(self.path), "error": None}
        except (LedgerError, OSError) as exc:
            return {"ok": False, "path": str(self.path), "error": str(exc)}
