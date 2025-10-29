from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.response import ResponseEnvelope, success_response
from app.core.authz import ProjectContext, require_project_member
from app.core.errors import ErrorCode, http_exception
from app.db.session import get_db
from app.models.api import Api
from app.models.dataset import Dataset
from app.models.environment import Environment
from app.models.test_case import TestCase
from app.schemas.test_case import TestCaseCreate, TestCaseRead, TestCaseUpdate

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

    test_case = TestCase(
        project_id=context.project.id,
        api_id=payload.api_id,
        name=payload.name,
        inputs=payload.inputs,
        expected=payload.expected,
        assertions=payload.assertions,
        environment_id=payload.environment_id,
        dataset_id=payload.dataset_id,
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
    if "param_mapping" in updates and updates["param_mapping"] is None:
        updates["param_mapping"] = {}

    for field, value in updates.items():
        setattr(test_case, field, value)

    if test_case.param_mapping is None:
        test_case.param_mapping = {}

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
