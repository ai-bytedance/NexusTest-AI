from __future__ import annotations

import enum
import secrets
import string
import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Iterable, Sequence

from passlib.context import CryptContext

PREFIX_ALPHABET = string.ascii_uppercase + string.digits
TOKEN_PREFIX_LENGTH = 12
TOKEN_SECRET_BYTES = 32

_token_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


class TokenScope(str, enum.Enum):
    READ_PROJECTS = "read:projects"
    WRITE_PROJECTS = "write:projects"
    READ_APIS = "read:apis"
    WRITE_APIS = "write:apis"
    READ_CASES = "read:cases"
    WRITE_CASES = "write:cases"
    EXECUTE = "execute"
    READ_REPORTS = "read:reports"
    WRITE_INTEGRATIONS = "write:integrations"
    ADMIN = "admin"


ALL_TOKEN_SCOPES: frozenset[str] = frozenset(scope.value for scope in TokenScope)


@dataclass(slots=True)
class TokenAuthContext:
    token_id: uuid.UUID
    token_prefix: str
    scopes: frozenset[str]
    project_ids: frozenset[uuid.UUID]
    expires_at: datetime | None
    rate_limit_policy_id: uuid.UUID | None

    def has_scope(self, required: str) -> bool:
        if TokenScope.ADMIN.value in self.scopes:
            return True
        return required in self.scopes


def generate_token_components() -> tuple[str, str]:
    prefix = "".join(secrets.choice(PREFIX_ALPHABET) for _ in range(TOKEN_PREFIX_LENGTH))
    secret = secrets.token_urlsafe(TOKEN_SECRET_BYTES)
    return prefix, secret


def format_token(prefix: str, secret: str) -> str:
    return f"{prefix}.{secret}"


def hash_token_secret(secret: str) -> str:
    return _token_context.hash(secret)


def verify_token_secret(secret: str, hashed: str) -> bool:
    return _token_context.verify(secret, hashed)


def parse_token(raw_token: str) -> tuple[str, str]:
    if raw_token.count(".") != 1:
        raise ValueError("Invalid token format")
    prefix, secret = raw_token.split(".", 1)
    if not prefix or not secret:
        raise ValueError("Invalid token format")
    return prefix, secret


def normalize_scopes(scopes: Iterable[str]) -> list[str]:
    normalized: list[str] = []
    seen: set[str] = set()
    for scope in scopes:
        value = scope.strip()
        if not value:
            continue
        if value not in ALL_TOKEN_SCOPES:
            raise ValueError(f"Unknown scope: {value}")
        if value in seen:
            continue
        seen.add(value)
        normalized.append(value)
    return normalized


def normalize_project_ids(project_ids: Iterable[uuid.UUID | str]) -> list[str]:
    normalized: list[str] = []
    seen: set[str] = set()
    for project_id in project_ids:
        if isinstance(project_id, uuid.UUID):
            value = str(project_id)
        else:
            value = str(project_id).strip()
            try:
                uuid.UUID(value)
            except ValueError as exc:
                raise ValueError(f"Invalid project id: {project_id}") from exc
        if value in seen:
            continue
        seen.add(value)
        normalized.append(value)
    return normalized


def to_uuid_set(project_ids: Sequence[str]) -> frozenset[uuid.UUID]:
    values: list[uuid.UUID] = []
    for raw in project_ids:
        values.append(uuid.UUID(raw))
    return frozenset(values)


__all__ = [
    "TokenScope",
    "ALL_TOKEN_SCOPES",
    "TokenAuthContext",
    "generate_token_components",
    "format_token",
    "hash_token_secret",
    "verify_token_secret",
    "parse_token",
    "normalize_scopes",
    "normalize_project_ids",
    "to_uuid_set",
]
