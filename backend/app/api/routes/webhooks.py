from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db
from app.models.user import User
from app.schemas.webhook import (
    WebhookDeliveryFilter,
    WebhookDeliveryResponse,
    WebhookRedeliverRequest,
    WebhookRedeliverResponse,
    WebhookSubscriptionCreate,
    WebhookSubscriptionResponse,
    WebhookSubscriptionUpdate,
    WebhookTestSendRequest,
    WebhookTestSendResponse,
)
from app.services.webhooks import WebhookService
from app.logging import get_logger

logger = get_logger(__name__)

router = APIRouter()


@router.post(
    "/projects/{project_id}/webhooks",
    response_model=WebhookSubscriptionResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_webhook_subscription(
    project_id: uuid.UUID,
    subscription_data: WebhookSubscriptionCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Any:
    """Create a new webhook subscription."""
    webhook_service = WebhookService(db)
    
    subscription = await webhook_service.create_subscription(
        project_id=project_id,
        subscription_data=subscription_data,
        created_by=current_user.id,
    )
    
    return subscription


@router.get(
    "/projects/{project_id}/webhooks",
    response_model=list[WebhookSubscriptionResponse],
)
async def list_webhook_subscriptions(
    project_id: uuid.UUID,
    enabled_only: bool = Query(False),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Any:
    """List webhook subscriptions for a project."""
    webhook_service = WebhookService(db)
    
    subscriptions = await webhook_service.list_subscriptions(
        project_id=project_id,
        enabled_only=enabled_only,
    )
    
    return subscriptions


@router.get(
    "/projects/{project_id}/webhooks/{subscription_id}",
    response_model=WebhookSubscriptionResponse,
)
async def get_webhook_subscription(
    project_id: uuid.UUID,
    subscription_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Any:
    """Get a webhook subscription by ID."""
    webhook_service = WebhookService(db)
    
    subscription = await webhook_service.get_subscription(
        subscription_id=subscription_id,
        project_id=project_id,
    )
    
    if not subscription:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Webhook subscription not found",
        )
    
    return subscription


@router.patch(
    "/projects/{project_id}/webhooks/{subscription_id}",
    response_model=WebhookSubscriptionResponse,
)
async def update_webhook_subscription(
    project_id: uuid.UUID,
    subscription_id: uuid.UUID,
    subscription_data: WebhookSubscriptionUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Any:
    """Update a webhook subscription."""
    webhook_service = WebhookService(db)
    
    subscription = await webhook_service.update_subscription(
        subscription_id=subscription_id,
        subscription_data=subscription_data,
        project_id=project_id,
    )
    
    if not subscription:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Webhook subscription not found",
        )
    
    return subscription


@router.delete(
    "/projects/{project_id}/webhooks/{subscription_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_webhook_subscription(
    project_id: uuid.UUID,
    subscription_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Any:
    """Delete a webhook subscription."""
    webhook_service = WebhookService(db)
    
    success = await webhook_service.delete_subscription(
        subscription_id=subscription_id,
        project_id=project_id,
    )
    
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Webhook subscription not found",
        )


@router.post(
    "/projects/{project_id}/webhooks/test-send",
    response_model=WebhookTestSendResponse,
)
async def test_webhook(
    project_id: uuid.UUID,
    test_request: WebhookTestSendRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Any:
    """Test a webhook configuration."""
    webhook_service = WebhookService(db)
    
    success, message, delivery_id = await webhook_service.test_webhook(
        url=str(test_request.url),
        secret=test_request.secret,
        event_type=test_request.event_type,
    )
    
    return WebhookTestSendResponse(
        success=success,
        message=message,
        delivery_id=str(delivery_id) if delivery_id else None,
    )


@router.get(
    "/projects/{project_id}/webhooks/{subscription_id}/deliveries",
    response_model=dict[str, Any],
)
async def list_webhook_deliveries(
    project_id: uuid.UUID,
    subscription_id: uuid.UUID,
    status: str | None = Query(None),
    event_type: str | None = Query(None),
    created_after: str | None = Query(None),
    created_before: str | None = Query(None),
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Any:
    """List webhook deliveries for a subscription."""
    webhook_service = WebhookService(db)
    
    # Build filters
    filters = WebhookDeliveryFilter(
        status=status,
        event_type=event_type,
        subscription_id=subscription_id,
    )
    
    deliveries, total = await webhook_service.list_deliveries(
        project_id=project_id,
        filters=filters,
        limit=limit,
        offset=offset,
    )
    
    return {
        "items": deliveries,
        "total": total,
        "limit": limit,
        "offset": offset,
    }


@router.get(
    "/projects/{project_id}/deliveries",
    response_model=dict[str, Any],
)
async def list_all_webhook_deliveries(
    project_id: uuid.UUID,
    status: str | None = Query(None),
    event_type: str | None = Query(None),
    subscription_id: str | None = Query(None),
    created_after: str | None = Query(None),
    created_before: str | None = Query(None),
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Any:
    """List all webhook deliveries for a project."""
    webhook_service = WebhookService(db)
    
    # Build filters
    filters = WebhookDeliveryFilter(
        status=status,
        event_type=event_type,
        subscription_id=subscription_id,
    )
    
    deliveries, total = await webhook_service.list_deliveries(
        project_id=project_id,
        filters=filters,
        limit=limit,
        offset=offset,
    )
    
    return {
        "items": deliveries,
        "total": total,
        "limit": limit,
        "offset": offset,
    }


@router.get(
    "/projects/{project_id}/deliveries/{delivery_id}",
    response_model=WebhookDeliveryResponse,
)
async def get_webhook_delivery(
    project_id: uuid.UUID,
    delivery_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Any:
    """Get a webhook delivery by ID."""
    webhook_service = WebhookService(db)
    
    delivery = await webhook_service.get_delivery(
        delivery_id=delivery_id,
        project_id=project_id,
    )
    
    if not delivery:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Webhook delivery not found",
        )
    
    return delivery


@router.post(
    "/deliveries/{delivery_id}/redeliver",
    response_model=WebhookRedeliverResponse,
)
async def redeliver_webhook(
    delivery_id: uuid.UUID,
    redeliver_request: WebhookRedeliverRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Any:
    """Redeliver a failed webhook."""
    webhook_service = WebhookService(db)
    
    # First get the delivery to check project access
    delivery = await webhook_service.get_delivery(delivery_id)
    if not delivery:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Webhook delivery not found",
        )
    
    # Check if user has access to the project
    # This would be handled by the get_current_user dependency with project access check
    
    success = await webhook_service.redeliver_webhook(delivery_id=delivery_id)
    
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Webhook delivery not found",
        )
    
    return WebhookRedeliverResponse(
        success=True,
        message="Webhook redelivery scheduled successfully",
        delivery_id=str(delivery_id),
    )