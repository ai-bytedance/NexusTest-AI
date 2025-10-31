from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Iterable, Sequence

from fastapi import status
from sqlalchemy import Select, select
from sqlalchemy.orm import Session

from app.core.api_tokens import (
    TokenAuthContext,
    TokenScope,
    format_token,
    generate_token_components,
    hash_token_secret,
    normalize_project_ids,
    normalize_scopes,
)
from app.core.config import get_settings
from app.core.errors import ErrorCode, http_exception
from app.models import ApiToken, ProjectMember, ProjectRole, RateLimitPolicy, User
from app.services.audit_log import record_audit_log


class ApiTokenService:
    def __init__(
        self,
        session: Session,
        actor: User,
        *,
        client_ip: str | None = None,
        user_agent: str | None = None,
    ) -> None:
        self.session = session
        self.actor = actor
        self.client_ip = client_ip
        self.user_agent = user_agent

    # ------------------------------------------------------------------
    # Query helpers
    # ------------------------------------------------------------------

    def list_tokens(self) -> list[ApiToken]:
        stmt = (
            select(ApiToken)
            .where(ApiToken.user_id == self.actor.id)
            .order_by(ApiToken.created_at.desc())
        )
        return self.session.execute(stmt).scalars().all()

    def get_owned_token(self, token_id: uuid.UUID) -> ApiToken:
        token = self.session.get(ApiToken, token_id)
        if token is None or token.user_id != self.actor.id:
            raise http_exception(status.HTTP_404_NOT_FOUND, ErrorCode.NOT_FOUND, "Token not found")
        return token

    # ------------------------------------------------------------------
    # Mutations
    # ------------------------------------------------------------------

    def create_token(
        self,
        *,
        name: str,
        scopes: Iterable[str],
        project_ids: Iterable[uuid.UUID | str] | None,
        expires_at: datetime | None,
        rate_limit_policy_id: uuid.UUID | None,
    ) -> tuple[ApiToken, str]:
        normalized_scopes = normalize_scopes(scopes)
        if not normalized_scopes:
            raise http_exception(status.HTTP_400_BAD_REQUEST, ErrorCode.BAD_REQUEST, "At least one scope is required")

        normalized_projects = normalize_project_ids(project_ids or [])
        project_uuid_set = {uuid.UUID(value) for value in normalized_projects}
        self._assert_project_membership(project_uuid_set)

        policy: RateLimitPolicy | None = None
        if rate_limit_policy_id is not None:
            policy = self._load_policy(rate_limit_policy_id)
            self._assert_policy_allowed(policy, project_uuid_set)

        prefix, secret = self._generate_unique_token()
        token_hash = hash_token_secret(secret)

        token = ApiToken(
            user_id=self.actor.id,
            name=name,
            token_prefix=prefix,
            token_hash=token_hash,
            scopes=normalized_scopes,
            project_ids=sorted(normalized_projects),
            expires_at=expires_at,
            rate_limit_policy_id=policy.id if policy else None,
        )

        self.session.add(token)
        record_audit_log(
            self.session,
            actor=self.actor,
            action="token.created",
            resource_type="api_token",
            resource_id=str(token.id),
            metadata={
                "name": name,
                "scopes": normalized_scopes,
                "project_ids": token.project_ids,
                "expires_at": expires_at.isoformat() if expires_at else None,
                "rate_limit_policy_id": str(policy.id) if policy else None,
            },
            ip=self.client_ip,
            user_agent=self.user_agent,
        )
        self.session.commit()
        self.session.refresh(token)
        return token, format_token(prefix, secret)

    def rotate_token(self, token: ApiToken, *, grace_seconds: int | None = None) -> tuple[ApiToken, str]:
        if token.revoked_at is not None:
            raise http_exception(status.HTTP_400_BAD_REQUEST, ErrorCode.BAD_REQUEST, "Cannot rotate a revoked token")

        settings = get_settings()
        if grace_seconds is None:
            grace_seconds = int(getattr(settings, "token_rotation_grace_seconds", 0) or 0)

        # Generate a new secret but keep the existing prefix to enable dual-valid window
        _prefix, secret = generate_token_components()
        token.prev_token_hash = token.token_hash
        if grace_seconds > 0:
            from datetime import datetime, timedelta, timezone

            token.prev_valid_until = datetime.now(timezone.utc) + timedelta(seconds=grace_seconds)
        else:
            token.prev_valid_until = None
        token.token_hash = hash_token_secret(secret)
        token.last_used_at = None

        record_audit_log(
            self.session,
            actor=self.actor,
            action="token.rotated",
            resource_type="api_token",
            resource_id=str(token.id),
            metadata={
                "token_prefix": token.token_prefix,
                "grace_seconds": grace_seconds,
                "prev_valid_until": token.prev_valid_until.isoformat() if token.prev_valid_until else None,
            },
            ip=self.client_ip,
            user_agent=self.user_agent,
        )
        self.session.add(token)
        self.session.commit()
        self.session.refresh(token)
        return token, format_token(token.token_prefix, secret)

    def revoke_token(self, token: ApiToken) -> ApiToken:
        if token.revoked_at is not None:
            return token
        token.revoked_at = datetime.now(timezone.utc)
        record_audit_log(
            self.session,
            actor=self.actor,
            action="token.revoked",
            resource_type="api_token",
            resource_id=str(token.id),
            metadata={"token_prefix": token.token_prefix},
            ip=self.client_ip,
            user_agent=self.user_agent,
        )
        self.session.add(token)
        self.session.commit()
        self.session.refresh(token)
        return token

    def delete_token(self, token: ApiToken) -> None:
        token_id = str(token.id)
        record_audit_log(
            self.session,
            actor=self.actor,
            action="token.deleted",
            resource_type="api_token",
            resource_id=token_id,
            metadata={"token_prefix": token.token_prefix},
            ip=self.client_ip,
            user_agent=self.user_agent,
        )
        self.session.delete(token)
        self.session.commit()

    # ------------------------------------------------------------------
    # Validation helpers
    # ------------------------------------------------------------------

    def _assert_project_membership(self, project_ids: set[uuid.UUID]) -> None:
        if not project_ids:
            return
        stmt: Select[tuple[uuid.UUID]] = (
            select(ProjectMember.project_id)
            .where(
                ProjectMember.project_id.in_(list(project_ids)),
                ProjectMember.user_id == self.actor.id,
                ProjectMember.is_deleted.is_(False),
            )
        )
        accessible = set(self.session.execute(stmt).scalars().all())
        missing = project_ids - accessible
        if missing:
            raise http_exception(
                status.HTTP_403_FORBIDDEN,
                ErrorCode.NO_PERMISSION,
                "Token cannot reference projects the actor cannot access",
            )

    def _load_policy(self, policy_id: uuid.UUID) -> RateLimitPolicy:
        policy = self.session.get(RateLimitPolicy, policy_id)
        if policy is None:
            raise http_exception(status.HTTP_404_NOT_FOUND, ErrorCode.NOT_FOUND, "Rate limit policy not found")
        if not policy.enabled:
            raise http_exception(status.HTTP_400_BAD_REQUEST, ErrorCode.BAD_REQUEST, "Rate limit policy is disabled")
        return policy

    def _assert_policy_allowed(self, policy: RateLimitPolicy, project_ids: set[uuid.UUID]) -> None:
        if policy.project_id is None:
            return
        if policy.project_id not in project_ids:
            raise http_exception(
                status.HTTP_400_BAD_REQUEST,
                ErrorCode.BAD_REQUEST,
                "Token-level policy must belong to one of the scoped projects",
            )
        # Ensure actor is an admin of the policy project to attach stricter overrides.
        stmt = (
            select(ProjectMember.role)
            .where(
                ProjectMember.project_id == policy.project_id,
                ProjectMember.user_id == self.actor.id,
                ProjectMember.is_deleted.is_(False),
            )
            .limit(1)
        )
        membership = self.session.execute(stmt).scalar_one_or_none()
        if membership not in (ProjectRole.ADMIN,):
            raise http_exception(
                status.HTTP_403_FORBIDDEN,
                ErrorCode.NO_PERMISSION,
                "Only project admins can assign rate limit overrides",
            )

    def _generate_unique_token(self) -> tuple[str, str]:
        while True:
            prefix, secret = generate_token_components()
            exists = self.session.execute(
                select(ApiToken.id).where(ApiToken.token_prefix == prefix).limit(1)
            ).scalar_one_or_none()
            if not exists:
                return prefix, secret


__all__ = ["ApiTokenService", "TokenAuthContext", "TokenScope"]
