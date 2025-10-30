from __future__ import annotations

import uuid

import redis
from fastapi import status
from redis.exceptions import RedisError
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.api_tokens import parse_token, verify_token_secret
from app.core.config import get_settings
from app.core.errors import ErrorCode, http_exception
from app.logging import get_logger
from app.models.agent import Agent, AgentStatus

_logger = get_logger().bind(component="agent-security")


class AgentAuthenticationError(RuntimeError):
    """Raised when an agent token cannot be authenticated."""


def _redis_client() -> redis.Redis:
    settings = get_settings()
    return redis.Redis.from_url(settings.redis_url, decode_responses=True)


def authenticate_agent_token(session: Session, token: str) -> Agent:
    """Authenticate an agent token and return the associated agent."""

    try:
        prefix, secret = parse_token(token)
    except ValueError as exc:
        raise http_exception(
            status.HTTP_401_UNAUTHORIZED,
            ErrorCode.AUTH_TOKEN_INVALID,
            "Invalid agent token",
        ) from exc

    stmt = select(Agent).where(Agent.token_prefix == prefix, Agent.is_deleted.is_(False)).limit(1)
    agent = session.execute(stmt).scalar_one_or_none()
    if agent is None or agent.token_revoked_at is not None:
        raise http_exception(
            status.HTTP_401_UNAUTHORIZED,
            ErrorCode.AUTH_TOKEN_INVALID,
            "Invalid agent token",
        )

    if not verify_token_secret(secret, agent.token_hash):
        raise http_exception(
            status.HTTP_401_UNAUTHORIZED,
            ErrorCode.AUTH_TOKEN_INVALID,
            "Invalid agent token",
        )

    if not agent.enabled or agent.status == AgentStatus.DISABLED:
        raise http_exception(
            status.HTTP_403_FORBIDDEN,
            ErrorCode.NO_PERMISSION,
            "Agent is disabled",
        )

    return agent


def enforce_heartbeat_rate_limit(agent_id: uuid.UUID) -> None:
    """Enforce per-agent heartbeat rate limiting using Redis."""

    settings = get_settings()
    limit = int(getattr(settings, "agent_heartbeat_rate_limit_per_minute", 0) or 0)
    if limit <= 0:
        return

    client = _redis_client()
    key = f"agent:heartbeat:{agent_id}"

    try:
        count = client.incr(key)
        if count == 1:
            client.expire(key, 60)
    except RedisError as exc:  # pragma: no cover - best effort fallback
        _logger.warning("agent_heartbeat_rate_limit.redis_error", error=str(exc))
        return

    if count > limit:
        retry_after = client.ttl(key)
        if not isinstance(retry_after, int) or retry_after <= 0:
            retry_after = 60
        raise http_exception(
            status.HTTP_429_TOO_MANY_REQUESTS,
            ErrorCode.RATE_LIMIT_EXCEEDED,
            "Agent heartbeat rate limit exceeded",
            headers={"Retry-After": str(retry_after)},
        )
