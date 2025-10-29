from __future__ import annotations

import json
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy import and_, func, select
from sqlalchemy.orm import Session

from app.api.response import ResponseEnvelope, success_response
from app.core.authz import ProjectContext, get_current_user, get_project_context
from app.core.config import get_settings
from app.core.errors import ErrorCode, http_exception
from app.db.session import get_db
from app.logging import get_logger
from app.models.ai_chat import AiChat, AiChatMessage
from app.models.ai_task import AITask, TaskStatus, TaskType
from app.models.api import Api
from app.models.test_report import TestReport
from app.models.user import User
from app.schemas.ai import (
    GenerateAssertionsRequest,
    GenerateCasesRequest,
    GenerateMockDataRequest,
    SummarizeReportRequest,
)
from app.schemas.ai_chat import (
    ChatCompletionResponse,
    ChatContext,
    ChatMessageContent,
    ChatMessageRead,
    ChatRead,
    ChatRequest,
    ChatRole,
    ChatSummary,
    ChatTool,
    SaveGeneratedCasesRequest,
)
from app.schemas.test_case import TestCaseRead
from app.schemas.test_report import TestReportRead
from app.services.ai import get_ai_provider
from app.services.ai.base import AIProviderError, ProviderResponse
from app.services.ai.chat import build_test_case_models, generate_chat_title, normalize_cases
from app.services.redaction import sanitize_for_storage

router = APIRouter(prefix="/ai", tags=["ai"])
_logger = get_logger().bind(component="ai_routes")


def _ensure_project_context(db: Session, current_user: User, project_id: UUID) -> ProjectContext:
    return get_project_context(project_id=project_id, project_key=None, db=db, current_user=current_user)


def _create_task(
    db: Session,
    *,
    project_id: UUID,
    task_type: TaskType,
    provider_name: str,
    input_payload: dict[str, Any],
) -> AITask:
    task = AITask(
        project_id=project_id,
        task_type=task_type,
        provider=provider_name,
        status=TaskStatus.PENDING,
        input_payload=input_payload,
    )
    db.add(task)
    db.commit()
    db.refresh(task)
    return task


def _resolve_success(db: Session, task: AITask, result: ProviderResponse) -> AITask:
    task.status = TaskStatus.SUCCESS
    task.output_payload = result.payload
    task.error_message = None
    task.model = result.model
    if result.usage:
        task.prompt_tokens = result.usage.prompt_tokens
        task.completion_tokens = result.usage.completion_tokens
        task.total_tokens = result.usage.total_tokens
    else:
        task.prompt_tokens = None
        task.completion_tokens = None
        task.total_tokens = None
    db.add(task)
    db.commit()
    db.refresh(task)
    return task


def _resolve_failure(db: Session, task: AITask, message: str) -> None:
    task.status = TaskStatus.FAILED
    task.error_message = message
    task.model = None
    task.prompt_tokens = None
    task.completion_tokens = None
    task.total_tokens = None
    db.add(task)
    db.commit()


def _handle_provider_failure(task: AITask, exc: AIProviderError, db: Session) -> None:
    _logger.error(
        "ai_provider_error",
        task_id=str(task.id),
        provider=task.provider,
        code=exc.code.value,
        status_code=exc.status_code,
        message=exc.message,
    )
    _resolve_failure(db, task, exc.message)


def _handle_unexpected_failure(task: AITask, exc: Exception, db: Session) -> None:
    _logger.error("ai_provider_unexpected_error", task_id=str(task.id), provider=task.provider, error=str(exc))
    _resolve_failure(db, task, str(exc))


def _serialize_report(report: TestReport) -> dict[str, Any]:
    schema = TestReportRead.model_validate(report)
    return schema.model_dump(mode="json")


def _sanitize_message_payload(content: ChatMessageContent, settings) -> dict[str, Any]:
    payload = sanitize_for_storage(content.model_dump(mode="json"))
    encoded = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    if len(encoded) > settings.ai_chat_message_max_bytes:
        raise http_exception(
            status.HTTP_400_BAD_REQUEST,
            ErrorCode.BAD_REQUEST,
            "Message exceeds configured size limit",
        )
    return payload


