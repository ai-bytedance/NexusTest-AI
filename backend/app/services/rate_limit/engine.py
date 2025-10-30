from __future__ import annotations

import fnmatch
import math
import time
import uuid
from dataclasses import dataclass
from functools import lru_cache
from typing import Iterable, Sequence

import redis
from fastapi import Request
from redis.exceptions import RedisError
from sqlalchemy.orm import Session

from app.core.api_tokens import TokenAuthContext
from app.core.config import get_settings
from app.core.errors import ErrorCode, http_exception
from app.logging import get_logger
from app.models import Project, RateLimitPolicy
from app.schemas.rate_limit import RateLimitRule

logger = get_logger().bind(component="rate_limit")
BURST_WINDOW_SECONDS = 10


@dataclass(frozen=True)
class CompiledRule:
    policy_id: uuid.UUID
    index: int
    per_minute: int | None
    per_hour: int | None
    burst: int | None
    path_patterns: tuple[str, ...]
    methods: tuple[str, ...]

    def matches(self, method: str, path: str) -> bool:
        if self.methods and method not in self.methods:
            return False
        for pattern in self.path_patterns:
            if pattern == "*" or fnmatch.fnmatch(path, pattern):
                return True
        return False


@dataclass(frozen=True)
class WindowCheck:
    key: str
    window_seconds: int
    limit: int


class RateLimitExceeded(Exception):
    def __init__(self, retry_after: float, policy_id: uuid.UUID) -> None:
        super().__init__("Rate limit exceeded")
        self.retry_after = retry_after
        self.policy_id = policy_id


@lru_cache(maxsize=1)
def _redis_client() -> redis.Redis:
    settings = get_settings()
    return redis.Redis.from_url(settings.redis_url, decode_responses=False)


def _compile_policy(policy: RateLimitPolicy) -> tuple[CompiledRule, ...]:
    compiled: list[CompiledRule] = []
    for index, raw_rule in enumerate(policy.rules or []):
        rule = RateLimitRule.model_validate(raw_rule)
        methods = tuple(method.upper() for method in (rule.methods or []))
        patterns = tuple(rule.path_patterns or ["*"])
        compiled.append(
            CompiledRule(
                policy_id=policy.id,
                index=index,
                per_minute=rule.per_minute,
                per_hour=rule.per_hour,
                burst=rule.burst,
                path_patterns=patterns,
                methods=methods,
            )
        )
    return tuple(compiled)


def _window_key(policy_id: uuid.UUID, rule_index: int, subject_id: uuid.UUID, project_id: uuid.UUID | None, suffix: str) -> str:
    project_part = str(project_id) if project_id is not None else "global"
    return f"rl:{policy_id}:{rule_index}:{subject_id}:{project_part}:{suffix}"


def _prepare_windows(rule: CompiledRule, subject_id: uuid.UUID, project_id: uuid.UUID | None) -> list[WindowCheck]:
    windows: list[WindowCheck] = []
    if rule.per_minute is not None:
        windows.append(
            WindowCheck(
                key=_window_key(rule.policy_id, rule.index, subject_id, project_id, "m"),
                window_seconds=60,
                limit=rule.per_minute,
            )
        )
    if rule.per_hour is not None:
        windows.append(
            WindowCheck(
                key=_window_key(rule.policy_id, rule.index, subject_id, project_id, "h"),
                window_seconds=3600,
                limit=rule.per_hour,
            )
        )
    if rule.burst is not None:
        windows.append(
            WindowCheck(
                key=_window_key(rule.policy_id, rule.index, subject_id, project_id, "b"),
                window_seconds=BURST_WINDOW_SECONDS,
                limit=rule.burst,
            )
        )
    return windows


def _check_window(client: redis.Redis, window: WindowCheck, now: float) -> float:
    try:
        cutoff = now - window.window_seconds
        pipe = client.pipeline()
        pipe.zremrangebyscore(window.key, "-inf", cutoff)
        pipe.zcard(window.key)
        pipe.zrange(window.key, 0, 0, withscores=True)
        _, count, oldest_entries = pipe.execute()
    except RedisError as exc:  # pragma: no cover - defensive logging
        logger.warning("rate_limit.redis_error", error=str(exc))
        return 0.0

    if count >= window.limit:
        oldest = oldest_entries[0][1] if oldest_entries else now
        retry_after = window.window_seconds - (now - oldest)
        return max(retry_after, 0.0)
    return 0.0


def _increment_window(client: redis.Redis, window: WindowCheck, now: float) -> None:
    member = f"{now:.6f}:{uuid.uuid4()}"
    ttl = max(window.window_seconds, BURST_WINDOW_SECONDS)
    try:
        pipe = client.pipeline()
        pipe.zadd(window.key, {member: now})
        pipe.expire(window.key, ttl)
        pipe.execute()
    except RedisError as exc:  # pragma: no cover - defensive logging
        logger.warning("rate_limit.redis_error", error=str(exc))


def enforce_rate_limits(
    session: Session,
    *,
    request: Request,
    auth_context: TokenAuthContext | None,
    project: Project | None = None,
    project_id: uuid.UUID | None = None,
) -> None:
    if auth_context is None:
        return

    policies: list[RateLimitPolicy] = []
    if auth_context.rate_limit_policy_id is not None:
        token_policy = session.get(RateLimitPolicy, auth_context.rate_limit_policy_id)
        if token_policy and token_policy.enabled:
            policies.append(token_policy)

    project_ref: Project | None = project
    if project_ref is None and project_id is not None:
        project_ref = session.get(Project, project_id)

    if project_ref and project_ref.default_rate_limit_policy_id:
        default_policy = session.get(RateLimitPolicy, project_ref.default_rate_limit_policy_id)
        if default_policy and default_policy.enabled:
            policies.append(default_policy)

    if not policies:
        return

    client = _redis_client()
    method = request.method.upper()
    path = request.url.path

    rule_applications: list[tuple[CompiledRule, list[WindowCheck]]] = []
    for policy in policies:
        compiled_rules = _compile_policy(policy)
        for rule in compiled_rules:
            if not rule.matches(method, path):
                continue
            windows = _prepare_windows(rule, auth_context.token_id, project_ref.id if project_ref else project_id)
            if not windows:
                continue
            rule_applications.append((rule, windows))

    if not rule_applications:
        return

    now = time.time()
    max_retry_after = 0.0
    for rule, windows in rule_applications:
        for window in windows:
            retry_after = _check_window(client, window, now)
            if retry_after > 0:
                max_retry_after = max(max_retry_after, retry_after)
    if max_retry_after > 0:
        headers = {"Retry-After": str(int(math.ceil(max_retry_after))) if max_retry_after else "1"}
        raise http_exception(
            status_code=429,
            code=ErrorCode.RATE_LIMIT_EXCEEDED,
            message="Rate limit exceeded",
            headers=headers,
        )

    for _, windows in rule_applications:
        for window in windows:
            _increment_window(client, window, now)


__all__ = ["enforce_rate_limits"]
