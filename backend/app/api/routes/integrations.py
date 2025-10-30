from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.response import ResponseEnvelope, success_response
from app.core.authz import ProjectContext, require_project_admin
from app.core.errors import ErrorCode, http_exception
from app.db.session import get_db
from app.models import (
    Integration,
    IntegrationProvider,
    IntegrationWebhook,
    IntegrationWebhookStatus,
)
from app.schemas.integration import IntegrationWebhookSettingsUpdate
from app.services.issue_tracking.webhook_service import (
    WebhookProcessingError,
    WebhookVerificationError,
    fail_webhook_event,
    parse_payload,
    process_webhook_event,
    record_webhook_event,
    verify_webhook_request,
)
router = APIRouter(tags=["integrations"])


def _load_integration(db: Session, integration_id: UUID, project_id: UUID) -> Integration:
    stmt = (
        select(Integration)
        .where(
            Integration.id == integration_id,
            Integration.project_id == project_id,
            Integration.is_deleted.is_(False),
        )
        .limit(1)
    )
    integration = db.execute(stmt).scalar_one_or_none()
    if integration is None:
        raise http_exception(status.HTTP_404_NOT_FOUND, ErrorCode.NOT_FOUND, "Integration not found")
    return integration


def _webhook_settings(config: dict[str, Any]) -> dict[str, Any]:
    webhook = dict(config.get("webhook") or {})
    if webhook.get("tolerance_seconds") is None:
        webhook["tolerance_seconds"] = 300
    return webhook


def _update_webhook_config(
    integration: Integration,
    *,
    enabled: bool | None = None,
    secret: str | None = None,
    url: str | None = None,
    tolerance_seconds: int | None = None,
    last_delivery: dict[str, Any] | None = None,
) -> None:
    config = dict(integration.config or {})
    webhook = _webhook_settings(config)
    if enabled is not None:
        webhook["enabled"] = bool(enabled)
    if secret is not None:
        webhook["secret"] = secret
    if url is not None:
        webhook["url"] = url
    if tolerance_seconds is not None:
        webhook["tolerance_seconds"] = max(30, min(int(tolerance_seconds), 3600))
    if last_delivery is not None:
        webhook["last_delivery"] = last_delivery
    config["webhook"] = webhook
    integration.config = config


def _select_candidate_integrations(db: Session, provider: IntegrationProvider) -> list[Integration]:
    stmt = (
        select(Integration)
        .where(
            Integration.provider == provider,
            Integration.enabled.is_(True),
            Integration.is_deleted.is_(False),
        )
        .order_by(Integration.created_at.desc())
    )
    return db.execute(stmt).scalars().unique().all()