def _enforce_chat_rate_limit(db: Session, user_id: UUID, settings) -> None:
    if settings.ai_chat_rate_limit_per_minute <= 0:
        return
    window_start = datetime.now(timezone.utc) - timedelta(minutes=1)
    count = (
        db.execute(
            select(func.count(AiChatMessage.id))
            .where(
                AiChatMessage.author_id == user_id,
                AiChatMessage.created_at >= window_start,
                AiChatMessage.is_deleted.is_(False),
            )
        )
        .scalar_one()
    )
    if count >= settings.ai_chat_rate_limit_per_minute:
        raise http_exception(
            status.HTTP_429_TOO_MANY_REQUESTS,
            ErrorCode.RATE_LIMIT_EXCEEDED,
            "AI chat rate limit exceeded",
        )


def _get_chat(db: Session, project_id: UUID, chat_id: UUID) -> AiChat:
    chat = db.get(AiChat, chat_id)
    if not chat or chat.project_id != project_id or chat.is_deleted:
        raise http_exception(status.HTTP_404_NOT_FOUND, ErrorCode.NOT_FOUND, "Chat session not found")
    return chat


def _get_chat_message(db: Session, chat_id: UUID, message_id: UUID) -> AiChatMessage:
    message = db.get(AiChatMessage, message_id)
    if not message or message.chat_id != chat_id or message.is_deleted:
        raise http_exception(status.HTTP_404_NOT_FOUND, ErrorCode.NOT_FOUND, "Chat message not found")
    return message


def _next_sequence(db: Session, chat_id: UUID) -> int:
    current = (
        db.execute(
            select(func.max(AiChatMessage.sequence)).where(
                AiChatMessage.chat_id == chat_id,
                AiChatMessage.is_deleted.is_(False),
            )
        )
        .scalar()
    )
    return (current or 0) + 1


def _get_api_for_project(db: Session, project_id: UUID, api_id: UUID | None) -> Api:
    if api_id is None:
        raise http_exception(status.HTTP_400_BAD_REQUEST, ErrorCode.BAD_REQUEST, "API identifier is required")
    api = db.get(Api, api_id)
    if not api or api.project_id != project_id or api.is_deleted:
        raise http_exception(status.HTTP_404_NOT_FOUND, ErrorCode.NOT_FOUND, "API definition not found")
    return api


def _build_api_spec(api: Api, context: ChatContext | None) -> dict[str, Any]:
    if context and context.openapi_spec:
        spec = deepcopy(context.openapi_spec)
    else:
        spec = {
            "id": str(api.id),
            "name": api.name,
            "method": api.method,
            "path": api.path,
            "version": api.version,
            "group_name": api.group_name,
            "headers": api.headers,
            "params": api.params,
            "body": api.body,
            "mock_example": api.mock_example,
        }
    if context and context.examples is not None:
        spec["examples"] = context.examples
    return spec


def _resolve_example_payload(api: Api, context: ChatContext | None) -> dict[str, Any] | None:
    if context and context.example_response is not None:
        return context.example_response
    if api.mock_example:
        return api.mock_example
    if context and isinstance(context.examples, dict):
        return context.examples
    return None


def _resolve_json_schema(context: ChatContext | None) -> dict[str, Any] | None:
    if context and context.json_schema is not None:
        return context.json_schema
    return None


