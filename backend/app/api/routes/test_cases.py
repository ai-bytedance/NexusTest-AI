from __future__ import annotations

from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.response import ResponseEnvelope, success_response
from app.core.authz import ProjectContext, require_project_member
from app.core.errors import ErrorCode, http_exception
from app.db.session import get_db
from app.models.api import Api
from app.models.dataset import Dataset
from app.models.environment import Environment
from app.models.execution_queue import ExecutionQueue, ExecutionQueueKind
from app.models.execution_routing import AgentSelectionPolicy
from app.models.test_case import TestCase
from app.schemas.test_case import (
    TestCaseAssertionsUpdateRequest,
    TestCaseCreate,
    TestCaseRead,
    TestCaseUpdate,
)

router = APIRouter(prefix="/projects/{project_id}/test-cases", tags=["test-cases"])


def _get_test_case(db: Session, project_id: UUID, test_case_id: UUID) -> TestCase:
    test_case = db.execute(
        select(TestCase).where(
            TestCase.id == test_case_id,
            TestCase.project_id == project_id,
            TestCase.is_deleted.is_(False),
        )
    ).scalar_one_or_none()
    if not test_case:
        raise http_exception(status.HTTP_404_NOT_FOUND, ErrorCode.NOT_FOUND, "Test case not found")
    return test_case


def _validate_api_belongs_to_project(db: Session, project_id: UUID, api_id: UUID) -> None:
    api = db.execute(
        select(Api).where(
            Api.id == api_id,
            Api.project_id == project_id,
            Api.is_deleted.is_(False),
        )
    ).scalar_one_or_none()
    if not api:
        raise http_exception(status.HTTP_400_BAD_REQUEST, ErrorCode.BAD_REQUEST, "API does not belong to this project")


def _validate_environment_belongs_to_project(
    db: Session,
    project_id: UUID,
    environment_id: UUID | None,
) -> None:
    if environment_id is None:
        return
    environment = db.execute(
        select(Environment).where(
            Environment.id == environment_id,
            Environment.project_id == project_id,
            Environment.is_deleted.is_(False),
        )
    ).scalar_one_or_none()
    if environment is None:
        raise http_exception(status.HTTP_400_BAD_REQUEST, ErrorCode.BAD_REQUEST, "Environment not found in this project")


def _validate_dataset_belongs_to_project(
    db: Session,
    project_id: UUID,
    dataset_id: UUID | None,
) -> None:
    if dataset_id is None:
        return
    dataset = db.execute(
        select(Dataset).where(
            Dataset.id == dataset_id,
            Dataset.project_id == project_id,
            Dataset.is_deleted.is_(False),
        )
    ).scalar_one_or_none()
    if dataset is None:
        raise http_exception(status.HTTP_400_BAD_REQUEST, ErrorCode.BAD_REQUEST, "Dataset not found in this project")


def _validate_queue_belongs_to_project(
    db: Session,
    project_id: UUID,
    queue_id: UUID | None,
    expected_kind: ExecutionQueueKind,
    environment_id: UUID | None,
) -> ExecutionQueue | None:
    if queue_id is None:
        return None
    queue = db.execute(
        select(ExecutionQueue).where(
            ExecutionQueue.id == queue_id,
            ExecutionQueue.project_id == project_id,
            ExecutionQueue.is_deleted.is_(False),
        )
    ).scalar_one_or_none()
    if queue is None:
        raise http_exception(status.HTTP_400_BAD_REQUEST, ErrorCode.BAD_REQUEST, "Queue not found in this project")
    if queue.kind != expected_kind:
        raise http_exception(status.HTTP_400_BAD_REQUEST, ErrorCode.BAD_REQUEST, "Queue kind does not match entity type")
    if queue.environment_id is not None and queue.environment_id != environment_id:
        raise http_exception(status.HTTP_400_BAD_REQUEST, ErrorCode.BAD_REQUEST, "Queue is scoped to a different environment")
    return queue


def _normalize_agent_tags(tags: list[str] | None) -> list[str]:
    if not tags:
        return []
    normalized: list[str] = []
    seen: set[str] = set()
    for item in tags:
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


def _serialise_assertions(assertions: Any | None) -> list[dict[str, Any]]:
    if not assertions:
        return []
    serialised: list[dict[str, Any]] = []
    for item in assertions:
        if isinstance(item, BaseModel):
            serialised.append(item.model_dump(mode="json", exclude_none=True))
        elif isinstance(item, dict):
            serialised.append(dict(item))
    return serialised


@router.get("", response_model=ResponseEnvelope)
def list_test_cases(
    context: ProjectContext = Depends(require_project_member),
    db: Session = Depends(get_db),
) -> dict:
    test_cases = db.execute(
        select(TestCase).where(
            TestCase.project_id == context.project.id,
            TestCase.is_deleted.is_(False),
        )
    ).scalars().all()
    data = [TestCaseRead.model_validate(item) for item in test_cases]
    return success_response(data)


