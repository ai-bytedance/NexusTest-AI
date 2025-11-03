from __future__ import annotations

import io
import json
import re
import textwrap
import unicodedata
from collections import defaultdict
from typing import Any, Iterable, Mapping, Sequence
from urllib.parse import urlparse
from uuid import UUID
from zipfile import ZIP_DEFLATED, ZipFile

from app.models.api import Api
from app.models.test_case import TestCase


def generate_pytest_archive(
    *,
    project_name: str,
    cases: Sequence[TestCase],
    api_map: Mapping[UUID, Api],
) -> bytes:
    buffer = io.BytesIO()
    grouped: dict[UUID, list[TestCase]] = defaultdict(list)
    for case in cases:
        grouped[case.api_id].append(case)

    mocks: dict[str, Any] = {}

    with ZipFile(buffer, "w", ZIP_DEFLATED) as bundle:
        bundle.writestr("tests/__init__.py", "\n")
        bundle.writestr("tests/helpers.py", _helpers_template())
        bundle.writestr("tests/conftest.py", _conftest_template())

        module_index = 1
        for api_id, case_items in grouped.items():
            api = api_map.get(api_id)
            if api is None:
                continue
            module_slug = _slugify(api.name or api.path or f"api_{module_index}")
            module_path = f"tests/test_{module_slug}.py"
            module_content = _build_test_module(api, case_items, mocks)
            bundle.writestr(module_path, module_content)
            module_index += 1

        bundle.writestr("tests/mocks.json", json.dumps(mocks, indent=2, ensure_ascii=False) + "\n")
        bundle.writestr("README.md", _readme_template(project_name))

    return buffer.getvalue()


def _build_test_module(api: Api, cases: Sequence[TestCase], mocks: dict[str, Any]) -> str:
    lines: list[str] = [
        "from __future__ import annotations",
        "",
        "from tests.helpers import extract_jsonpath",
        "",
    ]
    for index, case in enumerate(cases, start=1):
        lines.extend(_render_test_function(api, case, index, mocks))
        lines.append("")
    module = "\n".join(lines).rstrip()
    return module + "\n"


def _render_test_function(api: Api, case: TestCase, index: int, mocks: dict[str, Any]) -> list[str]:
    inputs = dict(case.inputs or {})
    method = _safe_method(inputs.get("method") or api.method or "GET")
    url_path = _resolve_url_path(inputs.get("url"), api.path)
    case_slug = _slugify(case.name or f"case_{index}")
    mock_key = f"{method} {url_path}::{case_slug}"
    fallback_key = f"{method} {url_path}"

    request_headers = dict(_coerce_dict(inputs.get("headers")))
    request_headers["X-Mock-Key"] = mock_key

    request_params = _coerce_dict(inputs.get("params")) or None
    request_json = inputs.get("json")
    request_data = inputs.get("data")

    expected_status = _resolve_status(case)
    expected_body = _extract_expected_body(case)

    mock_payload: dict[str, Any] = {"status_code": expected_status}
    if expected_body is not None:
        mock_payload["json"] = expected_body
    mocks[mock_key] = mock_payload
    mocks.setdefault(fallback_key, mock_payload.copy())

    lines = [f"def test_{case_slug}(http_client):"]
    request_lines = ["    response = http_client.request("]
    request_lines.extend(_format_argument("method", method))
    request_lines.extend(_format_argument("url", url_path))
    request_lines.extend(_format_argument("headers", request_headers))
    if request_params:
        request_lines.extend(_format_argument("params", request_params))
    if request_json is not None:
        request_lines.extend(_format_argument("json", request_json))
    elif request_data is not None:
        request_lines.extend(_format_argument("data", request_data))
    request_lines.append("    )")

    lines.extend(request_lines)
    lines.append(f"    assert response.status_code == {expected_status}")

    assertion_lines, requires_body = _render_assertions(case.assertions or [])
    needs_body = requires_body or expected_body is not None
    if needs_body:
        lines.append("    body = response.json()")
    if expected_body is not None:
        lines.append(f"    assert body == {_format_literal(expected_body)}")
    lines.extend(assertion_lines)

    return lines