@router.post("/generate-cases", response_model=ResponseEnvelope)
def generate_cases(
    payload: GenerateCasesRequest,
    provider_key: str | None = Query(default=None, alias="provider"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    provider = get_ai_provider(provider_key)
    _ensure_project_context(db, current_user, payload.project_id)
    input_payload = payload.model_dump(mode="json")
    task = _create_task(
        db,
        project_id=payload.project_id,
        task_type=TaskType.GENERATE_CASES,
        provider_name=provider.provider_name,
        input_payload=input_payload,
    )
    try:
        result = provider.generate_test_cases(payload.api_spec)
    except AIProviderError as exc:
        _handle_provider_failure(task, exc, db)
        raise http_exception(exc.status_code, exc.code, exc.message, data=exc.data) from exc
    except Exception as exc:  # pragma: no cover - safety fallback
        _handle_unexpected_failure(task, exc, db)
        raise http_exception(
            status.HTTP_502_BAD_GATEWAY,
            ErrorCode.AI_PROVIDER_ERROR,
            "Failed to generate test cases",
            data={"task_id": str(task.id)},
        ) from exc

    _resolve_success(db, task, result)
    payload_with_task = {"task_id": str(task.id), **result.payload}
    return success_response(payload_with_task)


@router.post("/generate-assertions", response_model=ResponseEnvelope)
def generate_assertions(
    payload: GenerateAssertionsRequest,
    provider_key: str | None = Query(default=None, alias="provider"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    provider = get_ai_provider(provider_key)
    _ensure_project_context(db, current_user, payload.project_id)
    input_payload = payload.model_dump(mode="json")
    task = _create_task(
        db,
        project_id=payload.project_id,
        task_type=TaskType.GENERATE_ASSERTIONS,
        provider_name=provider.provider_name,
        input_payload=input_payload,
    )
    try:
        result = provider.generate_assertions(payload.example_response)
    except AIProviderError as exc:
        _handle_provider_failure(task, exc, db)
        raise http_exception(exc.status_code, exc.code, exc.message, data=exc.data) from exc
    except Exception as exc:  # pragma: no cover - safety fallback
        _handle_unexpected_failure(task, exc, db)
        raise http_exception(
            status.HTTP_502_BAD_GATEWAY,
            ErrorCode.AI_PROVIDER_ERROR,
            "Failed to generate assertions",
            data={"task_id": str(task.id)},
        ) from exc

    _resolve_success(db, task, result)
    payload_with_task = {"task_id": str(task.id), **result.payload}
    return success_response(payload_with_task)


@router.post("/mock-data", response_model=ResponseEnvelope)
def generate_mock_data(
    payload: GenerateMockDataRequest,
    provider_key: str | None = Query(default=None, alias="provider"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    provider = get_ai_provider(provider_key)
    _ensure_project_context(db, current_user, payload.project_id)
    input_payload = payload.model_dump(mode="json")
    task = _create_task(
        db,
        project_id=payload.project_id,
        task_type=TaskType.GENERATE_MOCK,
        provider_name=provider.provider_name,
        input_payload=input_payload,
    )
    try:
        result = provider.generate_mock_data(payload.json_schema)
    except AIProviderError as exc:
        _handle_provider_failure(task, exc, db)
        raise http_exception(exc.status_code, exc.code, exc.message, data=exc.data) from exc
    except Exception as exc:  # pragma: no cover - safety fallback
        _handle_unexpected_failure(task, exc, db)
        raise http_exception(
            status.HTTP_502_BAD_GATEWAY,
            ErrorCode.AI_PROVIDER_ERROR,
            "Failed to generate mock data",
            data={"task_id": str(task.id)},
        ) from exc

    _resolve_success(db, task, result)
    payload_with_task = {"task_id": str(task.id), **result.payload}
    return success_response(payload_with_task)


@router.post("/summarize-report", response_model=ResponseEnvelope)
def summarize_report(
    payload: SummarizeReportRequest,
    provider_key: str | None = Query(default=None, alias="provider"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    provider = get_ai_provider(provider_key)
    _ensure_project_context(db, current_user, payload.project_id)

    report_payload: dict[str, Any]
    if payload.report is not None:
        if not isinstance(payload.report, dict):
            raise http_exception(status.HTTP_400_BAD_REQUEST, ErrorCode.BAD_REQUEST, "Report payload must be an object")
        report_payload = payload.report
    elif payload.report_id is not None:
        report = db.get(TestReport, payload.report_id)
        if not report or report.project_id != payload.project_id:
            raise http_exception(status.HTTP_404_NOT_FOUND, ErrorCode.NOT_FOUND, "Report not found for project")
        report_payload = _serialize_report(report)
    else:  # pragma: no cover - guarded by validator
        raise http_exception(status.HTTP_400_BAD_REQUEST, ErrorCode.BAD_REQUEST, "Report data required")

    input_payload = {
        **payload.model_dump(mode="json"),
        "resolved_report": report_payload,
    }

    task = _create_task(
        db,
        project_id=payload.project_id,
        task_type=TaskType.SUMMARIZE_REPORT,
        provider_name=provider.provider_name,
        input_payload=input_payload,
    )

    try:
        result = provider.summarize_report(report_payload)
    except AIProviderError as exc:
        _handle_provider_failure(task, exc, db)
        raise http_exception(exc.status_code, exc.code, exc.message, data=exc.data) from exc
    except Exception as exc:  # pragma: no cover - safety fallback
        _handle_unexpected_failure(task, exc, db)
        raise http_exception(
            status.HTTP_502_BAD_GATEWAY,
            ErrorCode.AI_PROVIDER_ERROR,
            "Failed to summarize report",
            data={"task_id": str(task.id)},
        ) from exc

    _resolve_success(db, task, result)
    payload_with_task = {"task_id": str(task.id), **result.payload}
    return success_response(payload_with_task)


@router.post("/chat", response_model=ResponseEnvelope)
def chat_completion(
    payload: ChatRequest,
    provider_key: str | None = Query(default=None, alias="provider"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    provider = get_ai_provider(provider_key)
    settings = get_settings()
    project_context = _ensure_project_context(db, current_user, payload.project_id)
    _enforce_chat_rate_limit(db, current_user.id, settings)

    tool = payload.tools[0] if payload.tools else None
    if payload.tools and len(payload.tools) > 1:
        _logger.warning("multiple_tools_requested", tools=[entry.value for entry in payload.tools])

    if payload.chat_id:
        chat = _get_chat(db, project_context.project.id, payload.chat_id)
    else:
        title_source = next(
            (message.content for message in payload.messages if message.role == ChatRole.USER),
            payload.messages[-1].content,
        )
        chat = AiChat(
            project_id=project_context.project.id,
            title=generate_chat_title(title_source),
            created_by=current_user.id,
        )
        db.add(chat)
        db.commit()
        db.refresh(chat)

    latest_message = payload.messages[-1]
    user_content = ChatMessageContent(kind="text", text=latest_message.content, tool=None)
    user_payload = _sanitize_message_payload(user_content, settings)
    user_sequence = _next_sequence(db, chat.id)
    user_record = AiChatMessage(
        chat_id=chat.id,
        role=ChatRole.USER.value,
        author_id=current_user.id,
        sequence=user_sequence,
        content=user_payload,
    )
    db.add(user_record)
    db.commit()
    db.refresh(user_record)

    assistant_content: ChatMessageContent
    provider_result: ProviderResponse | None = None

    try:
        if tool is None:
            assistant_content = ChatMessageContent(
                kind="text",
                text=(
                    "请选择一个可用的工具，例如 \"generate_cases\"、\"generate_assertions\"、\"generate_mock\" 或 \"summarize\"。"
                ),
                tool=None,
            )
        elif tool == ChatTool.GENERATE_CASES:
            chat_context = payload.context or ChatContext()
            api = _get_api_for_project(db, project_context.project.id, chat_context.api_id)
            api_spec = _build_api_spec(api, chat_context)
            provider_result = provider.generate_test_cases(api_spec)
            raw_cases = provider_result.payload.get("cases") if provider_result.payload else []
            normalized_cases = normalize_cases(raw_cases, api)
            assistant_content = ChatMessageContent(
                kind="cases",
                tool=tool,
                text=f"已为 {api.method} {api.path} 生成 {len(normalized_cases)} 个测试用例。",
                cases=normalized_cases,
                summary={
                    "api_id": str(api.id),
                    "case_count": len(normalized_cases),
                },
            )
        elif tool == ChatTool.GENERATE_ASSERTIONS:
            chat_context = payload.context or ChatContext()
            api = _get_api_for_project(db, project_context.project.id, chat_context.api_id)
            example_payload = _resolve_example_payload(api, chat_context)
            if example_payload is None:
                raise http_exception(
                    status.HTTP_400_BAD_REQUEST,
                    ErrorCode.BAD_REQUEST,
                    "示例响应数据缺失，无法生成断言",
                )
            provider_result = provider.generate_assertions(example_payload)
            assertions_payload = provider_result.payload.get("assertions") if provider_result.payload else []
            assistant_content = ChatMessageContent(
                kind="assertions",
                tool=tool,
                text=f"已为 {api.method} {api.path} 生成 {len(assertions_payload)} 条断言。",
                assertions=[item for item in assertions_payload if isinstance(item, dict)],
                summary={
                    "api_id": str(api.id),
                    "assertion_count": len(assertions_payload),
                },
            )
        elif tool == ChatTool.GENERATE_MOCK:
            chat_context = payload.context or ChatContext()
            schema_payload = _resolve_json_schema(chat_context)
            if schema_payload is None:
                raise http_exception(
                    status.HTTP_400_BAD_REQUEST,
                    ErrorCode.BAD_REQUEST,
                    "缺少 JSON Schema 数据，无法生成 Mock 数据",
                )
            provider_result = provider.generate_mock_data(schema_payload)
            assistant_content = ChatMessageContent(
                kind="mock",
                tool=tool,
                text="已生成示例 Mock 数据。",
                mock=provider_result.payload.get("data") if provider_result.payload else None,
            )
        elif tool == ChatTool.SUMMARIZE:
            chat_context = payload.context or ChatContext()
            report_payload: dict[str, Any]
            if chat_context.report is not None:
                if not isinstance(chat_context.report, dict):
                    raise http_exception(
                        status.HTTP_400_BAD_REQUEST,
                        ErrorCode.BAD_REQUEST,
                        "报告内容必须为对象",
                    )
                report_payload = chat_context.report
            elif chat_context.report_id is not None:
                report = db.get(TestReport, chat_context.report_id)
                if not report or report.project_id != project_context.project.id:
                    raise http_exception(
                        status.HTTP_404_NOT_FOUND,
                        ErrorCode.NOT_FOUND,
                        "报告不存在或不属于当前项目",
                    )
                report_payload = _serialize_report(report)
            else:
                raise http_exception(
                    status.HTTP_400_BAD_REQUEST,
                    ErrorCode.BAD_REQUEST,
                    "缺少报告数据，无法生成摘要",
                )
            provider_result = provider.summarize_report(report_payload)
            summary_payload = provider_result.payload if isinstance(provider_result.payload, dict) else {
                "markdown": provider_result.payload
            }
            assistant_content = ChatMessageContent(
                kind="summary",
                tool=tool,
                text="已生成测试报告摘要。",
                summary=summary_payload,
            )
        else:  # pragma: no cover - defensive
            assistant_content = ChatMessageContent(
                kind="text",
                tool=None,
                text="暂不支持所选工具。",
            )
    except AIProviderError as exc:
        _logger.error(
            "chat_tool_provider_error",
            tool=tool.value if tool else None,
            code=exc.code.value,
            message=exc.message,
        )
        raise http_exception(exc.status_code, exc.code, exc.message, data=exc.data) from exc
    except Exception as exc:  # pragma: no cover - safety fallback
        _logger.error(
            "chat_tool_unexpected_error",
            tool=tool.value if tool else None,
            error=str(exc),
        )
        raise http_exception(
            status.HTTP_502_BAD_GATEWAY,
            ErrorCode.AI_PROVIDER_ERROR,
            "AI 助手处理请求时出现错误",
        ) from exc

    assistant_payload = _sanitize_message_payload(assistant_content, settings)
    assistant_sequence = _next_sequence(db, chat.id)
    assistant_record = AiChatMessage(
        chat_id=chat.id,
        role=ChatRole.ASSISTANT.value,
        author_id=None,
        sequence=assistant_sequence,
        content=assistant_payload,
        tool_invoked=tool.value if tool else None,
    )
    db.add(assistant_record)
    db.commit()
    db.refresh(assistant_record)
    db.refresh(chat)

    messages = [
        ChatMessageRead.model_validate(user_record),
        ChatMessageRead.model_validate(assistant_record),
    ]
    chat_schema = ChatRead.model_validate(chat)
    usage_payload = provider_result.usage.as_dict() if provider_result and provider_result.usage else None
    completion = ChatCompletionResponse(
        chat=chat_schema,
        messages=messages,
        tool=tool,
        usage=usage_payload,
    )
    return success_response(completion.model_dump(mode="json"))


@router.get("/chats", response_model=ResponseEnvelope)
def list_chats(
    project_id: UUID = Query(..., description="Project identifier"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    project_context = _ensure_project_context(db, current_user, project_id)
    stmt = (
        select(
            AiChat,
            func.count(AiChatMessage.id).label("message_count"),
            func.max(AiChatMessage.created_at).label("last_message_at"),
        )
        .outerjoin(
            AiChatMessage,
            and_(
                AiChatMessage.chat_id == AiChat.id,
                AiChatMessage.is_deleted.is_(False),
            ),
        )
        .where(
            AiChat.project_id == project_context.project.id,
            AiChat.is_deleted.is_(False),
        )
        .group_by(AiChat.id)
        .order_by(func.max(AiChatMessage.created_at).desc().nullslast(), AiChat.created_at.desc())
    )
    rows = db.execute(stmt).all()
    items: list[dict[str, Any]] = []
    for chat, message_count, last_message_at in rows:
        summary = ChatSummary.model_validate(
            {
                "id": chat.id,
                "created_at": chat.created_at,
                "updated_at": chat.updated_at,
                "project_id": chat.project_id,
                "title": chat.title,
                "created_by": chat.created_by,
                "last_message_at": last_message_at,
                "message_count": int(message_count or 0),
            }
        )
        items.append(summary.model_dump(mode="json"))
    return success_response(items)


@router.get("/chats/{chat_id}", response_model=ResponseEnvelope)
def get_chat_detail(
    chat_id: UUID,
    project_id: UUID = Query(..., description="Project identifier"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    project_context = _ensure_project_context(db, current_user, project_id)
    chat = _get_chat(db, project_context.project.id, chat_id)
    messages = (
        db.execute(
            select(AiChatMessage)
            .where(
                AiChatMessage.chat_id == chat.id,
                AiChatMessage.is_deleted.is_(False),
            )
            .order_by(AiChatMessage.sequence.asc(), AiChatMessage.created_at.asc())
        )
        .scalars()
        .all()
    )
    chat_schema = ChatRead.model_validate(chat)
    message_payload = [ChatMessageRead.model_validate(item).model_dump(mode="json") for item in messages]
    return success_response(
        {
            "chat": chat_schema.model_dump(mode="json"),
            "messages": message_payload,
        }
    )


@router.post("/chats/{chat_id}/save-test-cases", response_model=ResponseEnvelope, status_code=status.HTTP_201_CREATED)
def save_generated_test_cases(
    chat_id: UUID,
    payload: SaveGeneratedCasesRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    settings = get_settings()
    project_context = _ensure_project_context(db, current_user, payload.project_id)
    chat = _get_chat(db, project_context.project.id, chat_id)
    message = _get_chat_message(db, chat.id, payload.message_id)
    content = ChatMessageContent.model_validate(message.content)
    if content.kind != "cases" or not content.cases:
        raise http_exception(status.HTTP_400_BAD_REQUEST, ErrorCode.BAD_REQUEST, "指定消息不包含可保存的测试用例")
    if content.saved_case_ids:
        raise http_exception(status.HTTP_409_CONFLICT, ErrorCode.CONFLICT, "该消息的测试用例已保存")

    api = _get_api_for_project(db, project_context.project.id, payload.api_id)
    generated_cases = content.cases or []
    if not generated_cases:
        raise http_exception(status.HTTP_400_BAD_REQUEST, ErrorCode.BAD_REQUEST, "没有可保存的测试用例")

    test_case_models = build_test_case_models(
        generated_cases,
        project_id=project_context.project.id,
        api_id=api.id,
        created_by=current_user.id,
    )
    for model in test_case_models:
        db.add(model)
    db.commit()
    for model in test_case_models:
        db.refresh(model)

    saved_ids = [case.id for case in test_case_models]
    content.saved_case_ids = saved_ids
    message.content = _sanitize_message_payload(content, settings)
    message.result_ref = json.dumps({"case_ids": [str(case_id) for case_id in saved_ids]})
    db.add(message)
    db.commit()
    db.refresh(message)

    cases_payload = [TestCaseRead.model_validate(case).model_dump(mode="json") for case in test_case_models]
    message_schema = ChatMessageRead.model_validate(message)
    return success_response(
        {
            "cases": cases_payload,
            "message": message_schema.model_dump(mode="json"),
        },
        message="Test cases saved",
    )