@router.post("", response_model=ResponseEnvelope, status_code=status.HTTP_201_CREATED)
def create_test_case(
    payload: TestCaseCreate,
    context: ProjectContext = Depends(require_project_member),
    db: Session = Depends(get_db),
) -> dict:
    _validate_api_belongs_to_project(db, context.project.id, payload.api_id)
    _validate_environment_belongs_to_project(db, context.project.id, payload.environment_id)
    _validate_dataset_belongs_to_project(db, context.project.id, payload.dataset_id)
    queue = _validate_queue_belongs_to_project(
        db,
        context.project.id,
        payload.queue_id,
        ExecutionQueueKind.CASE,
        payload.environment_id,
    )
    agent_tags = _normalize_agent_tags(payload.agent_tags)

    test_case = TestCase(
        project_id=context.project.id,
        api_id=payload.api_id,
        name=payload.name,
        inputs=payload.inputs,
        expected=payload.expected,
        assertions=_serialise_assertions(payload.assertions),
        environment_id=payload.environment_id,
        dataset_id=payload.dataset_id,
        queue_id=queue.id if queue else None,
        agent_selection_policy=payload.agent_selection_policy,
        agent_tags=agent_tags,
        param_mapping=payload.param_mapping or {},
        enabled=payload.enabled,
        created_by=context.membership.user_id,
    )
    db.add(test_case)
    db.commit()
    db.refresh(test_case)

    return success_response(TestCaseRead.model_validate(test_case))


@router.get("/{test_case_id}", response_model=ResponseEnvelope)
def get_test_case(
    test_case_id: UUID,
    context: ProjectContext = Depends(require_project_member),
    db: Session = Depends(get_db),
) -> dict:
    test_case = _get_test_case(db, context.project.id, test_case_id)
    return success_response(TestCaseRead.model_validate(test_case))


@router.patch("/{test_case_id}", response_model=ResponseEnvelope)
def update_test_case(
    test_case_id: UUID,
    payload: TestCaseUpdate,
    context: ProjectContext = Depends(require_project_member),
    db: Session = Depends(get_db),
) -> dict:
    test_case = _get_test_case(db, context.project.id, test_case_id)
    updates = payload.model_dump(exclude_unset=True)

    if "environment_id" in updates:
        _validate_environment_belongs_to_project(db, context.project.id, updates["environment_id"])
    if "dataset_id" in updates:
        _validate_dataset_belongs_to_project(db, context.project.id, updates["dataset_id"])
    if "environment_id" in updates and "queue_id" not in updates and test_case.queue_id is not None:
        _validate_queue_belongs_to_project(
            db,
            context.project.id,
            test_case.queue_id,
            ExecutionQueueKind.CASE,
            updates["environment_id"],
        )
    if "param_mapping" in updates and updates["param_mapping"] is None:
        updates["param_mapping"] = {}
    if "assertions" in updates:
        if updates["assertions"] is None:
            updates["assertions"] = []
        else:
            updates["assertions"] = _serialise_assertions(updates["assertions"])

    environment_id = updates.get("environment_id", test_case.environment_id)
    if "queue_id" in updates:
        queue_id_value = updates["queue_id"]
        if queue_id_value is None:
            updates["queue_id"] = None
        else:
            queue = _validate_queue_belongs_to_project(
                db,
                context.project.id,
                queue_id_value,
                ExecutionQueueKind.CASE,
                environment_id,
            )
            updates["queue_id"] = queue.id
    if "agent_tags" in updates:
        updates["agent_tags"] = _normalize_agent_tags(updates["agent_tags"]) if updates["agent_tags"] is not None else []
    if "agent_selection_policy" in updates:
        updates["agent_selection_policy"] = updates["agent_selection_policy"] or AgentSelectionPolicy.ROUND_ROBIN

    for field, value in updates.items():
        setattr(test_case, field, value)

    if test_case.param_mapping is None:
        test_case.param_mapping = {}

    db.add(test_case)
    db.commit()
    db.refresh(test_case)

    return success_response(TestCaseRead.model_validate(test_case))


@router.patch("/{test_case_id}/assertions", response_model=ResponseEnvelope)
def update_test_case_assertions(
    test_case_id: UUID,
    payload: TestCaseAssertionsUpdateRequest,
    context: ProjectContext = Depends(require_project_member),
    db: Session = Depends(get_db),
) -> dict:
    test_case = _get_test_case(db, context.project.id, test_case_id)
    raw_current = test_case.assertions or []
    if isinstance(raw_current, list):
        current = [dict(item) if isinstance(item, dict) else item for item in raw_current]
    elif isinstance(raw_current, dict):
        items = raw_current.get("items") if isinstance(raw_current, dict) else None
        current = [dict(item) for item in items] if isinstance(items, list) else []
    else:
        current = []

    if payload.operation == "replace":
        test_case.assertions = _serialise_assertions([item.assertion for item in payload.items])
    else:
        updated = list(current)
        for item in payload.items:
            serialised_list = _serialise_assertions([item.assertion])
            if not serialised_list:
                raise http_exception(status.HTTP_400_BAD_REQUEST, ErrorCode.BAD_REQUEST, "Invalid assertion payload")
            serialised = serialised_list[0]
            index = item.index if item.index is not None else len(updated)
            if index < 0:
                raise http_exception(status.HTTP_400_BAD_REQUEST, ErrorCode.BAD_REQUEST, "Index must be non-negative")
            if index < len(updated):
                updated[index] = serialised
            elif index == len(updated):
                updated.append(serialised)
            else:
                raise http_exception(status.HTTP_400_BAD_REQUEST, ErrorCode.BAD_REQUEST, "Index out of range for patch")
        test_case.assertions = updated

    db.add(test_case)
    db.commit()
    db.refresh(test_case)

    return success_response(TestCaseRead.model_validate(test_case))


@router.delete("/{test_case_id}", response_model=ResponseEnvelope)
def delete_test_case(
    test_case_id: UUID,
    context: ProjectContext = Depends(require_project_member),
    db: Session = Depends(get_db),
) -> dict:
    test_case = _get_test_case(db, context.project.id, test_case_id)
    test_case.is_deleted = True
    db.add(test_case)
    db.commit()

    return success_response({"id": test_case.id, "deleted": True})
