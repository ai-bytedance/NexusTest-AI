from __future__ import annotations

from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.api.response import ResponseEnvelope, success_response
from app.core.authz import ProjectContext, get_current_user, get_project_context
from app.core.errors import ErrorCode, http_exception
from app.db.session import get_db
from app.logging import get_logger
from app.models.ai_task import AITask, TaskStatus, TaskType
from app.models.test_report import TestReport
from app.models.user import User
from app.schemas.ai import (
    GenerateAssertionsRequest,
    GenerateCasesRequest,
    GenerateMockDataRequest,
    SummarizeReportRequest,
)
from app.schemas.test_report import TestReportRead
from app.services.ai import AIProvider, get_ai_provider
from app.services.ai.base import AIProviderError

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


def _resolve_success(db: Session, task: AITask, output_payload: dict[str, Any]) -> AITask:
    task.status = TaskStatus.SUCCESS
    task.output_payload = output_payload
    task.error_message = None
    db.add(task)
    db.commit()
    db.refresh(task)
    return task


def _resolve_failure(db: Session, task: AITask, message: str) -> None:
    task.status = TaskStatus.FAILED
    task.error_message = message
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


@router.post("/generate-cases", response_model=ResponseEnvelope)
def generate_cases(
    payload: GenerateCasesRequest,
    db: Session = Depends(get_db),
    provider: AIProvider = Depends(get_ai_provider),
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
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
    payload_with_task = {"task_id": str(task.id), **result}
    return success_response(payload_with_task)


@router.post("/generate-assertions", response_model=ResponseEnvelope)
def generate_assertions(
    payload: GenerateAssertionsRequest,
    db: Session = Depends(get_db),
    provider: AIProvider = Depends(get_ai_provider),
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
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
    payload_with_task = {"task_id": str(task.id), **result}
    return success_response(payload_with_task)


@router.post("/mock-data", response_model=ResponseEnvelope)
def generate_mock_data(
    payload: GenerateMockDataRequest,
    db: Session = Depends(get_db),
    provider: AIProvider = Depends(get_ai_provider),
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
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
    payload_with_task = {"task_id": str(task.id), **result}
    return success_response(payload_with_task)


@router.post("/summarize-report", response_model=ResponseEnvelope)
def summarize_report(
    payload: SummarizeReportRequest,
    db: Session = Depends(get_db),
    provider: AIProvider = Depends(get_ai_provider),
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
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
        markdown = provider.summarize_report(report_payload)
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

    output_payload = {"markdown": markdown}
    _resolve_success(db, task, output_payload)
    payload_with_task = {"task_id": str(task.id), **output_payload}
    return success_response(payload_with_task)
