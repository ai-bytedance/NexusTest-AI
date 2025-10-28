from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class ResponseEnvelope(BaseModel):
    code: str = Field(default="SUCCESS")
    message: str = Field(default="Success")
    data: Any | None = None


def success_response(data: Any | None = None, message: str = "Success", code: str = "SUCCESS") -> dict[str, Any | None]:
    return {"code": code, "message": message, "data": data}
