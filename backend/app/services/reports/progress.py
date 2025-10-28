from __future__ import annotations

import json
from datetime import datetime, timezone
from functools import lru_cache
from typing import Any, Literal, TypedDict, cast

import redis
import redis.asyncio as aioredis
from redis.asyncio.client import PubSub

from app.core.config import get_settings

ProgressEventType = Literal["task_queued", "started", "step_progress", "assertion_result", "finished"]

MAX_EVENT_BYTES = 32768
MAX_STRING_LENGTH = 2048
MAX_COLLECTION_ITEMS = 20
MAX_DEPTH = 4
TRUNCATED_SUFFIX = "… (truncated)"
CHANNEL_PREFIX = "report_progress"


class ProgressEvent(TypedDict, total=False):
    type: ProgressEventType
    report_id: str
    step_alias: str
    payload: dict[str, Any]
    timestamp: str
    truncated: bool


@lru_cache(maxsize=1)
def _sync_client() -> redis.Redis:
    settings = get_settings()
    return redis.Redis.from_url(settings.redis_url, decode_responses=True)


@lru_cache(maxsize=1)
def _async_client() -> aioredis.Redis:
    settings = get_settings()
    return aioredis.from_url(settings.redis_url, decode_responses=True)


def get_sync_redis() -> redis.Redis:
    return _sync_client()


def get_async_redis() -> aioredis.Redis:
    return _async_client()


def progress_channel(report_id: str) -> str:
    return f"{CHANNEL_PREFIX}:{report_id}"


def publish_progress_event(
    report_id: str,
    event_type: ProgressEventType,
    *,
    payload: dict[str, Any] | None = None,
    step_alias: str | None = None,
) -> ProgressEvent:
    event: ProgressEvent = {
        "type": event_type,
        "report_id": str(report_id),
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    if step_alias:
        event["step_alias"] = step_alias
    if payload is not None:
        event["payload"] = _sanitize_payload(payload)

    safe_event = _ensure_size(event)
    message = json.dumps(safe_event, ensure_ascii=False, separators=(",", ":"))
    get_sync_redis().publish(progress_channel(str(report_id)), message)
    return safe_event


async def subscribe_to_progress(report_id: str) -> PubSub:
    client = get_async_redis()
    pubsub = client.pubsub()
    await pubsub.subscribe(progress_channel(report_id))
    return pubsub


async def close_progress_subscription(pubsub: PubSub, report_id: str) -> None:
    try:
        await pubsub.unsubscribe(progress_channel(report_id))
    finally:
        await pubsub.close()


def _sanitize_payload(
    value: Any,
    *,
    depth: int = 0,
    max_depth: int = MAX_DEPTH,
    max_string_length: int = MAX_STRING_LENGTH,
    max_items: int = MAX_COLLECTION_ITEMS,
) -> Any:
    if value is None or isinstance(value, (int, float, bool)):
        return value
    if isinstance(value, str):
        if len(value) <= max_string_length:
            return value
        return value[:max_string_length] + TRUNCATED_SUFFIX
    if isinstance(value, (bytes, bytearray)):
        decoded = bytes(value).decode("utf-8", errors="replace")
        if len(decoded) <= max_string_length:
            return decoded
        return decoded[:max_string_length] + TRUNCATED_SUFFIX
    if isinstance(value, (list, tuple, set)):
        if depth >= max_depth:
            return ["__truncated__"]
        sanitized_list = []
        for index, item in enumerate(value):
            if index >= max_items:
                sanitized_list.append({"__truncated__": True, "count": len(value)})
                break
            sanitized_list.append(
                _sanitize_payload(
                    item,
                    depth=depth + 1,
                    max_depth=max_depth,
                    max_string_length=max_string_length,
                    max_items=max_items,
                )
            )
        return sanitized_list
    if isinstance(value, dict):
        if depth >= max_depth:
            return {"__truncated__": True}
        sanitized: dict[str, Any] = {}
        for index, (key, item) in enumerate(value.items()):
            if index >= max_items:
                sanitized["__truncated__"] = True
                break
            sanitized[str(key)] = _sanitize_payload(
                item,
                depth=depth + 1,
                max_depth=max_depth,
                max_string_length=max_string_length,
                max_items=max_items,
            )
        return sanitized
    return str(value)


def _ensure_size(event: ProgressEvent) -> ProgressEvent:
    encoded = json.dumps(event, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    if len(encoded) <= MAX_EVENT_BYTES:
        return event

    truncated_event = dict(event)
    truncated_event["truncated"] = True
    payload = truncated_event.get("payload")
    if payload is not None:
        truncated_event["payload"] = _sanitize_payload(
            payload,
            depth=0,
            max_depth=2,
            max_items=5,
            max_string_length=512,
        )
    else:
        truncated_event["payload"] = {"message": "payload omitted"}

    encoded = json.dumps(truncated_event, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    if len(encoded) <= MAX_EVENT_BYTES:
        return cast(ProgressEvent, truncated_event)

    truncated_event["payload"] = {"message": "payload truncated due to size limits"}
    return cast(ProgressEvent, truncated_event)
