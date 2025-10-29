from __future__ import annotations

from typing import List
from uuid import UUID

from pydantic import Field

from app.models.execution_routing import AgentSelectionPolicy
from app.schemas.common import ORMModel


class ExecutionTriggerRequest(ORMModel):
    queue_id: UUID | None = None
    agent_tags: List[str] = Field(default_factory=list)
    agent_selection_policy: AgentSelectionPolicy | None = None
