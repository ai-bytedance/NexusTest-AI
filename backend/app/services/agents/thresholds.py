from __future__ import annotations

import uuid
from typing import Any

from fastapi import status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.errors import ErrorCode, http_exception
from app.models import AgentAlertThreshold, Environment, Project, ProjectMember, ProjectRole, User, UserRole
from app.schemas.agent import AgentThresholdUpdate
from app.services.audit_log import record_audit_log


class AgentThresholdService:
    def __init__(
        self,
        session: Session,
        actor: User | None,
        *,
        client_ip: str | None = None,
        user_agent: str | None = None,
    ) -> None:
        self.session = session
        self.actor = actor
        self.client_ip = client_ip
        self.user_agent = user_agent
        self.settings = get_settings()

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _ensure_authenticated(self) -> None:
        if self.actor is None:
            raise http_exception(
                status.HTTP_401_UNAUTHORIZED,
                ErrorCode.NOT_AUTHENTICATED,
                "Authentication required",
            )

    def _load_project(self, project_id: uuid.UUID) -> Project:
        project = self.session.get(Project, project_id)
        if project is None or project.is_deleted:
            raise http_exception(status.HTTP_404_NOT_FOUND, ErrorCode.NOT_FOUND, "Project not found")
        return project

    def _ensure_membership(self, project: Project) -> ProjectMember | None:
        self._ensure_authenticated()
        assert self.actor is not None
        if self.actor.role == UserRole.ADMIN:
            return None
        stmt = (
            select(ProjectMember)
            .where(
                ProjectMember.project_id == project.id,
                ProjectMember.user_id == self.actor.id,
                ProjectMember.is_deleted.is_(False),
            )
            .limit(1)
        )
        membership = self.session.execute(stmt).scalar_one_or_none()
        if membership is None:
            raise http_exception(
                status.HTTP_403_FORBIDDEN,
                ErrorCode.NO_PERMISSION,
                "You do not have access to this project",
            )
        return membership

    def _require_admin(self, project: Project) -> None:
        membership = self._ensure_membership(project)
        if membership is None:
            return
        if membership.role != ProjectRole.ADMIN:
            raise http_exception(
                status.HTTP_403_FORBIDDEN,
                ErrorCode.NO_PERMISSION,
                "Project admin privileges are required",
            )

    def _load_environment(self, project: Project, environment_id: uuid.UUID | None) -> Environment | None:
        if environment_id is None:
            return None
        environment = self.session.get(Environment, environment_id)
        if environment is None or environment.is_deleted or environment.project_id != project.id:
            raise http_exception(
                status.HTTP_400_BAD_REQUEST,
                ErrorCode.BAD_REQUEST,
                "Environment does not belong to project",
            )
        return environment

    def _defaults(self) -> dict[str, int]:
        return {
            "offline_seconds": int(self.settings.agent_offline_threshold_seconds),
            "backlog_threshold": int(self.settings.agent_backlog_threshold),
            "latency_threshold_ms": int(self.settings.agent_latency_threshold_ms),
        }

    def _fetch_threshold(self, project_id: uuid.UUID, environment_id: uuid.UUID | None) -> AgentAlertThreshold | None:
        stmt = (
            select(AgentAlertThreshold)
            .where(
                AgentAlertThreshold.project_id == project_id,
                AgentAlertThreshold.environment_id.is_(None) if environment_id is None else AgentAlertThreshold.environment_id == environment_id,
                AgentAlertThreshold.is_deleted.is_(False),
            )
            .limit(1)
        )
        return self.session.execute(stmt).scalar_one_or_none()

    def _create_threshold(self, project: Project, environment: Environment | None) -> AgentAlertThreshold:
        defaults = self._defaults()
        threshold = AgentAlertThreshold(
            project_id=project.id,
            environment_id=environment.id if environment else None,
            offline_seconds=defaults["offline_seconds"],
            backlog_threshold=defaults["backlog_threshold"],
            latency_threshold_ms=defaults["latency_threshold_ms"],
            metadata={},
        )
        self.session.add(threshold)
        self.session.commit()
        self.session.refresh(threshold)
        return threshold

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get_threshold(self, project_id: uuid.UUID, environment_id: uuid.UUID | None) -> AgentAlertThreshold:
        project = self._load_project(project_id)
        self._ensure_membership(project)
        environment = self._load_environment(project, environment_id)
        threshold = self._fetch_threshold(project.id, environment.id if environment else None)
        if threshold is None:
            threshold = self._create_threshold(project, environment)
        return threshold

    def update_threshold(
        self,
        project_id: uuid.UUID,
        environment_id: uuid.UUID | None,
        payload: AgentThresholdUpdate,
    ) -> AgentAlertThreshold:
        project = self._load_project(project_id)
        self._require_admin(project)
        environment = self._load_environment(project, environment_id)
        threshold = self._fetch_threshold(project.id, environment.id if environment else None)
        if threshold is None:
            threshold = self._create_threshold(project, environment)

        updates: dict[str, Any] = {}
        data = payload.model_dump(exclude_unset=True)
        if "offline_seconds" in data and data["offline_seconds"] is not None:
            threshold.offline_seconds = int(data["offline_seconds"])
            updates["offline_seconds"] = threshold.offline_seconds
        if "backlog_threshold" in data and data["backlog_threshold"] is not None:
            threshold.backlog_threshold = int(data["backlog_threshold"])
            updates["backlog_threshold"] = threshold.backlog_threshold
        if "latency_threshold_ms" in data and data["latency_threshold_ms"] is not None:
            threshold.latency_threshold_ms = int(data["latency_threshold_ms"])
            updates["latency_threshold_ms"] = threshold.latency_threshold_ms

        if not updates:
            return threshold

        self.session.add(threshold)
        record_audit_log(
            self.session,
            actor=self.actor,
            action="agent.threshold_updated",
            resource_type="agent_threshold",
            resource_id=str(threshold.id),
            project_id=project.id,
            metadata={**updates, "environment_id": str(environment.id) if environment else None},
            ip=self.client_ip,
            user_agent=self.user_agent,
        )
        self.session.commit()
        self.session.refresh(threshold)
        return threshold


__all__ = ["AgentThresholdService"]
