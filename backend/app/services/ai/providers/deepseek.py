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


class DeepSeekProvider(AIProvider):
    name = "deepseek"

    def __init__(
        self,
        api_key: str,
        *,
        base_url: str = "https://api.deepseek.com",
        model: str = "deepseek-chat",
        timeout: float = 30.0,
        max_retries: int = 3,
        backoff_factor: float = 0.8,
        temperature: float = 0.2,
        max_tokens: int = 1024,
    ) -> None:
        super().__init__()
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.model = model
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
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
            "response_format": {"type": "json_object"},
        }
        raw_response = self._chat_completion(payload)
        content = self._extract_message_content(raw_response)
        try:
            parsed = extract_json_object(content)
        except ValueError as exc:
            self.logger.error("deepseek_json_parse_error", content=content)
            raise AIProviderError("Unable to parse DeepSeek response as JSON", data={"content": content}) from exc

        validated = validator(parsed)
        usage = self._record_usage(TokenUsage.from_raw(raw_response.get("usage")))
        model_name = raw_response.get("model") or self.model
        return ProviderResponse(payload=validated, model=model_name, usage=usage)

    def _chat_completion(self, payload: dict[str, Any]) -> dict[str, Any]:
        url = f"{self.base_url}/v1/chat/completions"
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
                    self.logger.warning("deepseek_timeout", attempt=attempt)
                    if attempt >= self.max_retries:
                        raise AIProviderTimeoutError("DeepSeek request timed out") from exc
                    self._sleep(attempt)
                    continue
                except httpx.HTTPError as exc:
                    self.logger.error("deepseek_transport_error", error=str(exc))
                    raise AIProviderUnavailableError("DeepSeek transport error") from exc

                if response.status_code == 429:
                    self.logger.warning("deepseek_rate_limited", attempt=attempt)
                    if attempt >= self.max_retries:
                        raise AIProviderRateLimitError(
                            "DeepSeek rate limit exceeded",
                            data=self._safe_json(response),
                        )
                    self._sleep(attempt)
                    continue

                if 500 <= response.status_code < 600:
                    self.logger.warning(
                        "deepseek_server_error", status_code=response.status_code, attempt=attempt
                    )
                    if attempt >= self.max_retries:
                        raise AIProviderUnavailableError(
                            "DeepSeek service unavailable",
                            data=self._safe_json(response),
                        )
                    self._sleep(attempt)
                    continue

                try:
                    response.raise_for_status()
                except httpx.HTTPStatusError as exc:
                    error_payload = self._safe_json(response)
                    message = self._extract_error_message(error_payload)
                    self.logger.error(
                        "deepseek_request_failed", status_code=response.status_code, message=message
                    )
                    raise AIProviderError(message or "DeepSeek request failed", data=error_payload) from exc

                return self._safe_json(response)

        raise AIProviderUnavailableError("DeepSeek service unavailable")

    def _extract_message_content(self, response: dict[str, Any]) -> str:
        choices = response.get("choices")
        if not isinstance(choices, list) or not choices:
            raise AIProviderError("DeepSeek response missing choices", data=response)
        first_choice = choices[0]
        if not isinstance(first_choice, dict):
            raise AIProviderError("DeepSeek response missing message", data=response)
        message = first_choice.get("message")
        if not isinstance(message, dict):
            raise AIProviderError("DeepSeek response missing message content", data=response)
        content = message.get("content")
        if isinstance(content, list):
            content = "\n".join(
                part.get("text", "") if isinstance(part, dict) else str(part)
                for part in content
            )
        if not isinstance(content, str):
            raise AIProviderError("DeepSeek response missing content", data=response)
        return content.strip()

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
        error = payload.get("error") if isinstance(payload, dict) else None
        if isinstance(error, dict):
            message = error.get("message") or error.get("msg")
            if isinstance(message, str):
                return message
        message = payload.get("message") if isinstance(payload, dict) else None
        return message if isinstance(message, str) else ""

    def _sleep(self, attempt: int) -> None:
        delay = self._backoff(attempt)
        time.sleep(delay)

    def _backoff(self, attempt: int) -> float:
        base = min(self.backoff_factor * (2 ** (attempt - 1)), self._max_backoff)
        jitter = random.uniform(0, base / 2)
        return base + jitter


__all__ = ["DeepSeekProvider"]
