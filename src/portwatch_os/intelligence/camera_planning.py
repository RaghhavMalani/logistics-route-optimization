"""Reviewed local evidence on a scenario clone; never rewrites observed port state."""
from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from src.portwatch_os.clock import LIVE, get_clock, world_now
from src.portwatch_os.intelligence.cameras import CameraRegistry
from src.portwatch_os.learning.weather_feedback import instant
from src.portwatch_os.roles import NATIONAL_ADMIN, PORT_AUTHORITY


class CameraPlanningAssumption(BaseModel):
    model_config = ConfigDict(extra="forbid")
    evidenceId: str = Field(min_length=1, max_length=80)
    berthId: str = Field(min_length=1, max_length=80)
    holdHours: float = Field(ge=.25, le=6, allow_inf_nan=False)


def apply_camera_hold(state, request: CameraPlanningAssumption, store: CameraRegistry, who):
    if not who.verified or (who.role != NATIONAL_ADMIN and not (
            who.role == PORT_AUTHORITY and state.port_code in who.port_codes)):
        raise ValueError("camera planning requires this port's verified authority")
    if get_clock().state.mode != LIVE:
        raise ValueError("current camera planning requires the live clock")
    cameras = {c["id"]: c for c in store.cameras() if c["portCode"] == state.port_code}
    evidence = next((e for e in store.evidence(set(cameras)) if e["id"] == request.evidenceId), None)
    if not evidence or not evidence.get("reviewed") or evidence["kind"] != "berth_occupied":
        raise ValueError("a reviewed berth occupancy observation from this port is required")
    camera = cameras[evidence["cameraId"]]
    if not camera["enabled"] or camera["viewpoint"] != "berth":
        raise ValueError("the observation must come from an enabled berth viewpoint")
    age = (world_now() - instant(evidence["observedAt"])).total_seconds()
    if not 0 <= age <= 1800:
        raise ValueError("camera planning requires an observation within 30 minutes")
    cloned = state.clone()
    berth = cloned.berth(request.berthId)
    if berth is None:
        raise ValueError("the selected berth is not in this port's twin")
    # A still frame cannot tell us when a berth will be free. The duration and
    # mapping to a schematic berth are explicit operator assumptions. Existing
    # hull identity and a later existing release time are retained.
    berth.occupied_by = berth.occupied_by or "camera-hold:" + evidence["id"]
    berth.free_at_hour = max(berth.free_at_hour or cloned.hour, cloned.hour + request.holdHours)
    basis = {"observation": evidence, "cameraPoseBasis": camera["poseBasis"],
             "baseStateEpoch": state.epoch, "source": "REVIEWED_CAMERA_EVIDENCE",
             "assumption": {"berthId": request.berthId, "holdHours": request.holdHours,
                            "source": "OPERATOR_ASSUMPTION"},
             "scenarioState": cloned.to_dict(),
             "scope": "This viewpoint and selected berth only; no vessel identity inferred."}
    return cloned, basis
