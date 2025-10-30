from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Iterable, Sequence

from fastapi import status
from sqlalchemy import Select, desc, select
from sqlalchemy.orm import Session, joinedload

from app.core.api_tokens import format_token, generate_token_components, hash_token_secret
from app.core.errors import ErrorCode, http_exception
from app.logging import get_logger
from app.models import (
    Agent,
    AgentAlertState,
    AgentHeartbeat,
    AgentQueueMembership,
    AgentStatus,
    Environment,
    Project,
    ProjectMember,
    ProjectRole,
    User,
    UserRole,
)
from app.observability.metrics import record_agent_metrics
from app.schemas.agent import AgentHeartbeatRequest
from app.services.agents.security import enforce_heartbeat_rate_limit
from app.services.audit_log import record_audit_log

logger = get_logger().bind(component="agent-service")


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _normalize_tags(values: Iterable[str]) -> list[str]:
    normalized: list[str] = []
    seen: set[str] = set()
    for item in values:
        if not isinstance(item, str):
            continue
        candidate = item.strip()
        if not candidate:
            continue
        key = candidate.lower()
        if key in seen:
            continue
        seen.add(key)
        normalized.append(candidate)
    return normalized


class AgentService:
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

    # ------------------------------------------------------------------
    # Core utilities
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

    def _ensure_project_membership(self, project: Project) -> ProjectMember | None:
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

    def _require_project_admin(self, project: Project) -> None:
        membership = self._ensure_project_membership(project)
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

    def _generate_unique_token(self) -> tuple[str, str]:
        while True:
            prefix, secret = generate_token_components()
            exists = (
                self.session.execute(select(Agent.id).where(Agent.token_prefix == prefix, Agent.is_deleted.is_(False)))
                .scalar_one_or_none()
            )
            if exists is None:
                return prefix, secret

    def _assert_unique_name(self, project_id: uuid.UUID | None, name: str, *, exclude_agent_id: uuid.UUID | None = None) -> None:
        stmt = select(Agent.id).where(Agent.name == name, Agent.is_deleted.is_(False))
        if project_id is None:
            stmt = stmt.where(Agent.project_id.is_(None))
        else:
            stmt = stmt.where(Agent.project_id == project_id)
        if exclude_agent_id is not None:
            stmt = stmt.where(Agent.id != exclude_agent_id)
        exists = self.session.execute(stmt.limit(1)).scalar_one_or_none()
        if exists is not None:
            raise http_exception(
                status.HTTP_400_BAD_REQUEST,
                ErrorCode.BAD_REQUEST,
                "Agent name already exists for project",
            )

    # ------------------------------------------------------------------
    # Mutations
    # ------------------------------------------------------------------

    def create_agent(
        self,
        *,
        name: str,
        project_id: uuid.UUID | None,
        environment_id: uuid.UUID | None,
        env_tags: Sequence[str] | None,
        capabilities: dict[str, Any] | None,
    ) -> tuple[Agent, str]:
        self._ensure_authenticated()
        project: Project | None = None
        environment: Environment | None = None
        if project_id is not None:
            project = self._load_project(project_id)
            self._require_project_admin(project)
            environment = self._load_environment(project, environment_id)
        else:
            if self.actor is None or self.actor.role != UserRole.ADMIN:
                raise http_exception(
                    status.HTTP_400_BAD_REQUEST,
                    ErrorCode.BAD_REQUEST,
                    "Agents must belong to a project",
                )

        clean_name = name.strip()
        if not clean_name:
            raise http_exception(status.HTTP_400_BAD_REQUEST, ErrorCode.BAD_REQUEST, "Agent name is required")
        self._assert_unique_name(project.id if project else None, clean_name)

        prefix, secret = self._generate_unique_token()
        now = _now()
        agent = Agent(
            project_id=project.id if project else None,
            environment_id=environment.id if environment else None,
            name=clean_name,
            env_tags=_normalize_tags(env_tags or []),
            status=AgentStatus.OFFLINE,
            enabled=True,
            capabilities=(capabilities or {}),
            token_prefix=prefix,
            token_hash=hash_token_secret(secret),
            token_last_rotated_at=now,
            last_heartbeat_at=None,
            health_metadata={},
        )
        self.session.add(agent)
        record_audit_log(
            self.session,
            actor=self.actor,
            action="agent.created",
            resource_type="agent",
            resource_id=str(agent.id),
            project_id=agent.project_id,
            metadata={
                "name": agent.name,
                "environment_id": str(agent.environment_id) if agent.environment_id else None,
                "env_tags": agent.env_tags,
            },
            ip=self.client_ip,
            user_agent=self.user_agent,
        )
        self.session.commit()
        self.session.refresh(agent)
        return agent, format_token(prefix, secret)

    def update_agent(self, agent: Agent, *, updates: dict[str, Any]) -> Agent:
        self._ensure_authenticated()
        project: Project | None = None
        if agent.project_id:
            project = self._load_project(agent.project_id)
            self._require_project_admin(project)
        elif self.actor.role != UserRole.ADMIN:
            raise http_exception(
                status.HTTP_403_FORBIDDEN,
                ErrorCode.NO_PERMISSION,
                "Only system administrators can modify global agents",
            )

        if "name" in updates and updates["name"] is not None:
            new_name = str(updates["name"]).strip()
            if not new_name:
                raise http_exception(status.HTTP_400_BAD_REQUEST, ErrorCode.BAD_REQUEST, "Agent name cannot be empty")
            self._assert_unique_name(agent.project_id, new_name, exclude_agent_id=agent.id)
            agent.name = new_name

        if "env_tags" in updates and updates["env_tags"] is not None:
            agent.env_tags = _normalize_tags(updates["env_tags"] or [])

        if "capabilities" in updates:
            agent.capabilities = dict(updates["capabilities"] or {})

        if "environment_id" in updates:
            environment = self._load_environment(project, updates["environment_id"]) if project else None
            agent.environment_id = environment.id if environment else None

        if "enabled" in updates and updates["enabled"] is not None:
            enabled = bool(updates["enabled"])
            agent.enabled = enabled
            if not enabled:
                agent.status = AgentStatus.DISABLED
            elif agent.status == AgentStatus.DISABLED:
                agent.status = AgentStatus.OFFLINE

        self.session.add(agent)
        record_audit_log(
            self.session,
            actor=self.actor,
            action="agent.updated",
            resource_type="agent",
            resource_id=str(agent.id),
            project_id=agent.project_id,
            metadata=updates,
            ip=self.client_ip,
            user_agent=self.user_agent,
        )
        self.session.commit()
        self.session.refresh(agent)
        return agent

    def rotate_token(self, agent: Agent) -> tuple[Agent, str]:
        self._ensure_authenticated()
        if agent.project_id:
            project = self._load_project(agent.project_id)
            self._require_project_admin(project)
        elif self.actor.role != UserRole.ADMIN:
            raise http_exception(
                status.HTTP_403_FORBIDDEN,
                ErrorCode.NO_PERMISSION,
                "Only system administrators can rotate this agent token",
            )

        prefix, secret = self._generate_unique_token()
        agent.token_prefix = prefix
        agent.token_hash = hash_token_secret(secret)
        agent.token_last_rotated_at = _now()
        agent.token_revoked_at = None

        self.session.add(agent)
        record_audit_log(
            self.session,
            actor=self.actor,
            action="agent.token_rotated",
            resource_type="agent",
            resource_id=str(agent.id),
            project_id=agent.project_id,
            metadata={"token_prefix": prefix},
            ip=self.client_ip,
            user_agent=self.user_agent,
        )
        self.session.commit()
        self.session.refresh(agent)
        return agent, format_token(prefix, secret)

    def revoke_token(self, agent: Agent) -> Agent:
        self._ensure_authenticated()
        if agent.project_id:
            project = self._load_project(agent.project_id)
            self._require_project_admin(project)
        elif self.actor.role != UserRole.ADMIN:
            raise http_exception(
                status.HTTP_403_FORBIDDEN,
                ErrorCode.NO_PERMISSION,
                "Only system administrators can revoke this agent token",
            )

        prefix, secret = self._generate_unique_token()
        agent.token_prefix = prefix
        agent.token_hash = hash_token_secret(secret)
        agent.token_revoked_at = _now()

        self.session.add(agent)
        record_audit_log(
            self.session,
            actor=self.actor,
            action="agent.token_revoked",
            resource_type="agent",
            resource_id=str(agent.id),
            project_id=agent.project_id,
            metadata={"token_prefix": prefix},
            ip=self.client_ip,
            user_agent=self.user_agent,
        )
        self.session.commit()
        self.session.refresh(agent)
        return agent

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------

    def list_agents(
        self,
        *,
        project_id: uuid.UUID | None = None,
        statuses: Sequence[AgentStatus] | None = None,
        tags: Sequence[str] | None = None,
        include_deleted: bool = False,
    ) -> list[Agent]:
        stmt: Select[tuple[Agent]] = select(Agent).options(joinedload(Agent.environment))
        if not include_deleted:
            stmt = stmt.where(Agent.is_deleted.is_(False))
        if project_id is not None:
            stmt = stmt.where(Agent.project_id == project_id)
        if statuses:
            stmt = stmt.where(Agent.status.in_(tuple(statuses)))
        agents = self.session.execute(stmt).scalars().all()
        if tags:
            required = {tag.strip().lower() for tag in tags if isinstance(tag, str) and tag.strip()}
            if required:
                filtered: list[Agent] = []
                for agent in agents:
                    agent_tags = {tag.lower() for tag in (agent.env_tags or [])}
                    if required.issubset(agent_tags):
                        filtered.append(agent)
                agents = filtered
        return agents

    def get_agent(self, agent_id: uuid.UUID) -> Agent:
        agent = self.session.get(Agent, agent_id)
        if agent is None or agent.is_deleted:
            raise http_exception(status.HTTP_404_NOT_FOUND, ErrorCode.NOT_FOUND, "Agent not found")
        return agent

    def get_agent_detail(self, agent_id: uuid.UUID, *, heartbeat_limit: int = 50) -> tuple[Agent, list[AgentHeartbeat], list[AgentQueueMembership], list[AgentAlertState]]:
        agent = self.get_agent(agent_id)
        heartbeats = (
            self.session.execute(
                select(AgentHeartbeat)
                .where(AgentHeartbeat.agent_id == agent.id)
                .order_by(desc(AgentHeartbeat.recorded_at))
                .limit(max(heartbeat_limit, 1))
            )
            .scalars()
            .all()
        )
        memberships = (
            self.session.execute(
                select(AgentQueueMembership)
                .where(
                    AgentQueueMembership.agent_id == agent.id,
                    AgentQueueMembership.is_deleted.is_(False),
                )
                .options(joinedload(AgentQueueMembership.queue))
            )
            .scalars()
            .all()
        )
        alert_states = (
            self.session.execute(
                select(AgentAlertState)
                .where(AgentAlertState.agent_id == agent.id, AgentAlertState.is_deleted.is_(False))
            )
            .scalars()
            .all()
        )
        return agent, heartbeats, memberships, alert_states

    def list_agent_queues(self, agent: Agent) -> list[AgentQueueMembership]:
        stmt = (
            select(AgentQueueMembership)
            .where(
                AgentQueueMembership.agent_id == agent.id,
                AgentQueueMembership.is_deleted.is_(False),
            )
            .options(joinedload(AgentQueueMembership.queue))
        )
        return self.session.execute(stmt).scalars().all()

    # ------------------------------------------------------------------
    # Heartbeats & metrics
    # ------------------------------------------------------------------

    def record_heartbeat(
        self,
        agent: Agent,
        payload: AgentHeartbeatRequest,
        *,
        client_ip: str | None,
        user_agent: str | None,
    ) -> Agent:
        if not agent.enabled or agent.status == AgentStatus.DISABLED:
            raise http_exception(
                status.HTTP_403_FORBIDDEN,
                ErrorCode.NO_PERMISSION,
                "Agent is disabled",
            )

        enforce_heartbeat_rate_limit(agent.id)

        now = _now()
        agent.last_heartbeat_at = now
        agent.last_version = payload.version
        agent.last_latency_ms = payload.latency_ms
        agent.last_cpu_pct = float(payload.cpu)
        agent.last_memory_pct = float(payload.mem)
        agent.last_load_avg = float(payload.load)
        agent.last_queue_depth = int(payload.queue_depth)
        agent.last_seen_ip = client_ip
        agent.last_seen_user_agent = user_agent
        agent.health_metadata = agent.health_metadata or {}
        agent.health_metadata.update({
            "heartbeat_received_at": now.isoformat(),
            "queue_depth": payload.queue_depth,
            "latency_ms": payload.latency_ms,
        })
        if agent.status != AgentStatus.DISABLED:
            agent.status = AgentStatus.ONLINE

        heartbeat = AgentHeartbeat(
            agent_id=agent.id,
            recorded_at=now,
            cpu_pct=float(payload.cpu),
            memory_pct=float(payload.mem),
            load_avg=float(payload.load),
            queue_depth=int(payload.queue_depth),
            latency_ms=int(payload.latency_ms),
            version=payload.version,
        )

        self.session.add(heartbeat)
        self.session.add(agent)
        self.session.commit()
        self.session.refresh(agent)

        record_agent_metrics(
            agent_id=str(agent.id),
            project_id=str(agent.project_id) if agent.project_id else None,
            status=agent.status,
            recorded_at=now,
            queue_depth=payload.queue_depth,
            latency_ms=payload.latency_ms,
        )
        return agent

    def summarize(
        self,
        *,
        project_id: uuid.UUID | None = None,
        environment_id: uuid.UUID | None = None,
        tags: Sequence[str] | None = None,
    ) -> dict[str, float | int | None]:
        stmt = select(Agent).where(Agent.is_deleted.is_(False))
        if project_id is not None:
            stmt = stmt.where(Agent.project_id == project_id)
        if environment_id is not None:
            stmt = stmt.where(Agent.environment_id == environment_id)
        agents = self.session.execute(stmt).scalars().all()

        if tags:
            required = {tag.strip().lower() for tag in tags if isinstance(tag, str) and tag.strip()}
            if required:
                agents = [
                    agent
                    for agent in agents
                    if required.issubset({tag.lower() for tag in (agent.env_tags or [])})
                ]

        total = len(agents)
        online = sum(1 for agent in agents if agent.status == AgentStatus.ONLINE)
        offline = sum(1 for agent in agents if agent.status == AgentStatus.OFFLINE)
        degraded = sum(1 for agent in agents if agent.status == AgentStatus.DEGRADED)
        disabled = sum(1 for agent in agents if agent.status == AgentStatus.DISABLED)

        def _average(values: Iterable[float | None]) -> float | None:
            collected = [float(value) for value in values if value is not None]
            if not collected:
                return None
            return round(sum(collected) / len(collected), 2)

        avg_latency = _average(agent.last_latency_ms for agent in agents)
        avg_queue_depth = _average(agent.last_queue_depth for agent in agents)
        avg_cpu = _average(agent.last_cpu_pct for agent in agents)
        avg_memory = _average(agent.last_memory_pct for agent in agents)
        capacity_utilization = avg_cpu

        return {
            "total": total,
            "online": online,
            "offline": offline,
            "degraded": degraded,
            "disabled": disabled,
            "avg_latency_ms": avg_latency,
            "avg_queue_depth": avg_queue_depth,
            "avg_cpu_pct": avg_cpu,
            "avg_memory_pct": avg_memory,
            "capacity_utilization": capacity_utilization,
        }


__all__ = ["AgentService"]
