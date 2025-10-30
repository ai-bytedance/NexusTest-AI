from __future__ import annotations

import uuid
from datetime import datetime
from typing import Iterable

from fastapi import status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import ErrorCode, http_exception
from app.models import ApiToken, Project, RateLimitPolicy, User
from app.schemas.rate_limit import RateLimitPolicyCreate, RateLimitPolicyUpdate
from app.services.audit_log import record_audit_log


class RateLimitService:
    def __init__(
        self,
        session: Session,
        *,
        actor: User,
        project: Project,
        client_ip: str | None = None,
        user_agent: str | None = None,
    ) -> None:
        self.session = session
        self.actor = actor
        self.project = project
        self.client_ip = client_ip
        self.user_agent = user_agent

    def list_policies(self) -> list[RateLimitPolicy]:
        stmt = (
            select(RateLimitPolicy)
            .where(RateLimitPolicy.project_id == self.project.id)
            .order_by(RateLimitPolicy.created_at.asc())
        )
        return self.session.execute(stmt).scalars().all()

    def create_policy(self, payload: RateLimitPolicyCreate) -> RateLimitPolicy:
        policy = RateLimitPolicy(
            project_id=self.project.id,
            name=payload.name,
            rules=[rule.model_dump(mode="json") for rule in payload.rules],
            enabled=payload.enabled,
        )
        self.session.add(policy)
        record_audit_log(
            self.session,
            actor=self.actor,
            action="rate_limit_policy.created",
            resource_type="rate_limit_policy",
            resource_id=str(policy.id),
            project_id=self.project.id,
            metadata={
                "name": policy.name,
                "enabled": policy.enabled,
            },
            ip=self.client_ip,
            user_agent=self.user_agent,
        )
        self.session.commit()
        self.session.refresh(policy)
        return policy

    def update_policy(self, policy: RateLimitPolicy, payload: RateLimitPolicyUpdate) -> RateLimitPolicy:
        if payload.name is not None:
            policy.name = payload.name
        if payload.rules is not None:
            policy.rules = [rule.model_dump(mode="json") for rule in payload.rules]
        if payload.enabled is not None:
            policy.enabled = payload.enabled
        self.session.add(policy)
        record_audit_log(
            self.session,
            actor=self.actor,
            action="rate_limit_policy.updated",
            resource_type="rate_limit_policy",
            resource_id=str(policy.id),
            project_id=self.project.id,
            metadata={
                "name": policy.name,
                "enabled": policy.enabled,
            },
            ip=self.client_ip,
            user_agent=self.user_agent,
        )
        self.session.commit()
        self.session.refresh(policy)
        return policy

    def delete_policy(self, policy: RateLimitPolicy) -> None:
        if self.project.default_rate_limit_policy_id == policy.id:
            self.project.default_rate_limit_policy_id = None
        tokens_stmt = select(ApiToken).where(ApiToken.rate_limit_policy_id == policy.id)
        tokens = self.session.execute(tokens_stmt).scalars().all()
        for token in tokens:
            token.rate_limit_policy_id = None
            self.session.add(token)
        policy_id = str(policy.id)
        record_audit_log(
            self.session,
            actor=self.actor,
            action="rate_limit_policy.deleted",
            resource_type="rate_limit_policy",
            resource_id=policy_id,
            project_id=self.project.id,
            metadata={"affected_tokens": len(tokens)},
            ip=self.client_ip,
            user_agent=self.user_agent,
        )
        self.session.delete(policy)
        self.session.add(self.project)
        self.session.commit()

    def set_default_policy(self, policy: RateLimitPolicy | None) -> Project:
        if policy is not None and policy.project_id != self.project.id:
            raise http_exception(status.HTTP_400_BAD_REQUEST, ErrorCode.BAD_REQUEST, "Policy does not belong to project")
        self.project.default_rate_limit_policy_id = policy.id if policy else None
        self.session.add(self.project)
        record_audit_log(
            self.session,
            actor=self.actor,
            action="rate_limit_policy.set_default",
            resource_type="project",
            resource_id=str(self.project.id),
            project_id=self.project.id,
            metadata={"policy_id": str(policy.id) if policy else None},
            ip=self.client_ip,
            user_agent=self.user_agent,
        )
        self.session.commit()
        self.session.refresh(self.project)
        return self.project

    def get_policy(self, policy_id: uuid.UUID) -> RateLimitPolicy:
        policy = self.session.get(RateLimitPolicy, policy_id)
        if policy is None or policy.project_id != self.project.id:
            raise http_exception(status.HTTP_404_NOT_FOUND, ErrorCode.NOT_FOUND, "Rate limit policy not found")
        return policy


__all__ = ["RateLimitService"]
