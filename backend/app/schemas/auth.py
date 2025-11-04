from __future__ import annotations

from typing import List
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator, model_validator

from app.models.user import UserRole


class LoginRequest(BaseModel):
    username: str | None = None
    email: EmailStr | None = None
    password: str = Field(min_length=8)

    @field_validator("username", mode="before")
    @classmethod
    def normalize_username(cls, value: str | None) -> str | None:
        if value is None:
            return None
        if isinstance(value, str):
            value = value.strip()
            if not value:
                return None
            return value.lower()
        return value

    @field_validator("email", mode="before")
    @classmethod
    def normalize_email(cls, value: str | EmailStr | None) -> str | EmailStr | None:
        if value is None:
            return None
        if isinstance(value, str):
            value = value.strip()
            if not value:
                return None
            return value.lower()
        if isinstance(value, EmailStr):
            return str(value).strip().lower()
        return value

    @model_validator(mode="after")
    def ensure_identifier(self) -> "LoginRequest":
        if self.email is None and self.username is None:
            raise ValueError("Either email or username must be provided")
        return self

    def normalized_identifier(self) -> str:
        identifier = self.email or self.username
        return str(identifier).strip().lower()


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
