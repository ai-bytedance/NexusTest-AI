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


class GeminiProvider(AIProvider):
    name = "gemini"

    def __init__(
        self,
        api_key: str,
        *,
        model: str = "gemini-1.5-flash",
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
        self.base_url = (base_url or "https://generativelanguage.googleapis.com").rstrip("/")
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
            "systemInstruction": {
                "parts": [{"text": system_prompt}],
            },
            "contents": [
                {
                    "role": "user",
                    "parts": [{"text": user_prompt}],
                }
            ],
            "generationConfig": {
                "temperature": self.temperature,
                "maxOutputTokens": self.max_tokens,
                "responseMimeType": "application/json",
            },
        }
        url = f"{self.base_url}/v1beta/models/{self.model}:generateContent"
        params = {"key": self.api_key}
        raw_response = self._send_request(url=url, payload=payload, params=params)
        content = self._extract_content(raw_response)
        try:
            parsed = extract_json_object(content)
        except ValueError as exc:
            self.logger.error("gemini_json_parse_error", content=content)
            raise AIProviderError("Unable to parse Gemini response as JSON", data={"content": content}) from exc

        validated = validator(parsed)
        usage = self._record_usage(TokenUsage.from_raw(raw_response.get("usageMetadata")))
        model_name = raw_response.get("modelVersion") or self.model
        return ProviderResponse(payload=validated, model=model_name, usage=usage)

    def _send_request(
        self,
        *,
        url: str,
        payload: dict[str, Any],
        params: dict[str, Any],
    ) -> dict[str, Any]:
        headers = {"Content-Type": "application/json"}
        attempt = 0
        with httpx.Client(timeout=self.timeout) as client:
            while attempt < self.max_retries:
                attempt += 1
                try:
                    response = client.post(url, headers=headers, json=payload, params=params)
                except httpx.TimeoutException as exc:
                    self.logger.warning("gemini_timeout", attempt=attempt)
                    if attempt >= self.max_retries:
                        raise AIProviderTimeoutError("Gemini request timed out") from exc
                    self._sleep(attempt)
                    continue
                except httpx.HTTPError as exc:
                    self.logger.error("gemini_transport_error", error=str(exc))
                    raise AIProviderUnavailableError("Gemini transport error") from exc

                if response.status_code == 429:
                    self.logger.warning("gemini_rate_limited", attempt=attempt)
                    if attempt >= self.max_retries:
                        raise AIProviderRateLimitError(
                            "Gemini rate limit exceeded",
                            data=self._safe_json(response),
                        )
                    self._sleep(attempt)
                    continue

                if 500 <= response.status_code < 600:
                    self.logger.warning("gemini_server_error", status_code=response.status_code, attempt=attempt)
                    if attempt >= self.max_retries:
                        raise AIProviderUnavailableError(
                            "Gemini service unavailable",
                            data=self._safe_json(response),
                        )
                    self._sleep(attempt)
                    continue

                try:
                    response.raise_for_status()
                except httpx.HTTPStatusError as exc:
                    error_payload = self._safe_json(response)
                    message = self._extract_error_message(error_payload)
                    raise AIProviderError(message or "Gemini request failed", data=error_payload) from exc

                return self._safe_json(response)

        raise AIProviderUnavailableError("Gemini service unavailable")

    def _extract_content(self, response: dict[str, Any]) -> str:
        candidates = response.get("candidates")
        if not isinstance(candidates, list) or not candidates:
            raise AIProviderError("Gemini response missing candidates", data=response)
        for candidate in candidates:
            content = candidate.get("content") if isinstance(candidate, dict) else None
            if not isinstance(content, dict):
                continue
            parts = content.get("parts")
            if isinstance(parts, list):
                texts = [
                    part.get("text", "") if isinstance(part, dict) else str(part)
                    for part in parts
                ]
                joined = "\n".join(texts).strip()
                if joined:
                    return joined
        prompt_feedback = response.get("promptFeedback")
        if isinstance(prompt_feedback, dict):
            block_reason = prompt_feedback.get("blockReason")
            if isinstance(block_reason, str):
                raise AIProviderError(f"Gemini request blocked: {block_reason}", data=response)
        raise AIProviderError("Gemini response missing textual content", data=response)

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
        error = payload.get("error")
        if isinstance(error, dict):
            message = error.get("message") or error.get("status")
            if isinstance(message, str):
                return message
        return ""

    def _sleep(self, attempt: int) -> None:
        time.sleep(self._backoff(attempt))

    def _backoff(self, attempt: int) -> float:
        base = min(self.backoff_factor * (2 ** (attempt - 1)), self._max_backoff)
        jitter = random.uniform(0, base / 2)
        return base + jitter


__all__ = ["GeminiProvider"]
