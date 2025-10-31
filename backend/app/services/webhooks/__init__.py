from __future__ import annotations

import hashlib
import hmac
import json
import secrets
import uuid
from datetime import datetime, timedelta
from typing import Any

import httpx
from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.logging import get_logger
from app.models.webhook import (
    WebhookDelivery,
    WebhookDeliveryStatus,
    WebhookEventType,
    WebhookSubscription,
)
from app.observability.metrics import record_webhook_delivery
from app.schemas.webhook import (
    WebhookDeliveryFilter,
    WebhookSubscriptionCreate,
    WebhookSubscriptionUpdate,
)

logger = get_logger(__name__)

# Constants
WEBHOOK_TIMEOUT = 30  # seconds
WEBHOOK_SIGNATURE_HEADER = "X-NT-Signature"
WEBHOOK_TIMESTAMP_HEADER = "X-NT-Timestamp"
WEBHOOK_EVENT_HEADER = "X-NT-Event"
WEBHOOK_DELIVERY_ID_HEADER = "X-NT-Delivery-ID"


class WebhookService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def create_subscription(
        self,
        project_id: uuid.UUID,
        subscription_data: WebhookSubscriptionCreate,
        created_by: uuid.UUID,
    ) -> WebhookSubscription:
        """Create a new webhook subscription."""
        subscription = WebhookSubscription(
            name=subscription_data.name,
            project_id=project_id,
            url=str(subscription_data.url),
            secret=subscription_data.secret,
            events=[event.value for event in subscription_data.events],
            enabled=subscription_data.enabled,
            headers=subscription_data.headers,
            retries_max=subscription_data.retries_max,
            backoff_strategy=subscription_data.backoff_strategy,
            created_by=created_by,
        )
        
        self.db.add(subscription)
        await self.db.commit()
        await self.db.refresh(subscription)
        
        logger.info(
            "webhook_subscription_created",
            subscription_id=str(subscription.id),
            project_id=str(project_id),
            name=subscription.name,
        )
        
        return subscription

    async def get_subscription(
        self,
        subscription_id: uuid.UUID,
        project_id: uuid.UUID | None = None,
    ) -> WebhookSubscription | None:
        """Get a webhook subscription by ID."""
        query = select(WebhookSubscription).where(
            and_(
                WebhookSubscription.id == subscription_id,
                WebhookSubscription.is_deleted.is_(False),
            )
        )
        
        if project_id:
            query = query.where(WebhookSubscription.project_id == project_id)
        
        result = await self.db.execute(query)
        return result.scalar_one_or_none()

    async def list_subscriptions(
        self,
        project_id: uuid.UUID,
        enabled_only: bool = False,
    ) -> list[WebhookSubscription]:
        """List webhook subscriptions for a project."""
        query = select(WebhookSubscription).where(
            and_(
                WebhookSubscription.project_id == project_id,
                WebhookSubscription.is_deleted.is_(False),
            )
        ).order_by(WebhookSubscription.created_at.desc())
        
        if enabled_only:
            query = query.where(WebhookSubscription.enabled.is_(True))
        
        result = await self.db.execute(query)
        return result.scalars().all()

    async def update_subscription(
        self,
        subscription_id: uuid.UUID,
        subscription_data: WebhookSubscriptionUpdate,
        project_id: uuid.UUID | None = None,
    ) -> WebhookSubscription | None:
        """Update a webhook subscription."""
        subscription = await self.get_subscription(subscription_id, project_id)
        if not subscription:
            return None
        
        update_data = subscription_data.model_dump(exclude_unset=True)
        
        if "url" in update_data:
            update_data["url"] = str(update_data["url"])
        if "events" in update_data:
            update_data["events"] = [event.value for event in update_data["events"]]
        
        for field, value in update_data.items():
            setattr(subscription, field, value)
        
        await self.db.commit()
        await self.db.refresh(subscription)
        
        logger.info(
            "webhook_subscription_updated",
            subscription_id=str(subscription_id),
            project_id=str(subscription.project_id),
        )
        
        return subscription

    async def delete_subscription(
        self,
        subscription_id: uuid.UUID,
        project_id: uuid.UUID | None = None,
    ) -> bool:
        """Delete a webhook subscription (soft delete)."""
        subscription = await self.get_subscription(subscription_id, project_id)
        if not subscription:
            return False
        
        subscription.is_deleted = True
        await self.db.commit()
        
        logger.info(
            "webhook_subscription_deleted",
            subscription_id=str(subscription_id),
            project_id=str(subscription.project_id),
        )
        
        return True

    async def create_delivery(
        self,
        subscription_id: uuid.UUID,
        event_type: WebhookEventType,
        payload: dict[str, Any],
    ) -> WebhookDelivery:
        """Create a webhook delivery."""
        delivery = WebhookDelivery(
            subscription_id=subscription_id,
            event_type=event_type,
            payload=payload,
            status=WebhookDeliveryStatus.PENDING,
        )
        
        self.db.add(delivery)
        await self.db.commit()
        await self.db.refresh(delivery)
        
        return delivery

    async def get_delivery(
        self,
        delivery_id: uuid.UUID,
        project_id: uuid.UUID | None = None,
    ) -> WebhookDelivery | None:
        """Get a webhook delivery by ID."""
        query = select(WebhookDelivery).where(
            and_(
                WebhookDelivery.id == delivery_id,
                WebhookDelivery.is_deleted.is_(False),
            )
        )
        
        if project_id:
            query = query.join(WebhookSubscription).where(
                WebhookSubscription.project_id == project_id
            )
        
        result = await self.db.execute(query)
        return result.scalar_one_or_none()

    async def list_deliveries(
        self,
        project_id: uuid.UUID,
        filters: WebhookDeliveryFilter,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[WebhookDelivery], int]:
        """List webhook deliveries with filters."""
        query = select(WebhookDelivery).join(WebhookSubscription).where(
            and_(
                WebhookSubscription.project_id == project_id,
                WebhookDelivery.is_deleted.is_(False),
                WebhookSubscription.is_deleted.is_(False),
            )
        )
        
        count_query = select(func.count(WebhookDelivery.id)).join(WebhookSubscription).where(
            and_(
                WebhookSubscription.project_id == project_id,
                WebhookDelivery.is_deleted.is_(False),
                WebhookSubscription.is_deleted.is_(False),
            )
        )
        
        # Apply filters
        if filters.status:
            query = query.where(WebhookDelivery.status == filters.status)
            count_query = count_query.where(WebhookDelivery.status == filters.status)
        
        if filters.event_type:
            query = query.where(WebhookDelivery.event_type == filters.event_type)
            count_query = count_query.where(WebhookDelivery.event_type == filters.event_type)
        
        if filters.subscription_id:
            query = query.where(WebhookDelivery.subscription_id == filters.subscription_id)
            count_query = count_query.where(WebhookDelivery.subscription_id == filters.subscription_id)
        
        if filters.created_after:
            query = query.where(WebhookDelivery.created_at >= filters.created_after)
            count_query = count_query.where(WebhookDelivery.created_at >= filters.created_after)
        
        if filters.created_before:
            query = query.where(WebhookDelivery.created_at <= filters.created_before)
            count_query = count_query.where(WebhookDelivery.created_at <= filters.created_before)
        
        # Get total count
        count_result = await self.db.execute(count_query)
        total = count_result.scalar()
        
        # Get deliveries with pagination
        query = query.order_by(WebhookDelivery.created_at.desc()).limit(limit).offset(offset)
        result = await self.db.execute(query)
        deliveries = result.scalars().all()
        
        return list(deliveries), total

    async def trigger_event(
        self,
        event_type: WebhookEventType,
        payload: dict[str, Any],
        project_id: uuid.UUID,
    ) -> None:
        """Trigger a webhook event for all matching subscriptions."""
        subscriptions = await self.list_subscriptions(project_id, enabled_only=True)
        
        for subscription in subscriptions:
            if event_type.value in subscription.events:
                delivery = await self.create_delivery(
                    subscription_id=subscription.id,
                    event_type=event_type,
                    payload=payload,
                )
                
                # Schedule immediate delivery
                await self.schedule_delivery(delivery.id)

    async def schedule_delivery(self, delivery_id: uuid.UUID) -> None:
        """Schedule a webhook delivery for immediate processing."""
        delivery = await self.get_delivery(delivery_id)
        if not delivery or delivery.status != WebhookDeliveryStatus.PENDING:
            return
        
        # This would normally be handled by a background task queue
        # For now, we'll deliver synchronously
        await self.deliver_webhook(delivery_id)

    async def _ensure_cutover(self, subscription: WebhookSubscription) -> WebhookSubscription:
        """If cutover time has passed, promote the pending_secret to active."""
        if subscription.cutover_at and subscription.pending_secret:
            now = datetime.utcnow()
            if subscription.cutover_at.tzinfo is not None:
                # normalize to naive UTC for comparison
                now = datetime.utcnow()
                cutoff = subscription.cutover_at.replace(tzinfo=None)
                if now >= cutoff:
                    subscription.secret = subscription.pending_secret
                    subscription.pending_secret = None
                    subscription.cutover_at = None
                    await self.db.commit()
                    await self.db.refresh(subscription)
            else:
                if datetime.utcnow() >= subscription.cutover_at:
                    subscription.secret = subscription.pending_secret
                    subscription.pending_secret = None
                    subscription.cutover_at = None
                    await self.db.commit()
                    await self.db.refresh(subscription)
        return subscription

    async def start_rotation(self, subscription_id: uuid.UUID, *, grace_seconds: int = 3600, new_secret: str | None = None) -> WebhookSubscription | None:
        """Begin secret rotation by staging a pending_secret and cutover time.
        The active secret continues to be used for signing until cutover.
        """
        subscription = await self.get_subscription(subscription_id)
        if not subscription:
            return None
        pending = new_secret or secrets.token_urlsafe(24)
        subscription.pending_secret = pending
        subscription.cutover_at = datetime.utcnow() + timedelta(seconds=grace_seconds)
        await self.db.commit()
        await self.db.refresh(subscription)
        logger.info("webhook_secret_rotation_started", subscription_id=str(subscription.id), cutover_at=str(subscription.cutover_at))
        return subscription

    async def finalize_rotation(self, subscription_id: uuid.UUID) -> WebhookSubscription | None:
        """Immediately cut over to the pending secret if present."""
        subscription = await self.get_subscription(subscription_id)
        if not subscription:
            return None
        if subscription.pending_secret:
            subscription.secret = subscription.pending_secret
            subscription.pending_secret = None
            subscription.cutover_at = None
            await self.db.commit()
            await self.db.refresh(subscription)
            logger.info("webhook_secret_rotation_finalized", subscription_id=str(subscription.id))
        return subscription

    async def deliver_webhook(self, delivery_id: uuid.UUID) -> bool:
        """Deliver a webhook."""
        delivery = await self.get_delivery(delivery_id)
        if not delivery:
            return False
        
        subscription = await self.get_subscription(delivery.subscription_id)
        if not subscription or not subscription.enabled:
            return False
        
        # If cutover passed, promote secret
        subscription = await self._ensure_cutover(subscription)
        
        # Generate signature
        timestamp = int(datetime.utcnow().timestamp())
        payload_str = json.dumps(delivery.payload, separators=(",", ":"), sort_keys=True)
        signature_payload = f"{timestamp}.{payload_str}"
        signature = hmac.new(
            subscription.secret.encode(),
            signature_payload.encode(),
            hashlib.sha256,
        ).hexdigest()
        
        # Prepare headers
        headers = {
            "Content-Type": "application/json",
            WEBHOOK_SIGNATURE_HEADER: f"sha256={signature}",
            WEBHOOK_TIMESTAMP_HEADER: str(timestamp),
            WEBHOOK_EVENT_HEADER: delivery.event_type.value,
            WEBHOOK_DELIVERY_ID_HEADER: str(delivery.id),
            **subscription.headers,
        }
        
        # Record start time for metrics
        start_time = datetime.utcnow()
        final_status = WebhookDeliveryStatus.FAILED
        failure_reason = None
        
        try:
            async with httpx.AsyncClient(timeout=WEBHOOK_TIMEOUT) as client:
                response = await client.post(
                    subscription.url,
                    json=delivery.payload,
                    headers=headers,
                )
            
            if 200 <= response.status_code < 300:
                # Success
                delivery.status = WebhookDeliveryStatus.DELIVERED
                delivery.delivered_at = datetime.utcnow()
                delivery.last_error = None
                final_status = WebhookDeliveryStatus.DELIVERED
                
                logger.info(
                    "webhook_delivered",
                    delivery_id=str(delivery_id),
                    subscription_id=str(subscription.id),
                    status_code=response.status_code,
                )
            else:
                # Failure - determine if we should retry
                delivery.attempts += 1
                delivery.last_error = f"HTTP {response.status_code}: {response.text}"
                failure_reason = f"http_{response.status_code}"
                
                if 400 <= response.status_code < 500:
                    # Client error - don't retry
                    delivery.status = WebhookDeliveryStatus.FAILED
                    final_status = WebhookDeliveryStatus.FAILED
                else:
                    # Server error - retry if we haven't exceeded max retries
                    if delivery.attempts >= subscription.retries_max:
                        delivery.status = WebhookDeliveryStatus.DLQ
                        final_status = WebhookDeliveryStatus.DLQ
                    else:
                        delivery.next_retry_at = self._calculate_retry_at(
                            subscription.backoff_strategy,
                            delivery.attempts,
                        )
                        final_status = WebhookDeliveryStatus.FAILED
                
                logger.warning(
                    "webhook_delivery_failed",
                    delivery_id=str(delivery_id),
                    subscription_id=str(subscription.id),
                    status_code=response.status_code,
                    attempts=delivery.attempts,
                    max_retries=subscription.retries_max,
                )
        
        except Exception as exc:
            # Network or other error
            delivery.attempts += 1
            delivery.last_error = str(exc)
            failure_reason = f"network_error"
            
            if delivery.attempts >= subscription.retries_max:
                delivery.status = WebhookDeliveryStatus.DLQ
                final_status = WebhookDeliveryStatus.DLQ
            else:
                delivery.next_retry_at = self._calculate_retry_at(
                    subscription.backoff_strategy,
                    delivery.attempts,
                )
                final_status = WebhookDeliveryStatus.FAILED
            
            logger.error(
                "webhook_delivery_error",
                delivery_id=str(delivery_id),
                subscription_id=str(subscription.id),
                error=str(exc),
                attempts=delivery.attempts,
            )
        
        # Calculate duration and record metrics
        duration_ms = (datetime.utcnow() - start_time).total_seconds() * 1000
        
        record_webhook_delivery(
            project_id=str(subscription.project_id),
            event_type=delivery.event_type.value,
            subscription_id=str(subscription.id),
            status=final_status.value,
            duration_ms=duration_ms,
            failure_reason=failure_reason,
        )
        
        await self.db.commit()
        return delivery.status == WebhookDeliveryStatus.DELIVERED

    def _calculate_retry_at(
        self,
        strategy: str,
        attempts: int,
    ) -> datetime:
        """Calculate the next retry time based on strategy."""
        if strategy == "exponential":
            # Exponential backoff with jitter: 2^attempts * base_delay + jitter
            base_delay = 60  # 1 minute base
            delay = (2 ** (attempts - 1)) * base_delay
        elif strategy == "linear":
            # Linear backoff: attempts * base_delay
            delay = attempts * 300  # 5 minutes per attempt
        else:  # fixed
            # Fixed delay
            delay = 300  # 5 minutes
        
        # Add jitter (±25%)
        import random
        jitter = delay * 0.25 * (random.random() * 2 - 1)
        final_delay = max(60, delay + jitter)  # Minimum 1 minute
        
        return datetime.utcnow() + timedelta(seconds=final_delay)

    async def redeliver_webhook(self, delivery_id: uuid.UUID) -> bool:
        """Redeliver a failed webhook."""
        delivery = await self.get_delivery(delivery_id)
        if not delivery:
            return False
        
        # Reset delivery state
        delivery.status = WebhookDeliveryStatus.PENDING
        delivery.attempts = 0
        delivery.last_error = None
        delivery.next_retry_at = None
        
        await self.db.commit()
        
        # Schedule immediate delivery
        await self.schedule_delivery(delivery_id)
        
        logger.info(
            "webhook_redelivery_scheduled",
            delivery_id=str(delivery_id),
            subscription_id=str(delivery.subscription_id),
        )
        
        return True

    async def test_webhook(
        self,
        url: str,
        secret: str,
        event_type: WebhookEventType,
    ) -> tuple[bool, str, uuid.UUID | None]:
        """Test a webhook configuration."""
        # Create test payload
        test_payload = {
            "test": True,
            "event_type": event_type.value,
            "timestamp": datetime.utcnow().isoformat(),
            "message": "This is a test webhook from the API Automation Platform",
        }
        
        # Create a temporary delivery for tracking
        delivery_id = uuid.uuid4()
        
        # Generate signature
        timestamp = int(datetime.utcnow().timestamp())
        payload_str = json.dumps(test_payload, separators=(",", ":"), sort_keys=True)
        signature_payload = f"{timestamp}.{payload_str}"
        signature = hmac.new(
            secret.encode(),
            signature_payload.encode(),
            hashlib.sha256,
        ).hexdigest()
        
        headers = {
            "Content-Type": "application/json",
            WEBHOOK_SIGNATURE_HEADER: f"sha256={signature}",
            WEBHOOK_TIMESTAMP_HEADER: str(timestamp),
            WEBHOOK_EVENT_HEADER: event_type.value,
            WEBHOOK_DELIVERY_ID_HEADER: str(delivery_id),
        }
        
        try:
            async with httpx.AsyncClient(timeout=WEBHOOK_TIMEOUT) as client:
                response = await client.post(
                    url,
                    json=test_payload,
                    headers=headers,
                )
            
            if 200 <= response.status_code < 300:
                return True, "Test webhook delivered successfully", delivery_id
            else:
                return False, f"HTTP {response.status_code}: {response.text}", delivery_id
        
        except Exception as exc:
            return False, f"Network error: {str(exc)}", delivery_id

    @staticmethod
    def verify_signature(
        payload: str,
        signature: str,
        secret: str,
        timestamp: int,
    ) -> bool:
        """Verify a webhook signature."""
        # Check timestamp is within 5 minutes
        now = int(datetime.utcnow().timestamp())
        if abs(now - timestamp) > 300:  # 5 minutes
            return False
        
        # Recreate signature payload
        signature_payload = f"{timestamp}.{payload}"
        expected_signature = hmac.new(
            secret.encode(),
            signature_payload.encode(),
            hashlib.sha256,
        ).hexdigest()
        
        # Compare signatures securely
        return hmac.compare_digest(f"sha256={expected_signature}", signature)