@router.post("/integrations/{provider}/webhook", response_model=ResponseEnvelope)
async def receive_integration_webhook(
    provider: str,
    request: Request,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    try:
        provider_enum = IntegrationProvider(provider.lower())
    except ValueError:
        raise http_exception(status.HTTP_404_NOT_FOUND, ErrorCode.NOT_FOUND, "Unknown integration provider") from None

    body = await request.body()
    candidates = _select_candidate_integrations(db, provider_enum)
    if not candidates:
        raise http_exception(status.HTTP_404_NOT_FOUND, ErrorCode.NOT_FOUND, "No integrations registered for provider")

    verification_error: WebhookVerificationError | None = None
    matched_integration: Integration | None = None
    verification_details: dict[str, str] | None = None
    webhook_headers: dict[str, str] | None = None

    for integration in candidates:
        config = dict(integration.config or {})
        webhook = _webhook_settings(config)
        if not webhook.get("enabled") or not webhook.get("secret"):
            continue
        tolerance = int(webhook.get("tolerance_seconds") or 300)
        try:
            verification = verify_webhook_request(
                webhook.get("secret"),
                request.headers,
                body,
                tolerance_seconds=tolerance,
            )
            verification_details = verification
            webhook_headers = {key: request.headers[key] for key in request.headers.keys()}
            matched_integration = integration
            break
        except WebhookVerificationError as exc:  # pragma: no cover - only logged when mismatch
            verification_error = exc
            continue

    if matched_integration is None:
        message = "Webhook signature verification failed"
        detail = message if verification_error is None else str(verification_error)
        raise http_exception(status.HTTP_401_UNAUTHORIZED, ErrorCode.NO_PERMISSION, detail)

    try:
        payload = parse_payload(body)
    except WebhookProcessingError as exc:
        raise http_exception(status.HTTP_400_BAD_REQUEST, ErrorCode.BAD_REQUEST, str(exc)) from exc

    assert verification_details is not None  # for type checker
    assert webhook_headers is not None

    event, created = record_webhook_event(
        db,
        matched_integration,
        provider=provider_enum.value,
        payload=payload,
        headers=webhook_headers,
        signature=verification_details.get("signature"),
        idempotency_key=verification_details.get("idempotency_key", ""),
    )

    processed_issue: "Issue" | None = None
    status_value = event.status

    if created or event.status in {IntegrationWebhookStatus.PENDING, IntegrationWebhookStatus.PROCESSING}:
        try:
            processed_issue = process_webhook_event(db, event, provider=provider_enum.value)
            status_value = event.status
        except WebhookProcessingError as exc:
            fail_webhook_event(event, str(exc))
            status_value = event.status
            db.add(event)
    else:
        status_value = event.status

    last_delivery = {
        "event_id": str(event.id),
        "status": status_value.value,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    if event.error:
        last_delivery["error"] = event.error
    _update_webhook_config(matched_integration, last_delivery=last_delivery)
    db.add(matched_integration)
    db.add(event)
    if processed_issue is not None:
        db.add(processed_issue)
    db.commit()

    response_payload = {
        "event_id": str(event.id),
        "status": status_value.value,
        "created": created,
        "issue_id": str(processed_issue.id) if processed_issue else None,
        "integration_id": str(matched_integration.id),
    }
    if event.error:
        response_payload["error"] = event.error
    return success_response(response_payload)


@router.post(
    "/projects/{project_id}/integrations/webhooks/{webhook_id}/reprocess",
    response_model=ResponseEnvelope,
)
def reprocess_webhook_event(
    webhook_id: UUID,
    context: ProjectContext = Depends(require_project_admin),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    stmt = (
        select(IntegrationWebhook)
        .where(
            IntegrationWebhook.id == webhook_id,
            IntegrationWebhook.project_id == context.project.id,
            IntegrationWebhook.is_deleted.is_(False),
        )
        .limit(1)
    )
    event = db.execute(stmt).scalar_one_or_none()
    if event is None:
        raise http_exception(status.HTTP_404_NOT_FOUND, ErrorCode.NOT_FOUND, "Webhook event not found")

    integration = None
    if event.integration_id:
        integration = _load_integration(db, event.integration_id, context.project.id)

    provider_value = event.provider
    try:
        processed_issue = process_webhook_event(db, event, provider=provider_value)
        status_value = event.status.value
    except WebhookProcessingError as exc:
        fail_webhook_event(event, str(exc))
        status_value = event.status.value
        processed_issue = None

    last_delivery = {
        "event_id": str(event.id),
        "status": status_value,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    if event.error:
        last_delivery["error"] = event.error
    if integration is not None:
        _update_webhook_config(integration, last_delivery=last_delivery)
        db.add(integration)

    db.add(event)
    if processed_issue is not None:
        db.add(processed_issue)
    db.commit()

    payload = {
        "event_id": str(event.id),
        "status": event.status.value,
        "issue_id": str(processed_issue.id) if processed_issue else None,
        "error": event.error,
    }
    return success_response(payload)


@router.patch(
    "/projects/{project_id}/integrations/{integration_id}",
    response_model=ResponseEnvelope,
)
def update_integration_settings(
    integration_id: UUID,
    payload: IntegrationWebhookSettingsUpdate,
    context: ProjectContext = Depends(require_project_admin),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    integration = _load_integration(db, integration_id, context.project.id)
    updates = payload.model_dump(exclude_unset=True)
    webhook_updates = updates.get("webhook")
    if webhook_updates:
        _update_webhook_config(
            integration,
            enabled=webhook_updates.get("enabled"),
            secret=webhook_updates.get("secret"),
            url=webhook_updates.get("url"),
            tolerance_seconds=webhook_updates.get("tolerance_seconds"),
        )
    db.add(integration)
    db.commit()
    db.refresh(integration)
    return success_response({
        "id": str(integration.id),
        "project_id": str(integration.project_id),
        "provider": integration.provider.value,
        "config": integration.config,
        "enabled": integration.enabled,
    })


__all__ = ["router"]
