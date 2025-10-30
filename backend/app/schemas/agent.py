from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import Field, field_validator

from app.models.agent import AgentAlertKind, AgentStatus
from app.schemas.common import IdentifierModel, ORMModel


def _normalize_tags(value: list[str] | str | None) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        candidates = [value]
    else:
        candidates = list(value)
    normalized: list[str] = []
    seen: set[str] = set()
    for item in candidates:
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


class AgentBase(ORMModel):
    name: str = Field(min_length=1, max_length=255)
    env_tags: list[str] = Field(default_factory=list)
    capabilities: dict[str, Any] = Field(default_factory=dict)

    @field_validator("env_tags", mode="before")
    @classmethod
    def validate_env_tags(cls, value: list[str] | str | None) -> list[str]:
        return _normalize_tags(value)


class AgentCreate(AgentBase):
    project_id: UUID | None = None
    environment_id: UUID | None = None


class AgentUpdate(ORMModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    env_tags: list[str] | None = None
    capabilities: dict[str, Any] | None = None
    enabled: bool | None = None
    environment_id: UUID | None = None

    @field_validator("env_tags", mode="before")
    @classmethod
    def validate_update_env_tags(cls, value: list[str] | str | None) -> list[str] | None:
        if value is None:
            return None
        return _normalize_tags(value)


class AgentRead(IdentifierModel):
    project_id: UUID | None
    environment_id: UUID | None
    name: str
    env_tags: list[str]
    status: AgentStatus
    enabled: bool
    last_heartbeat_at: datetime | None
    last_version: str | None
    last_latency_ms: int | None
    last_cpu_pct: float | None
    last_memory_pct: float | None
    last_load_avg: float | None
    last_queue_depth: int | None
    capabilities: dict[str, Any]
    health_metadata: dict[str, Any]
    token_prefix: str
    token_last_rotated_at: datetime
    token_revoked_at: datetime | None
    last_seen_ip: str | None
    last_seen_user_agent: str | None


class AgentCreateResponse(ORMModel):
    agent: AgentRead
    token: str


class AgentRotateTokenResponse(ORMModel):
    agent: AgentRead
    token: str


class AgentHeartbeatRequest(ORMModel):
    cpu: float = Field(ge=0, le=100)
    mem: float = Field(ge=0, le=100)
    load: float = Field(ge=0)
    queue_depth: int = Field(ge=0)
    latency_ms: int = Field(ge=0)
    version: str | None = Field(default=None, max_length=64)


class AgentHeartbeatRead(ORMModel):
    recorded_at: datetime
    cpu_pct: float | None = None
    memory_pct: float | None = None
    load_avg: float | None = None
    queue_depth: int | None = None
    latency_ms: int | None = None
    version: str | None = None


class AgentAlertStateRead(IdentifierModel):
    agent_id: UUID
    kind: AgentAlertKind
    active: bool
    last_triggered_at: datetime | None
    last_cleared_at: datetime | None
    context: dict[str, Any]


class AgentQueueInfo(ORMModel):
    id: UUID
    name: str
    routing_key: str
    kind: str
    enabled: bool
    labels: dict[str, list[str]] | None = None


class AgentQueueMembershipRead(IdentifierModel):
    agent_id: UUID
    queue: AgentQueueInfo
    capacity: int | None = None
    weight: int | None = None
    enabled: bool
    metadata: dict[str, Any]


class AgentDetail(AgentRead):
    heartbeats: list[AgentHeartbeatRead] = Field(default_factory=list)
    queues: list[AgentQueueMembershipRead] = Field(default_factory=list)
    alert_states: list[AgentAlertStateRead] = Field(default_factory=list)


class AgentHeartbeatResponse(ORMModel):
    agent: AgentRead


class AgentSummary(ORMModel):
    total: int
    online: int
    offline: int
    degraded: int
    disabled: int
    avg_latency_ms: float | None
    avg_queue_depth: float | None
    avg_cpu_pct: float | None
    avg_memory_pct: float | None
    capacity_utilization: float | None


class AgentThresholdRead(IdentifierModel):
    project_id: UUID
    environment_id: UUID | None
    offline_seconds: int
    backlog_threshold: int
    latency_threshold_ms: int
    metadata: dict[str, Any]


class AgentThresholdUpdate(ORMModel):
    offline_seconds: int | None = Field(default=None, ge=1)
    backlog_threshold: int | None = Field(default=None, ge=0)
    latency_threshold_ms: int | None = Field(default=None, ge=0)


class AgentTestAlertRequest(ORMModel):
    project_id: UUID
    environment_id: UUID | None = None
    kind: AgentAlertKind = AgentAlertKind.OFFLINE


__all__ = [
    "AgentBase",
    "AgentCreate",
    "AgentUpdate",
    "AgentRead",
    "AgentCreateResponse",
    "AgentRotateTokenResponse",
    "AgentHeartbeatRequest",
    "AgentHeartbeatRead",
    "AgentAlertStateRead",
    "AgentQueueInfo",
    "AgentQueueMembershipRead",
    "AgentDetail",
    "AgentHeartbeatResponse",
    "AgentSummary",
    "AgentThresholdRead",
    "AgentThresholdUpdate",
    "AgentTestAlertRequest",
]
