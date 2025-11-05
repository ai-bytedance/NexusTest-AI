from __future__ import annotations

from typing import List
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field, SecretStr, field_validator, model_validator

from app.models.user import UserRole


class LoginRequest(BaseModel):
    identifier: str | None = Field(default=None, alias="identifier")
    email: EmailStr | None = None
    username: str | None = None
    password: SecretStr

    model_config = ConfigDict(populate_by_name=True, extra="ignore")

    @field_validator("identifier", "username", mode="before")
    @classmethod
    def normalize_identifier_aliases(cls, value: str | SecretStr | None) -> str | None:
        if value is None:
            return None
        if isinstance(value, SecretStr):
            value = value.get_secret_value()
        candidate = str(value).strip()
        if not candidate:
            return None
        return candidate

    @field_validator("email", mode="before")
    @classmethod
    def normalize_email_alias(cls, value: str | EmailStr | SecretStr | None) -> str | None:
        if value is None:
            return None
        if isinstance(value, SecretStr):
            value = value.get_secret_value()
        candidate = str(value).strip()
        if not candidate:
            return None
        return candidate.lower()

    @field_validator("password", mode="before")
    @classmethod
    def password_non_empty(cls, value: SecretStr | str | None) -> SecretStr:
        if value is None:
            raise ValueError("password required")
        if isinstance(value, SecretStr):
            raw = value.get_secret_value()
        else:
            raw = str(value)
        if not raw.strip():
            raise ValueError("password required")
        return SecretStr(raw)

    @model_validator(mode="after")
    def ensure_identifier_present(self) -> "LoginRequest":
        try:
            normalized = self._resolve_identifier()
        except ValueError as exc:
            raise ValueError(str(exc)) from exc
        object.__setattr__(self, "_normalized_identifier", normalized)
        object.__setattr__(self, "identifier", normalized)
        return self

    def _resolve_identifier(self) -> str:
        for field_name in ("identifier", "email", "username"):
            value = getattr(self, field_name)
            if value is None:
                continue
            candidate = str(value).strip()
            if not candidate:
                continue
            return candidate.lower()
        raise ValueError("identifier required")

    def normalized_identifier(self) -> str:
        return getattr(self, "_normalized_identifier", self._resolve_identifier())


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
