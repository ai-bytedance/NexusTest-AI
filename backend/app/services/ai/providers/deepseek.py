from __future__ import annotations

import json
import time
from typing import Any

import httpx

from app.logging import get_logger
from app.services.ai.base import (
    AIProvider,
    AIProviderError,
    AIProviderRateLimitError,
    AIProviderTimeoutError,
    AIProviderUnavailableError,
)


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
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout = timeout
        self.max_retries = max(1, max_retries)
        self.backoff_factor = max(0.1, backoff_factor)
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.logger = get_logger().bind(provider=self.name)

    def generate_test_cases(self, api_spec: dict[str, Any] | str) -> dict[str, Any]:
        prompt = self._format_input(api_spec)
        response = self._invoke_structured(
            system_prompt=(
                "You are an expert API testing assistant. Generate high quality API test "
                "cases covering positive, negative, and edge scenarios. Always respond "
                "with a valid JSON object following the required schema."
            ),
            user_prompt=(
                "API specification for generating test cases:\n\n"
                f"{prompt}\n\n"
                "Respond with a JSON object: {\"cases\": [ { ... } ]}. Each case must contain\n"
                "`name`, `description`, `steps` (list of instructions), and `assertions` (list of assertions)."
            ),
        )
        cases = response.get("cases")
        if not isinstance(cases, list):
            raise AIProviderError("DeepSeek response did not include 'cases'", data=response)
        return {"cases": cases}

    def generate_assertions(self, example_response: dict[str, Any] | str) -> dict[str, Any]:
        prompt = self._format_input(example_response)
        response = self._invoke_structured(
            system_prompt=(
                "You are an assistant that creates response assertions for API automation. "
                "Return structured assertion definitions suitable for JSONPath and status checks."
            ),
            user_prompt=(
                "Given this example API response, create a set of assertions.\n\n"
                f"Response:\n{prompt}\n\n"
                "Respond with a JSON object: {\"assertions\": [ { ... } ]}. Each assertion must include\n"
                "`name`, `operator`, and the relevant fields (`expected`, `actual`, or `path`)."
            ),
        )
        assertions = response.get("assertions")
        if not isinstance(assertions, list):
            raise AIProviderError("DeepSeek response did not include 'assertions'", data=response)
        return {"assertions": assertions}

    def generate_mock_data(self, json_schema: dict[str, Any]) -> dict[str, Any]:
        response = self._invoke_structured(
            system_prompt=(
                "You generate realistic mock data that conforms to the provided JSON schema. "
                "Always return a JSON object with a top-level 'data' key."
            ),
            user_prompt=(
                "Create a mock payload that matches this JSON schema:\n\n"
                f"{self._format_input(json_schema)}\n\n"
                "Respond with: {\"data\": <mock object>}."
            ),
        )
        data = response.get("data")
        if not isinstance(data, (dict, list)):  # allow list payloads if schema defines arrays
            raise AIProviderError("DeepSeek response did not include mock 'data'", data=response)
        return {"data": data}

    def summarize_report(self, report: dict[str, Any]) -> str:
        response = self._invoke_structured(
            system_prompt=(
                "You summarize API test execution reports into clear Markdown formatted notes. "
                "Highlight pass/fail counts, flaky areas, regression risks, and next actions."
            ),
            user_prompt=(
                "Summarize the following test execution report.\n\n"
                f"{self._format_input(report)}\n\n"
                "Respond with a JSON object: {\"markdown\": "
                """<summary markdown string>""""} (use double quotes)."
            ),
        )
        markdown = response.get("markdown")
        if not isinstance(markdown, str):
            raise AIProviderError("DeepSeek response did not include 'markdown'", data=response)
        return markdown.strip()

    def _invoke_structured(self, *, system_prompt: str, user_prompt: str) -> dict[str, Any]:
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
        return self._extract_json_payload(raw_response)

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
                    time.sleep(self._backoff(attempt))
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
                    time.sleep(self._backoff(attempt))
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
                    time.sleep(self._backoff(attempt))
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

    def _extract_json_payload(self, response: dict[str, Any]) -> dict[str, Any]:
        choices = response.get("choices")
        if not isinstance(choices, list) or not choices:
            raise AIProviderError("DeepSeek response missing choices", data=response)
        message = choices[0].get("message") if isinstance(choices[0], dict) else None
        if not isinstance(message, dict):
            raise AIProviderError("DeepSeek response missing message", data=response)
        content = message.get("content")
        if not isinstance(content, str):
            raise AIProviderError("DeepSeek response missing content", data=response)
        text = content.strip()
        if text.startswith("```"):
            segments = [segment.strip() for segment in text.split("```") if segment.strip()]
            for segment in segments:
                if segment.startswith("{"):
                    text = segment
                    break
        try:
            return json.loads(text)
        except json.JSONDecodeError as exc:
            self.logger.error("deepseek_json_parse_error", content=text)
            raise AIProviderError("Unable to parse DeepSeek response as JSON", data={"content": content}) from exc

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

    def _format_input(self, value: dict[str, Any] | str) -> str:
        if isinstance(value, str):
            return value
        try:
            return json.dumps(value, indent=2, ensure_ascii=False)
        except (TypeError, ValueError):
            return str(value)

    def _backoff(self, attempt: int) -> float:
        return min(self.backoff_factor * (2 ** (attempt - 1)), 10.0)


__all__ = ["DeepSeekProvider"]
