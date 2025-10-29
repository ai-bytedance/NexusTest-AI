from __future__ import annotations

import io
from datetime import datetime
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, status
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.authz import get_current_user, get_project_context
from app.core.errors import ErrorCode, http_exception
from app.db.session import get_db
from app.models.api import Api
from app.models.test_case import TestCase
from app.models.user import User
from app.schemas.export import PytestExportRequest
from app.services.exports import generate_pytest_archive

router = APIRouter(prefix="/exports", tags=["exports"])


@router.post("/pytest", response_class=StreamingResponse, status_code=status.HTTP_200_OK)
def export_pytest_suite(
    payload: PytestExportRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> StreamingResponse:
    context = get_project_context(project_id=payload.project_id, db=db, current_user=current_user)

    if not payload.case_ids:
        raise http_exception(status.HTTP_400_BAD_REQUEST, ErrorCode.BAD_REQUEST, "No test cases selected")

    stmt = select(TestCase).where(
        TestCase.id.in_(payload.case_ids),
        TestCase.project_id == context.project.id,
        TestCase.is_deleted.is_(False),
    )
    retrieved_cases = {case.id: case for case in db.execute(stmt).scalars()}
    ordered_cases: list[TestCase] = []
    for case_id in payload.case_ids:
        case = retrieved_cases.get(case_id)
        if case is None:
            raise http_exception(status.HTTP_404_NOT_FOUND, ErrorCode.NOT_FOUND, "Test case not found in project")
        if case not in ordered_cases:
            ordered_cases.append(case)

    api_ids = {case.api_id for case in ordered_cases}
    api_stmt = select(Api).where(
        Api.id.in_(api_ids),
        Api.project_id == context.project.id,
        Api.is_deleted.is_(False),
    )
    api_map = {api.id: api for api in db.execute(api_stmt).scalars()}
    if len(api_map) != len(api_ids):
        raise http_exception(status.HTTP_404_NOT_FOUND, ErrorCode.NOT_FOUND, "Associated API definitions missing")

    archive_bytes = generate_pytest_archive(
        project_name=context.project.name or context.project.key or "project",
        cases=ordered_cases,
        api_map=api_map,
    )

    timestamp = datetime.utcnow().strftime("%Y%m%d%H%M%S")
    filename = f"{_slugify_filename(context.project.name or context.project.key)}_pytest_{timestamp}.zip"

    response = StreamingResponse(io.BytesIO(archive_bytes), media_type="application/zip")
    response.headers["Content-Disposition"] = f"attachment; filename=\"{filename}\""
    return response


def _slugify_filename(value: str | None) -> str:
    if not value:
        return "export"
    sanitized = value.strip().lower()
    sanitized = "".join(char if char.isalnum() else "_" for char in sanitized)
    sanitized = "_".join(filter(None, sanitized.split("_")))
    return sanitized or "export"
