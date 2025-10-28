from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.response import ResponseEnvelope, success_response
from app.core.authz import ProjectContext, require_project_member
from app.core.errors import ErrorCode, http_exception
from app.db.session import get_db
from app.models.test_suite import TestSuite
from app.schemas.test_suite import TestSuiteCreate, TestSuiteRead, TestSuiteUpdate

router = APIRouter(prefix="/projects/{project_id}/test-suites", tags=["test-suites"])


def _get_test_suite(db: Session, project_id: UUID, suite_id: UUID) -> TestSuite:
    suite = db.execute(
        select(TestSuite).where(
            TestSuite.id == suite_id,
            TestSuite.project_id == project_id,
            TestSuite.is_deleted.is_(False),
        )
    ).scalar_one_or_none()
    if not suite:
        raise http_exception(status.HTTP_404_NOT_FOUND, ErrorCode.NOT_FOUND, "Test suite not found")
    return suite


@router.get("", response_model=ResponseEnvelope)
def list_test_suites(
    context: ProjectContext = Depends(require_project_member),
    db: Session = Depends(get_db),
) -> dict:
    suites = db.execute(
        select(TestSuite).where(
            TestSuite.project_id == context.project.id,
            TestSuite.is_deleted.is_(False),
        )
    ).scalars().all()
    data = [TestSuiteRead.model_validate(item) for item in suites]
    return success_response(data)


@router.post("", response_model=ResponseEnvelope, status_code=status.HTTP_201_CREATED)
def create_test_suite(
    payload: TestSuiteCreate,
    context: ProjectContext = Depends(require_project_member),
    db: Session = Depends(get_db),
) -> dict:
    suite = TestSuite(
        project_id=context.project.id,
        name=payload.name,
        description=payload.description,
        steps=payload.steps,
        variables=payload.variables,
        created_by=context.membership.user_id,
    )
    db.add(suite)
    db.commit()
    db.refresh(suite)

    return success_response(TestSuiteRead.model_validate(suite))


@router.get("/{suite_id}", response_model=ResponseEnvelope)
def get_test_suite(
    suite_id: UUID,
    context: ProjectContext = Depends(require_project_member),
    db: Session = Depends(get_db),
) -> dict:
    suite = _get_test_suite(db, context.project.id, suite_id)
    return success_response(TestSuiteRead.model_validate(suite))


@router.patch("/{suite_id}", response_model=ResponseEnvelope)
def update_test_suite(
    suite_id: UUID,
    payload: TestSuiteUpdate,
    context: ProjectContext = Depends(require_project_member),
    db: Session = Depends(get_db),
) -> dict:
    suite = _get_test_suite(db, context.project.id, suite_id)
    updates = payload.model_dump(exclude_unset=True)

    for field, value in updates.items():
        setattr(suite, field, value)

    db.add(suite)
    db.commit()
    db.refresh(suite)

    return success_response(TestSuiteRead.model_validate(suite))


@router.delete("/{suite_id}", response_model=ResponseEnvelope)
def delete_test_suite(
    suite_id: UUID,
    context: ProjectContext = Depends(require_project_member),
    db: Session = Depends(get_db),
) -> dict:
    suite = _get_test_suite(db, context.project.id, suite_id)
    suite.is_deleted = True
    db.add(suite)
    db.commit()

    return success_response({"id": suite.id, "deleted": True})
