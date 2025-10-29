from __future__ import annotations

from typing import List
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from app.models.user import UserRole


class OAuthStartRequest(BaseModel):
    redirect_uri: str | None = None
    scopes: List[str] | None = None
    link: bool = False


class OAuthStartResponse(BaseModel):
    provider: str
    authorization_url: str
    state: str


class OAuthCallbackRequest(BaseModel):
    code: str
    state: str
    redirect_uri: str | None = None


class OAuthCallbackResponse(BaseModel):
    access_token: str
    token_type: str
    user_id: UUID
    user_role: UserRole
    is_new_user: bool


class OAuthLinkResponse(BaseModel):
    provider: str
    linked: bool


class LinkedIdentity(BaseModel):
    provider: str
    provider_account_id: str
    email: str | None = None

    model_config = ConfigDict(from_attributes=True)
