"""Verified sign-in; accounts and memberships are provisioned only on the server."""
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Request, Response
from pydantic import BaseModel, ConfigDict, Field

from backend.app.auth_store import AuthStore, get_auth_store

router = APIRouter()


class Credentials(BaseModel):
    model_config = ConfigDict(extra="forbid")
    email: str = Field(min_length=3, max_length=254)
    password: str = Field(min_length=1, max_length=256)


@router.post("/auth/login")
def login(payload: Credentials, request: Request, response: Response,
          store: AuthStore = Depends(get_auth_store)) -> dict:
    response.headers["Cache-Control"] = "no-store"
    return store.login(payload.email, payload.password, request.client.host if request.client else "unknown")


@router.get("/auth/session")
def session(request: Request, response: Response) -> dict:
    response.headers["Cache-Control"] = "no-store"
    session = request.state.verified_session
    return {"user": session["user"], "mode": "production",
            "issuedAt": datetime.fromtimestamp(session["issuedAt"], timezone.utc).isoformat(),
            "expiresAt": datetime.fromtimestamp(session["expiresAt"], timezone.utc).isoformat()}


@router.post("/auth/logout", status_code=204)
def logout(request: Request, response: Response, store: AuthStore = Depends(get_auth_store)) -> None:
    response.headers["Cache-Control"] = "no-store"
    store.revoke(request.state.session_token)
