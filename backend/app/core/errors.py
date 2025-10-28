from __future__ import annotations

from enum import Enum
from typing import Any

from fastapi import HTTPException, status


class ErrorCode(str, Enum):
    SUCCESS = "SUCCESS"
    VALIDATION_ERROR = "V001"
    NOT_AUTHENTICATED = "A001"
    NO_PERMISSION = "P001"
    NOT_FOUND = "N001"
    CONFLICT = "C001"
    BAD_REQUEST = "B001"
    AI_PROVIDER_ERROR = "AI001"
    AI_PROVIDER_RATE_LIMIT = "AI002"
    AI_PROVIDER_TIMEOUT = "AI003"
    AI_PROVIDER_UNAVAILABLE = "AI004"
    AI_PROVIDER_NOT_CONFIGURED = "AI005"
    AI_PROVIDER_NOT_IMPLEMENTED = "AI006"


def create_error_detail(code: ErrorCode | str, message: str, data: Any | None = None) -> dict[str, Any | None]:
    code_value = code.value if isinstance(code, ErrorCode) else str(code)
    return {"code": code_value, "message": message, "data": data}


def http_exception(
    status_code: int,
    code: ErrorCode | str,
    message: str,
    *,
    data: Any | None = None,
    headers: dict[str, str] | None = None,
) -> HTTPException:
    return HTTPException(
        status_code=status_code,
        detail=create_error_detail(code, message, data),
        headers=headers,
    )


def raise_http_exception(
    status_code: int,
    code: ErrorCode | str,
    message: str,
    *,
    data: Any | None = None,
    headers: dict[str, str] | None = None,
) -> None:
    raise http_exception(status_code, code, message, data=data, headers=headers)


NOT_FOUND_EXCEPTION = http_exception(status.HTTP_404_NOT_FOUND, ErrorCode.NOT_FOUND, "Resource not found")
