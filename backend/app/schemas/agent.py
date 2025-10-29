from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import Field

from app.models.agent import AgentStatus
from app.schemas.common import IdentifierModel, ORMModel


class AgentBase(ORMModel):
    name: str = Field(min_length=1, max_length=255)
    env_tags: list[str] = Field(default_factory=list)
    capabilities: dict[str, Any] = Field(default_factory=dict)


class AgentCreate(AgentBase):
    project_id: UUID | None = None


class AgentUpdate(ORMModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    env_tags: list[str] | None = None
    capabilities: dict[str, Any] | None = None
    status: AgentStatus | None = None


class AgentRead(IdentifierModel):
    project_id: UUID | None
    name: str
    env_tags: list[str]
    status: AgentStatus
    last_heartbeat_at: datetime | None
    capabilities: dict[str, Any]
    token_prefix: str
    token_last_rotated_at: datetime
    last_seen_ip: str | None
    last_seen_user_agent: str | None


class AgentCreateResponse(ORMModel):
    agent: AgentRead
    token: str


class AgentRotateTokenResponse(ORMModel):
    agent: AgentRead
    token: str


class AgentHeartbeatResponse(ORMModel):
    agent: AgentRead
