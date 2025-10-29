from __future__ import annotations

import json
from typing import Any

from app.services.ai.validators import (
    generate_assertions_json_schema,
    generate_cases_json_schema,
    generate_mock_data_json_schema,
    summarize_report_json_schema,
)


def _schema_as_text(schema: dict[str, Any]) -> str:
    return json.dumps(schema, indent=2, ensure_ascii=False)


_CASES_SCHEMA_TEXT = _schema_as_text(generate_cases_json_schema())
_ASSERTIONS_SCHEMA_TEXT = _schema_as_text(generate_assertions_json_schema())
_MOCK_DATA_SCHEMA_TEXT = _schema_as_text(generate_mock_data_json_schema())
_SUMMARY_SCHEMA_TEXT = _schema_as_text(summarize_report_json_schema())


def format_input(value: dict[str, Any] | str) -> str:
    if isinstance(value, str):
        return value
    try:
        return json.dumps(value, indent=2, ensure_ascii=False)
    except (TypeError, ValueError):
        return str(value)


def build_generate_cases_prompts(api_spec: dict[str, Any] | str) -> tuple[str, str]:
    formatted_spec = format_input(api_spec)
    system_prompt = (
        "You are an expert API testing assistant. Generate comprehensive API test cases covering "
        "positive, negative, and boundary scenarios. Always respond with a JSON object that matches the "
        "provided schema."
    )
    user_prompt = (
        "Generate API test cases using the following specification.\n\n"
        f"Specification:\n{formatted_spec}\n\n"
        "Respond with a JSON object following this schema:\n"
        f"{_CASES_SCHEMA_TEXT}"
    )
    return system_prompt, user_prompt


def build_generate_assertions_prompts(example_response: dict[str, Any] | str) -> tuple[str, str]:
    formatted_response = format_input(example_response)
    system_prompt = (
        "You generate precise API response assertions. Focus on status codes, headers, JSON paths, and "
        "important field validations. Always return a JSON object matching the provided schema."
    )
    user_prompt = (
        "Create structured assertions for the following API response.\n\n"
        f"Example response:\n{formatted_response}\n\n"
        "Respond with a JSON object following this schema:\n"
        f"{_ASSERTIONS_SCHEMA_TEXT}"
    )
    return system_prompt, user_prompt


def build_generate_mock_data_prompts(json_schema: dict[str, Any]) -> tuple[str, str]:
    formatted_schema = format_input(json_schema)
    system_prompt = (
        "You create realistic mock JSON payloads that strictly comply with a provided JSON schema."
        " Always respond with a JSON object matching the specified schema."
    )
    user_prompt = (
        "Generate a mock payload that satisfies the following JSON schema.\n\n"
        f"JSON schema:\n{formatted_schema}\n\n"
        "Respond with a JSON object following this schema:\n"
        f"{_MOCK_DATA_SCHEMA_TEXT}"
    )
    return system_prompt, user_prompt


def build_summarize_report_prompts(report: dict[str, Any] | str) -> tuple[str, str]:
    formatted_report = format_input(report)
    system_prompt = (
        "You summarize API test execution reports into concise, actionable Markdown. Highlight pass/fail "
        "counts, flaky behaviour, regressions, and next steps. Always output JSON matching the schema."
    )
    user_prompt = (
        "Summarize the following test execution report.\n\n"
        f"Report data:\n{formatted_report}\n\n"
        "Respond with a JSON object following this schema:\n"
        f"{_SUMMARY_SCHEMA_TEXT}"
    )
    return system_prompt, user_prompt
