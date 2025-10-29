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


class OpenAIProvider(AIProvider):
    name = "openai"

    def __init__(
        self,
        api_key: str,
        *,
        model: str = "gpt-4o-mini",
        base_url: str | None = None,
        timeout: float = 30.0,
        max_retries: int = 3,
        backoff_factor: float = 0.6,
        temperature: float = 0.2,
        max_tokens: int = 1024,
        use_responses_api: bool = True,
    ) -> None:
        super().__init__()
        self.api_key = api_key
        self.model = model
        self.base_url = (base_url or "https://api.openai.com").rstrip("/")
        self.timeout = timeout
        self.max_retries = max(1, max_retries)
        self.backoff_factor = max(0.1, backoff_factor)
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.use_responses_api = use_responses_api
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
        raw_response: dict[str, Any]
        content: str

        if self.use_responses_api:
            try:
                raw_response = self._responses_request(system_prompt, user_prompt)
                content = self._extract_responses_content(raw_response)
            except AIProviderError as exc:
                self.logger.info("openai_responses_fallback", reason=str(exc))
                raw_response = self._chat_request(system_prompt, user_prompt)
                content = self._extract_chat_content(raw_response)
        else:
            raw_response = self._chat_request(system_prompt, user_prompt)
            content = self._extract_chat_content(raw_response)

        try:
            parsed = extract_json_object(content)
        except ValueError as exc:
            self.logger.error("openai_json_parse_error", content=content)
            raise AIProviderError("Unable to parse OpenAI response as JSON", data={"content": content}) from exc

        validated = validator(parsed)
        usage = self._record_usage(TokenUsage.from_raw(raw_response.get("usage")))
        model_name = raw_response.get("model") or self.model
        return ProviderResponse(payload=validated, model=model_name, usage=usage)

    def _responses_request(self, system_prompt: str, user_prompt: str) -> dict[str, Any]:
        payload = {
            "model": self.model,
            "temperature": self.temperature,
            "response_format": {"type": "json_object"},
            "max_output_tokens": self.max_tokens,
            "input": [
                {"role": "system", "content": [{"type": "text", "text": system_prompt}]},
                {"role": "user", "content": [{"type": "text", "text": user_prompt}]},
            ],
        }
        url = f"{self.base_url}/v1/responses"
        return self._send_request(url=url, payload=payload, context="responses")

    def _chat_request(self, system_prompt: str, user_prompt: str) -> dict[str, Any]:
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
        url = f"{self.base_url}/v1/chat/completions"
        return self._send_request(url=url, payload=payload, context="chat")

    def _send_request(self, *, url: str, payload: dict[str, Any], context: str) -> dict[str, Any]:
        attempt = 0
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        with httpx.Client(timeout=self.timeout) as client:
            while attempt < self.max_retries:
                attempt += 1
                try:
                    response = client.post(url, headers=headers, json=payload)
                except httpx.TimeoutException as exc:
                    self.logger.warning("openai_timeout", attempt=attempt, context=context)
                    if attempt >= self.max_retries:
                        raise AIProviderTimeoutError("OpenAI request timed out") from exc
                    self._sleep(attempt)
                    continue
                except httpx.HTTPError as exc:
                    self.logger.error("openai_transport_error", error=str(exc), context=context)
                    raise AIProviderUnavailableError("OpenAI transport error") from exc

                if response.status_code == 429:
                    self.logger.warning("openai_rate_limited", attempt=attempt, context=context)
                    if attempt >= self.max_retries:
                        raise AIProviderRateLimitError(
                            "OpenAI rate limit exceeded",
                            data=self._safe_json(response),
                        )
                    self._sleep(attempt)
                    continue

                if 500 <= response.status_code < 600:
                    self.logger.warning(
                        "openai_server_error",
                        status_code=response.status_code,
                        attempt=attempt,
                        context=context,
                    )
                    if attempt >= self.max_retries:
                        raise AIProviderUnavailableError(
                            "OpenAI service unavailable",
                            data=self._safe_json(response),
                        )
                    self._sleep(attempt)
                    continue

                try:
                    response.raise_for_status()
                except httpx.HTTPStatusError as exc:
                    error_payload = self._safe_json(response)
                    message = self._extract_error_message(error_payload)
                    raise AIProviderError(
                        message or f"OpenAI {context} request failed",
                        data=error_payload,
                    ) from exc

                return self._safe_json(response)

        raise AIProviderUnavailableError("OpenAI service unavailable")

    def _extract_responses_content(self, response: dict[str, Any]) -> str:
        output = response.get("output")
        if not isinstance(output, list) or not output:
            raise AIProviderError("OpenAI responses output missing", data=response)
        for item in output:
            if not isinstance(item, dict):
                continue
            if item.get("type") == "message":
                content = item.get("content")
                if isinstance(content, list):
                    texts = [
                        part.get("text", "") if isinstance(part, dict) else str(part)
                        for part in content
                    ]
                    joined = "\n".join(texts).strip()
                    if joined:
                        return joined
                elif isinstance(content, str) and content.strip():
                    return content.strip()
        text = response.get("output_text")
        if isinstance(text, str) and text.strip():
            return text.strip()
        raise AIProviderError("OpenAI responses output missing content", data=response)

    def _extract_chat_content(self, response: dict[str, Any]) -> str:
        choices = response.get("choices")
        if not isinstance(choices, list) or not choices:
            raise AIProviderError("OpenAI response missing choices", data=response)
        first_choice = choices[0]
        if not isinstance(first_choice, dict):
            raise AIProviderError("OpenAI response missing message", data=response)
        message = first_choice.get("message")
        if not isinstance(message, dict):
            raise AIProviderError("OpenAI response missing message content", data=response)
        content = message.get("content")
        if isinstance(content, list):
            content = "\n".join(
                part.get("text", "") if isinstance(part, dict) else str(part)
                for part in content
            )
        if not isinstance(content, str):
            raise AIProviderError("OpenAI response missing content", data=response)
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
        if not isinstance(payload, dict):
            return ""
        error = payload.get("error")
        if isinstance(error, dict):
            message = error.get("message") or error.get("code")
            if isinstance(message, str):
                return message
        message = payload.get("message")
        return message if isinstance(message, str) else ""

    def _sleep(self, attempt: int) -> None:
        time.sleep(self._backoff(attempt))

    def _backoff(self, attempt: int) -> float:
        base = min(self.backoff_factor * (2 ** (attempt - 1)), self._max_backoff)
        jitter = random.uniform(0, base / 2)
        return base + jitter


__all__ = ["OpenAIProvider"]
