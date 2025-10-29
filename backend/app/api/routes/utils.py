from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, Depends, status
from jsonpath_ng.exceptions import JsonPathParserError
from jsonpath_ng.ext import parse as jsonpath_parse

from app.api.response import ResponseEnvelope, success_response
from app.core.authz import get_current_user
from app.core.errors import ErrorCode, http_exception
from app.schemas.assertions import (
    AssertionPreviewRequest,
    AssertionPreviewResponse,
    AssertionResultRead,
    JsonPathTestRequest,
    JsonPathTestResponse,
)
from app.services.assertions.engine import AssertionEngine
from app.services.assertions.templates import list_common_templates
from app.services.execution.context import ExecutionContext

router = APIRouter(prefix="/utils", tags=["utils"])
assertion_engine = AssertionEngine()


@router.get("/assertions/templates", response_model=ResponseEnvelope)
def list_assertion_templates(_current_user=Depends(get_current_user)) -> dict[str, Any]:
    templates = list_common_templates()
    return success_response({"templates": templates})


@router.post("/jsonpath", response_model=ResponseEnvelope)
def evaluate_jsonpath(
    payload: JsonPathTestRequest,
    _current_user=Depends(get_current_user),
) -> dict[str, Any]:
    json_payload = payload.json if payload.json is not None else {}
    path = payload.path.strip()
    try:
        expression = jsonpath_parse(path)
    except JsonPathParserError as exc:
        raise http_exception(
            status.HTTP_400_BAD_REQUEST,
            ErrorCode.BAD_REQUEST,
            f"Invalid JSONPath expression: {path}",
        ) from exc

    matches = [match.value for match in expression.find(json_payload)]
    response = JsonPathTestResponse(matches=matches)
    return success_response(response.model_dump())


@router.post("/assertion/preview", response_model=ResponseEnvelope)
def preview_assertion(
    payload: AssertionPreviewRequest,
    _current_user=Depends(get_current_user),
) -> dict[str, Any]:
    response_context = {
        "status_code": payload.status_code,
        "headers": payload.headers or {},
        "json": payload.response_json if payload.response_json is not None else {},
        "body": payload.body,
    }
    if response_context["body"] is None and payload.response_json is not None:
        try:
            response_context["body"] = json.dumps(payload.response_json, ensure_ascii=False)
        except TypeError:
            response_context["body"] = str(payload.response_json)

    context = ExecutionContext()
    assertion_payload = payload.assertion.model_dump(mode="json", exclude_none=True)
    passed, results = assertion_engine.evaluate([assertion_payload], response_context, context)
    result_model: AssertionResultRead | None = None
    if results:
        result_model = AssertionResultRead.model_validate(results[0].to_dict())
    preview = AssertionPreviewResponse(passed=passed, result=result_model)
    return success_response(preview.model_dump())
