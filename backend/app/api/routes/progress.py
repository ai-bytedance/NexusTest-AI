from __future__ import annotations

import asyncio
import json
import time
import uuid
from dataclasses import dataclass
from typing import AsyncIterator

from fastapi import APIRouter, Query, Request, WebSocket, WebSocketDisconnect, status
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import ErrorCode, http_exception
from app.core.security import decode_access_token
from app.db.session import SessionLocal
from app.models.project import Project
from app.models.project_member import ProjectMember
from app.models.test_report import TestReport
from app.models.user import User
from app.services.reports.progress import close_progress_subscription, subscribe_to_progress

router = APIRouter(tags=["progress"])

UNAUTHORIZED_CLOSE_CODE = 4401
FORBIDDEN_CLOSE_CODE = 4403
HEARTBEAT_INTERVAL_SECONDS = 25.0


@dataclass(slots=True)
class SubscriptionContext:
    user: User
    project: Project
    membership: ProjectMember
    report: TestReport


class SubscriptionError(Exception):
    def __init__(self, close_code: int, message: str) -> None:
        super().__init__(message)
        self.close_code = close_code
        self.message = message


@router.websocket("/ws/projects/{project_id}/reports/{report_id}")
async def stream_report_progress_ws(websocket: WebSocket, project_id: uuid.UUID, report_id: uuid.UUID) -> None:
    header_token = _normalize_token(websocket.headers.get("authorization"))
    query_token = _normalize_token(websocket.query_params.get("token"))
    session = SessionLocal()
    try:
        context = _authorize_subscription(header_token or query_token, project_id, report_id, session)
    except SubscriptionError as exc:  # pragma: no cover - handshake failure
        await websocket.close(code=exc.close_code, reason=exc.message)
        session.close()
        return
    finally:
        session.close()

    pubsub = await subscribe_to_progress(str(context.report.id))
    heartbeat_message = _heartbeat_payload(context.report.id)
    await websocket.accept()
    last_activity = time.monotonic()

    try:
        while True:
            message = await pubsub.get_message(ignore_subscribe_messages=True, timeout=1.0)
            now = time.monotonic()
            if message and message.get("type") == "message":
                data = message.get("data")
                if isinstance(data, bytes):
                    data = data.decode("utf-8", errors="replace")
                if isinstance(data, str):
                    await websocket.send_text(data)
                    last_activity = now
            elif now - last_activity >= HEARTBEAT_INTERVAL_SECONDS:
                await websocket.send_text(heartbeat_message)
                last_activity = now
            await asyncio.sleep(0.1)
    except WebSocketDisconnect:  # pragma: no cover - client disconnect
        pass
    finally:
        await close_progress_subscription(pubsub, str(context.report.id))


@router.get("/sse/projects/{project_id}/reports/{report_id}")
async def stream_report_progress_sse(
    project_id: uuid.UUID,
    report_id: uuid.UUID,
    request: Request,
    token: str | None = Query(default=None),
) -> StreamingResponse:
    session = SessionLocal()
    try:
        context = _authorize_subscription(token or _normalize_token(request.headers.get("authorization")), project_id, report_id, session)
    except SubscriptionError as exc:
        session.close()
        raise _subscription_error_to_http(exc) from exc
    finally:
        session.close()

    async def event_generator() -> AsyncIterator[str]:
        pubsub = await subscribe_to_progress(str(context.report.id))
        last_activity = time.monotonic()
        try:
            yield ": connected\n\n"
            while True:
                if await request.is_disconnected():
                    break
                message = await pubsub.get_message(ignore_subscribe_messages=True, timeout=1.0)
                now = time.monotonic()
                if message and message.get("type") == "message":
                    data = message.get("data")
                    if isinstance(data, bytes):
                        data = data.decode("utf-8", errors="replace")
                    if isinstance(data, str):
                        yield f"data: {data}\n\n"
                        last_activity = now
                elif now - last_activity >= HEARTBEAT_INTERVAL_SECONDS:
                    yield ": heartbeat\n\n"
                    last_activity = now
                await asyncio.sleep(0.1)
        finally:
            await close_progress_subscription(pubsub, str(context.report.id))

    headers = {
        "Cache-Control": "no-cache",
        "X-Accel-Buffering": "no",
    }
    return StreamingResponse(event_generator(), media_type="text/event-stream", headers=headers)


def _authorization_subject(token: str | None) -> uuid.UUID:
    normalized = _normalize_token(token)
    if not normalized:
        raise SubscriptionError(UNAUTHORIZED_CLOSE_CODE, "Authentication token is required")
    try:
        payload = decode_access_token(normalized)
    except ValueError as exc:  # pragma: no cover - token parsing
        raise SubscriptionError(UNAUTHORIZED_CLOSE_CODE, "Invalid authentication token") from exc
    subject = payload.get("sub")
    if not subject:
        raise SubscriptionError(UNAUTHORIZED_CLOSE_CODE, "Authentication token is invalid")
    try:
        return uuid.UUID(str(subject))
    except ValueError as exc:  # pragma: no cover - malformed uuid
        raise SubscriptionError(UNAUTHORIZED_CLOSE_CODE, "Authentication token is invalid") from exc


def _authorize_subscription(
    token: str | None,
    project_id: uuid.UUID,
    report_id: uuid.UUID,
    session: Session,
) -> SubscriptionContext:
    user_id = _authorization_subject(token)

    user = session.get(User, user_id)
    if not user or user.is_deleted:
        raise SubscriptionError(UNAUTHORIZED_CLOSE_CODE, "Authentication credentials are invalid")

    project = session.get(Project, project_id)
    if not project or project.is_deleted:
        raise SubscriptionError(FORBIDDEN_CLOSE_CODE, "Project not found")

    membership_stmt = select(ProjectMember).where(
        ProjectMember.project_id == project_id,
        ProjectMember.user_id == user_id,
        ProjectMember.is_deleted.is_(False),
    )
    membership = session.execute(membership_stmt).scalar_one_or_none()
    if membership is None:
        raise SubscriptionError(FORBIDDEN_CLOSE_CODE, "You do not have access to this project")

    report = session.get(TestReport, report_id)
    if not report or report.is_deleted or report.project_id != project_id:
        raise SubscriptionError(FORBIDDEN_CLOSE_CODE, "Report not found for project")

    return SubscriptionContext(user=user, project=project, membership=membership, report=report)


def _subscription_error_to_http(exc: SubscriptionError):
    if exc.close_code == UNAUTHORIZED_CLOSE_CODE:
        return http_exception(status.HTTP_401_UNAUTHORIZED, ErrorCode.NOT_AUTHENTICATED, exc.message)
    if exc.close_code == FORBIDDEN_CLOSE_CODE:
        return http_exception(status.HTTP_403_FORBIDDEN, ErrorCode.NO_PERMISSION, exc.message)
    return http_exception(status.HTTP_400_BAD_REQUEST, ErrorCode.BAD_REQUEST, exc.message)


def _normalize_token(raw: str | None) -> str | None:
    if not raw:
        return None
    value = raw.strip()
    if not value:
        return None
    if value.lower().startswith("bearer "):
        value = value[7:]
    return value.strip() or None


def _heartbeat_payload(report_id: uuid.UUID) -> str:
    payload = {
        "type": "step_progress",
        "report_id": str(report_id),
        "payload": {"status": "heartbeat"},
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
