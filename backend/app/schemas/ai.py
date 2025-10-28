from __future__ import annotations

from typing import Any
from uuid import UUID

from pydantic import BaseModel, model_validator


class GenerateCasesRequest(BaseModel):
    project_id: UUID
    api_spec: dict[str, Any] | str


class GenerateAssertionsRequest(BaseModel):
    project_id: UUID
    example_response: dict[str, Any] | str


class GenerateMockDataRequest(BaseModel):
    project_id: UUID
    json_schema: dict[str, Any]


class SummarizeReportRequest(BaseModel):
    project_id: UUID
    report_id: UUID | None = None
    report: dict[str, Any] | None = None

    @model_validator(mode="after")
    def validate_source(cls, values: "SummarizeReportRequest") -> "SummarizeReportRequest":
        if not values.report_id and not values.report:
            raise ValueError("Either report_id or report must be provided")
        return values
