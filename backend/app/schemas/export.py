from __future__ import annotations

from typing import List
from uuid import UUID

from pydantic import BaseModel, Field


class PytestExportRequest(BaseModel):
    project_id: UUID
    case_ids: List[UUID] = Field(min_length=1)


__all__ = ["PytestExportRequest"]
