from __future__ import annotations

import threading

import httpx

from app.core.config import get_settings
from app.logging import get_logger

_client: httpx.Client | None = None
_client_lock = threading.Lock()
_logger = get_logger().bind(component="http_client")


def _build_client() -> httpx.Client:
    settings = get_settings()
    limits = httpx.Limits(
        max_connections=settings.httpx_max_connections,
        max_keepalive_connections=settings.httpx_max_keepalive_connections,
        keepalive_expiry=settings.httpx_keepalive_expiry,
    )
    timeout = httpx.Timeout(
        connect=settings.httpx_connect_timeout,
        read=settings.httpx_read_timeout,
        write=settings.httpx_write_timeout,
        pool=settings.httpx_pool_timeout,
    )
    _logger.debug(
        "http_client_created",
        max_connections=settings.httpx_max_connections,
        max_keepalive_connections=settings.httpx_max_keepalive_connections,
        connect_timeout=settings.httpx_connect_timeout,
        read_timeout=settings.httpx_read_timeout,
        write_timeout=settings.httpx_write_timeout,
        pool_timeout=settings.httpx_pool_timeout,
        keepalive_expiry=settings.httpx_keepalive_expiry,
    )
    return httpx.Client(timeout=timeout, limits=limits, follow_redirects=True)


def get_http_client() -> httpx.Client:
    global _client
    if _client is not None:
        return _client
    with _client_lock:
        if _client is None:
            _client = _build_client()
    return _client


def close_http_client() -> None:
    global _client
    with _client_lock:
        if _client is not None:
            try:
                _client.close()
            finally:
                _client = None


def override_http_client(client: httpx.Client | None) -> None:
    global _client
    with _client_lock:
        if _client is not None and _client is not client:
            try:
                _client.close()
            except Exception:  # pragma: no cover - defensive guard
                _logger.warning("http_client_close_failed")
        _client = client


__all__ = ["get_http_client", "close_http_client", "override_http_client"]
