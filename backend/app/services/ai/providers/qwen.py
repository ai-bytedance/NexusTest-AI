from __future__ import annotations

import json
import random
import time
from typing import Any, Callable

import httpx

from app.logging import get_logger
from app.services.ai.base import (
    AIProvider,
    AIProviderError,
    AIProviderRateLimitError,
    AIProviderTimeoutError,
    AIProviderUnavailableError,
    ProviderResponse,
    TokenUsage,
    extract_json_object,
)
from app.services.ai.prompts import (
    build_generate_assertions_prompts,
    build_generate_cases_prompts,
    build_generate_mock_data_prompts,
    build_summarize_report_prompts,
)
from app.services.ai.validators import (
    validate_generate_assertions,
    validate_generate_cases,
    validate_generate_mock_data,
    validate_summarize_report,
)

Validator = Callable[[dict[str, Any]], dict[str, Any]]


class QwenProvider(AIProvider):
    name = "qwen"

    def __init__(
        self,
        api_key: str,
        *,
        model: str = "qwen-plus",
        base_url: str | None = None,
        timeout: float = 30.0,
        max_retries: int = 3,
        backoff_factor: float = 0.6,
        temperature: float = 0.2,
        max_tokens: int = 1024,
    ) -> None:
        super().__init__()
        self.api_key = api_key
        self.model = model
        self.base_url = (base_url or "https://dashscope.aliyuncs.com").rstrip("/")
        self.timeout = timeout
        self.max_retries = max(1, max_retries)
        self.backoff_factor = max(0.1, backoff_factor)
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.logger = get_logger().bind(provider=self.name)
        self._max_backoff = 12.0

    def generate_test_cases(self, api_spec: dict[str, Any] | str) -> ProviderResponse:
        system_prompt, user_prompt = build_generate_cases_prompts(api_spec)
        return self._invoke_structured(system_prompt, user_prompt, validate_generate_cases)

    def generate_assertions(self, example_response: dict[str, Any] | str) -> ProviderResponse:
        system_prompt, user_prompt = build_generate_assertions_prompts(example_response)
        return self._invoke_structured(system_prompt, user_prompt, validate_generate_assertions)

    def generate_mock_data(self, json_schema: dict[str, Any]) -> ProviderResponse:
        system_prompt, user_prompt = build_generate_mock_data_prompts(json_schema)
        return self._invoke_structured(system_prompt, user_prompt, validate_generate_mock_data)

    def summarize_report(self, report: dict[str, Any]) -> ProviderResponse:
        system_prompt, user_prompt = build_summarize_report_prompts(report)
        return self._invoke_structured(system_prompt, user_prompt, validate_summarize_report)

    def _invoke_structured(
        self,
        system_prompt: str,
        user_prompt: str,
        validator: Validator,
    ) -> ProviderResponse:
        payload = {
            "model": self.model,
            "input": {
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ]
            },
            "parameters": {
                "result_format": "json",
                "temperature": self.temperature,
                "max_tokens": self.max_tokens,
            },
        }
        url = f"{self.base_url}/api/v1/services/aigc/text-generation/generation"
        raw_response = self._send_request(url=url, payload=payload)
        content = self._extract_content(raw_response)
        try:
            parsed = extract_json_object(content)
        except ValueError as exc:
            self.logger.error("qwen_json_parse_error", content=content)
            raise AIProviderError("Unable to parse Qwen response as JSON", data={"content": content}) from exc

        validated = validator(parsed)
        usage = self._record_usage(TokenUsage.from_raw(raw_response.get("usage")))
        model_name = raw_response.get("model") or self.model
        return ProviderResponse(payload=validated, model=model_name, usage=usage)

    def _send_request(self, *, url: str, payload: dict[str, Any]) -> dict[str, Any]:
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        attempt = 0
        with httpx.Client(timeout=self.timeout) as client:
            while attempt < self.max_retries:
                attempt += 1
                try:
                    response = client.post(url, headers=headers, json=payload)
                except httpx.TimeoutException as exc:
                    self.logger.warning("qwen_timeout", attempt=attempt)
                    if attempt >= self.max_retries:
                        raise AIProviderTimeoutError("Qwen request timed out") from exc
                    self._sleep(attempt)
                    continue
                except httpx.HTTPError as exc:
                    self.logger.error("qwen_transport_error", error=str(exc))
                    raise AIProviderUnavailableError("Qwen transport error") from exc

                if response.status_code == 429:
                    self.logger.warning("qwen_rate_limited", attempt=attempt)
                    if attempt >= self.max_retries:
                        raise AIProviderRateLimitError(
                            "Qwen rate limit exceeded",
                            data=self._safe_json(response),
                        )
                    self._sleep(attempt)
                    continue

                if 500 <= response.status_code < 600:
                    self.logger.warning("qwen_server_error", status_code=response.status_code, attempt=attempt)
                    if attempt >= self.max_retries:
                        raise AIProviderUnavailableError(
                            "Qwen service unavailable",
                            data=self._safe_json(response),
                        )
                    self._sleep(attempt)
                    continue

                try:
                    response.raise_for_status()
                except httpx.HTTPStatusError as exc:
                    error_payload = self._safe_json(response)
                    message = self._extract_error_message(error_payload)
                    raise AIProviderError(message or "Qwen request failed", data=error_payload) from exc

                data = self._safe_json(response)
                code = data.get("code") if isinstance(data, dict) else None
                if isinstance(code, int) and code != 200:
                    message = data.get("message") if isinstance(data.get("message"), str) else None
                    raise AIProviderError(message or f"Qwen request failed with code {code}", data=data)
                return data

        raise AIProviderUnavailableError("Qwen service unavailable")

    def _extract_content(self, response: dict[str, Any]) -> str:
        output = response.get("output")
        if isinstance(output, dict):
            text = output.get("text")
            if isinstance(text, str) and text.strip():
                return text.strip()
            choices = output.get("choices")
            if isinstance(choices, list) and choices:
                first_choice = choices[0]
                if isinstance(first_choice, dict):
                    message = first_choice.get("message")
                    if isinstance(message, dict):
                        content = message.get("content")
                        if isinstance(content, str) and content.strip():
                            return content.strip()
        raise AIProviderError("Qwen response missing textual content", data=response)

    def _safe_json(self, response: httpx.Response) -> dict[str, Any]:
        try:
            payload = response.json()
            if isinstance(payload, dict):
                return payload
            return {"data": payload}
        except json.JSONDecodeError:
            return {"status_code": response.status_code, "content": response.text}
        except httpx.DecodingError:
            return {"status_code": response.status_code, "content": response.text}

    def _extract_error_message(self, payload: dict[str, Any]) -> str:
        if not isinstance(payload, dict):
            return ""
        message = payload.get("message")
        return message if isinstance(message, str) else ""

    def _sleep(self, attempt: int) -> None:
        time.sleep(self._backoff(attempt))

    def _backoff(self, attempt: int) -> float:
        base = min(self.backoff_factor * (2 ** (attempt - 1)), self._max_backoff)
        jitter = random.uniform(0, base / 2)
        return base + jitter


__all__ = ["QwenProvider"]
