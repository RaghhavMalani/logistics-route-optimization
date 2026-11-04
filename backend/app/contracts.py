"""OpenAPI response shapes. The routers still return their existing payloads."""

from typing import Any, Literal
from typing_extensions import NotRequired, TypedDict


WorkspaceRole = Literal["VESSEL_OPERATOR", "SHIPPING_COMPANY", "PORT_AUTHORITY", "NATIONAL_ADMIN"]


class IdentityUser(TypedDict):
    id: str
    email: str
    displayName: str
    role: WorkspaceRole
    organisation: str
    portCode: str | None
    portCodes: NotRequired[list[str]]
    companyId: str | None
    vesselIds: list[str]
    canApprove: NotRequired[bool]


class SessionPayload(TypedDict):
    user: IdentityUser
    mode: Literal["demo", "production"]
    issuedAt: str
    expiresAt: str
    demoId: NotRequired[str]
    accessToken: NotRequired[str]


class HandoffItem(TypedDict):
    id: str
    vesselName: str
    portCode: str
    state: str
    summary: NotRequired[str]
    nextActor: str | None
    deepLink: str | None
    advisoryId: NotRequired[str]


class HandoffPayload(TypedDict):
    items: list[HandoffItem]


class WorldClockPayload(TypedDict):
    mode: Literal["LIVE", "REPLAY", "HISTORICAL_MISSION", "SCENARIO"]
    now: str
    wallNow: str
    anchor: str | None
    setAt: str | None
    rate: float | None
    frozen: bool
    setBy: str
    reason: str
    subject: dict[str, Any]
    offsetFromWallSeconds: float


class ScreenSection(TypedDict):
    status: int
    data: Any


class ScreenPayload(TypedDict):
    sections: dict[str, ScreenSection]
    session: SessionPayload | None


class RegistryPosition(TypedDict):
    lat: float
    lon: float


class PortRegistryPayload(TypedDict):
    modelId: str
    code: str
    name: str
    short: str
    authority: str
    location: RegistryPosition
    coast: Literal["east", "west", "south"]
    capacityIndex: float
    berthCount: int
    connectivityScore: float