def _render_assertions(assertions: Iterable[dict[str, Any]]) -> tuple[list[str], bool]:
    lines: list[str] = []
    needs_body = False
    for definition in assertions:
        operator = str(definition.get("operator", "")).lower()
        if operator == "status_code":
            continue
        if operator == "jsonpath_equals":
            path = definition.get("path")
            expected = definition.get("expected")
            lines.append(
                f"    assert extract_jsonpath(body, {_format_literal(path)}) == {_format_literal(expected)}"
            )
            needs_body = True
        elif operator == "jsonpath_contains":
            path = definition.get("path")
            expected = definition.get("expected")
            lines.append(
                f"    assert {_format_literal(expected)} in extract_jsonpath(body, {_format_literal(path)})"
            )
            needs_body = True
        else:
            name = definition.get("name") or operator or "assertion"
            lines.append(f"    # TODO: Review unsupported assertion '{operator}' ({name})")
    return lines, needs_body


def _resolve_status(case: TestCase) -> int:
    assertions = case.assertions or []
    for definition in assertions:
        operator = str(definition.get("operator", "")).lower()
        if operator == "status_code":
            expected = definition.get("expected")
            if isinstance(expected, int):
                return expected
    expected_payload = case.expected or {}
    status_candidate = expected_payload.get("status_code")
    if isinstance(status_candidate, int):
        return status_candidate
    return 200


def _extract_expected_body(case: TestCase) -> Any:
    expected = case.expected or {}
    body = expected.get("body")
    if body in (None, ""):
        return None
    return body


def _format_argument(name: str, value: Any) -> list[str]:
    literal = _format_literal(value)
    if "\n" not in literal:
        return [f"    {name}={literal},"]
    lines = literal.splitlines()
    formatted = [f"    {name}={lines[0]}"]
    formatted.extend(f"    {line}" for line in lines[1:])
    formatted[-1] = formatted[-1] + ","
    return formatted


def _format_literal(value: Any) -> str:
    if isinstance(value, (int, float, bool)) or value is None:
        return repr(value)
    if isinstance(value, str):
        return repr(value)
    try:
        serialized = json.dumps(value, indent=4, ensure_ascii=False)
    except TypeError:
        return repr(value)
    serialized = re.sub(r"\btrue\b", "True", serialized)
    serialized = re.sub(r"\bfalse\b", "False", serialized)
    serialized = re.sub(r"\bnull\b", "None", serialized)
    return serialized


def _resolve_url_path(url_value: Any, fallback: str | None) -> str:
    if isinstance(url_value, str) and url_value.strip():
        parsed = urlparse(url_value)
        if parsed.scheme and parsed.netloc:
            path = parsed.path or "/"
        else:
            path = url_value
    else:
        path = fallback or "/"
    path = path or "/"
    if not path.startswith("/"):
        path = f"/{path}"
    return path


def _safe_method(value: Any) -> str:
    if isinstance(value, str) and value.strip():
        return value.strip().upper()
    return "GET"


