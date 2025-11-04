from __future__ import annotations

from typing import List
from uuid import UUID

from pydantic import BaseModel, ConfigDict, SecretStr, field_validator, model_validator

from app.models.user import UserRole


class LoginRequest(BaseModel):
    identifier: str
    password: SecretStr

    model_config = ConfigDict(populate_by_name=True, extra="ignore")

    @field_validator("identifier", mode="before")
    @classmethod
    def normalize_identifier(cls, value: str | SecretStr | None) -> str | None:
        if value is None:
            return None
        if isinstance(value, SecretStr):
            value = value.get_secret_value()
        value_str = str(value).strip()
        if not value_str:
            return None
        return value_str.lower()

    @field_validator("password", mode="before")
    @classmethod
    def ensure_password_not_blank(cls, value: SecretStr | str | None) -> SecretStr | str | None:
        if value is None:
            return None
        if isinstance(value, SecretStr):
            raw = value.get_secret_value()
        else:
            raw = str(value)
        if not raw.strip():
            return None
        return raw

    @field_validator("password")
    @classmethod
    def enforce_password_length(cls, value: SecretStr) -> SecretStr:
        raw = value.get_secret_value()
        if len(raw) < 8:
            raise ValueError("password must be at least 8 characters long")
        return value

    @model_validator(mode="after")
    def ensure_required(self) -> "LoginRequest":
        if self.identifier is None:
            raise ValueError("identifier required")
        if self.password is None:
            raise ValueError("password required")
        return self

    def normalized_identifier(self) -> str:
        return self.identifier


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
