from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, Field, model_validator

from app.schemas.common import IdentifierModel, ORMModel


class ChatRole(str, Enum):
    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"


class ChatTool(str, Enum):
    GENERATE_CASES = "generate_cases"
    GENERATE_ASSERTIONS = "generate_assertions"
    GENERATE_MOCK = "generate_mock"
    SUMMARIZE = "summarize"


class ChatMessageInput(BaseModel):
    role: ChatRole
    content: str = Field(min_length=1)


class ChatContext(BaseModel):
    api_id: UUID | None = None
    openapi_spec: dict[str, Any] | None = None
    example_response: dict[str, Any] | None = None
    json_schema: dict[str, Any] | None = None
    report_id: UUID | None = None
    report: dict[str, Any] | None = None
    examples: list[dict[str, Any]] | dict[str, Any] | None = None


class ChatRequest(BaseModel):
    project_id: UUID
    chat_id: UUID | None = None
    messages: list[ChatMessageInput] = Field(min_length=1)
    tools: list[ChatTool] | None = None
    context: ChatContext | None = None

    @model_validator(mode="after")
    def ensure_user_message(cls, values: "ChatRequest") -> "ChatRequest":
        if not values.messages:
            raise ValueError("At least one message is required")
        if values.messages[-1].role != ChatRole.USER:
            raise ValueError("The last message must be from the user")
        return values


class GeneratedCase(BaseModel):
    name: str
    description: str | None = None
    request: dict[str, Any] = Field(default_factory=dict)
    expected: dict[str, Any] = Field(default_factory=dict)
    assertions: list[dict[str, Any]] = Field(default_factory=list)
    metadata: dict[str, Any] | None = None


class ChatMessageContent(BaseModel):
    kind: Literal["text", "cases", "assertions", "mock", "summary", "system"]
    text: str | None = None
    cases: list[GeneratedCase] | None = None
    assertions: list[dict[str, Any]] | None = None
    mock: dict[str, Any] | None = None
    summary: dict[str, Any] | None = None
    tool: ChatTool | None = None
    saved_case_ids: list[UUID] | None = None


class ChatMessageRead(IdentifierModel):
    chat_id: UUID
    role: ChatRole
    sequence: int
    content: ChatMessageContent
    tool_invoked: ChatTool | None = None
    result_ref: str | None = None
    author_id: UUID | None


class ChatRead(IdentifierModel):
    project_id: UUID
    title: str
    created_by: UUID


class ChatSummary(ChatRead):
    last_message_at: datetime | None = None
    message_count: int = 0


class ChatCompletionResponse(ORMModel):
    chat: ChatRead
    messages: list[ChatMessageRead]
    tool: ChatTool | None = None
    usage: dict[str, int] | None = None


class SaveGeneratedCasesRequest(BaseModel):
    project_id: UUID
    message_id: UUID
    api_id: UUID


__all__ = [
    "ChatCompletionResponse",
    "ChatContext",
    "ChatMessageContent",
    "ChatMessageInput",
    "ChatMessageRead",
    "ChatRead",
    "ChatRequest",
    "ChatRole",
    "ChatSummary",
    "ChatTool",
    "GeneratedCase",
    "SaveGeneratedCasesRequest",
]