def _coerce_dict(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    return {}


def _slugify(value: str) -> str:
    candidate = unicodedata.normalize("NFKC", value).strip().lower()
    candidate = re.sub(r"[^a-z0-9]+", "_", candidate)
    candidate = re.sub(r"_+", "_", candidate).strip("_")
    return candidate or "item"


def _helpers_template() -> str:
    return textwrap.dedent(
        '''
        from __future__ import annotations

        from typing import Any, Iterable


        class JsonPathError(RuntimeError):
            """Raised when a JSONPath lookup fails."""


        def extract_jsonpath(payload: Any, path: str) -> Any:
            if not isinstance(path, str) or not path.startswith("$"):
                raise JsonPathError(f"Invalid JSONPath expression: {path}")
            tokens: list[Iterable[str | int]] = []
            buffer = ""
            index = 1
            while index < len(path):
                char = path[index]
                if char == ".":
                    if buffer:
                        tokens.append(buffer)
                        buffer = ""
                    index += 1
                    continue
                if char == "[":
                    if buffer:
                        tokens.append(buffer)
                        buffer = ""
                    end = path.find("]", index)
                    if end == -1:
                        raise JsonPathError(f"Unclosed index in JSONPath: {path}")
                    segment = path[index + 1 : end]
                    if segment.isdigit():
                        tokens.append(int(segment))
                    else:
                        tokens.append(segment.strip("\'\""))
                    index = end + 1
                    continue
                buffer += char
                index += 1
            if buffer:
                tokens.append(buffer)

            current = payload
            for token in tokens:
                if isinstance(token, int):
                    if not isinstance(current, (list, tuple)) or token >= len(current):
                        raise JsonPathError(f"Index {token} unavailable in path {path}")
                    current = current[token]
                else:
                    if not isinstance(current, dict) or token not in current:
                        raise JsonPathError(f"Key '{token}' unavailable in path {path}")
                    current = current[token]
            return current
        '''
    ).lstrip()


def _conftest_template() -> str:
    return textwrap.dedent(
        """
        from __future__ import annotations

        import json
        import os
        from pathlib import Path

        import httpx
        import pytest


        def _load_mocks() -> dict[str, object]:
            path_override = os.getenv("MOCK_RESPONSES")
            if path_override:
                target = Path(path_override)
            else:
                target = Path(__file__).parent / "mocks.json"
            if not target.exists():
                return {}
            try:
                content = target.read_text(encoding="utf-8")
                return json.loads(content)
            except Exception:  # pragma: no cover - guardrail
                return {}


        @pytest.fixture(scope="session")
        def base_url() -> str:
            value = os.getenv("BASE_URL")
            if not value:
                raise RuntimeError("BASE_URL environment variable must be set before running tests")
            return value.rstrip("/")


        @pytest.fixture(scope="session")
        def http_client(base_url: str) -> Iterable[httpx.Client]:
            use_live_http = os.getenv("PYTEST_USE_LIVE_HTTP") == "1"
            mocks = {} if use_live_http else _load_mocks()

            if mocks:
                def handler(request: httpx.Request) -> httpx.Response:
                    mock_key = request.headers.get("X-Mock-Key")
                    payload = None
                    if mock_key and mock_key in mocks:
                        payload = mocks[mock_key]
                    fallback = f"{request.method.upper()} {request.url.path}"
                    if payload is None:
                        payload = mocks.get(fallback)
                    if payload is None:
                        return httpx.Response(500, json={"error": f"No mock configured for {fallback}"}, request=request)
                    status_code = payload.get("status_code", 200)
                    headers = payload.get("headers")
                    if "json" in payload:
                        return httpx.Response(status_code, json=payload["json"], headers=headers, request=request)
                    if "body" in payload:
                        body = payload.get("body")
                        if isinstance(body, str):
                            return httpx.Response(status_code, text=body, headers=headers, request=request)
                        if isinstance(body, (bytes, bytearray)):
                            return httpx.Response(status_code, content=bytes(body), headers=headers, request=request)
                    return httpx.Response(status_code, headers=headers, request=request)

                transport = httpx.MockTransport(handler)
                client = httpx.Client(base_url=base_url, transport=transport)
            else:
                client = httpx.Client(base_url=base_url)

            with client:
                yield client
        """
    ).lstrip()


def _readme_template(project_name: str) -> str:
    return textwrap.dedent(
        f"""
        # Pytest export for {project_name}

        ## Usage

        1. Create and activate a virtual environment.
        2. Install dependencies:

           ```bash
           pip install pytest httpx
           ```

        3. Set the required environment variables:

           ```bash
           export BASE_URL=https://api.example.com
           # Optional: export MOCK_RESPONSES=tests/mocks.json
           # Optional: export PYTEST_USE_LIVE_HTTP=1  # to hit the real service instead of mocks
           ```

        4. Run the tests:

           ```bash
           pytest -q
           ```

        The generated suite uses `httpx.Client` for HTTP requests. By default the bundled
        mocks are used to simulate responses. Override the environment variables above to
        target a live environment.
        """
    ).lstrip()
