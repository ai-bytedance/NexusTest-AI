from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field, HttpUrl

from app.models.webhook import WebhookBackoffStrategy, WebhookDeliveryStatus, WebhookEventType


class WebhookSubscriptionBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    url: HttpUrl
    events: list[WebhookEventType] = Field(..., min_items=1)
    enabled: bool = True
    headers: dict[str, str] = Field(default_factory=dict)
    retries_max: int = Field(default=5, ge=0, le=20)
    backoff_strategy: WebhookBackoffStrategy = WebhookBackoffStrategy.EXPONENTIAL


class WebhookSubscriptionCreate(WebhookSubscriptionBase):
    secret: str = Field(..., min_length=8, max_length=255)


class WebhookSubscriptionUpdate(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=255)
    url: HttpUrl | None = None
    events: list[WebhookEventType] | None = Field(None, min_items=1)
    enabled: bool | None = None
    headers: dict[str, str] | None = None
    retries_max: int | None = Field(None, ge=0, le=20)
    backoff_strategy: WebhookBackoffStrategy | None = None


class WebhookSubscriptionResponse(WebhookSubscriptionBase):
    id: str
    project_id: str
    created_by: str
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class WebhookSubscriptionWithSecret(WebhookSubscriptionResponse):
    secret: str


class WebhookDeliveryBase(BaseModel):
    event_type: WebhookEventType
    payload: dict[str, Any]
    status: WebhookDeliveryStatus
    attempts: int
    last_error: str | None = None
    next_retry_at: datetime | None = None
    delivered_at: datetime | None = None


class WebhookDeliveryResponse(WebhookDeliveryBase):
    id: str
    subscription_id: str
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class WebhookDeliveryFilter(BaseModel):
    status: WebhookDeliveryStatus | None = None
    event_type: WebhookEventType | None = None
    subscription_id: str | None = None
    created_after: datetime | None = None
    created_before: datetime | None = None


class WebhookTestSendRequest(BaseModel):
    url: HttpUrl
    secret: str
    event_type: WebhookEventType = WebhookEventType.RUN_STARTED


class WebhookTestSendResponse(BaseModel):
    success: bool
    message: str
    delivery_id: str | None = None


class WebhookRedeliverRequest(BaseModel):
    pass


class WebhookRedeliverResponse(BaseModel):
    success: bool
    message: str
    delivery_id: str