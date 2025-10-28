import logging
import sys
from typing import Awaitable, Callable
from uuid import uuid4

import structlog
from structlog import contextvars
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response


def configure_logging() -> None:
    logging.basicConfig(level=logging.INFO, handlers=[logging.StreamHandler(sys.stdout)], format="%(message)s")
    for logger_name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        logging.getLogger(logger_name).handlers = []

    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.JSONRenderer(),
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )


class RequestIdMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: Callable[[Request], Awaitable[Response]]) -> Response:
        request_id = request.headers.get("X-Request-ID", str(uuid4()))
        contextvars.clear_contextvars()
        contextvars.bind_contextvars(request_id=request_id, path=str(request.url.path))
        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        return response


def get_logger() -> structlog.stdlib.BoundLogger:
    return structlog.get_logger()
