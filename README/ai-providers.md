# AI Providers Configuration

This guide describes how to configure and operate the multi-provider AI integration that powers the `/api/v1/ai/*` endpoints. The platform now supports OpenAI, Anthropic Claude, Google Gemini, Alibaba Qwen, Zhipu GLM, ByteDance Doubao, DeepSeek, and a deterministic mock provider.

## Selecting a provider

By default the backend uses the value of the `PROVIDER` environment variable. Accepted values are:

```
mock | deepseek | openai | anthropic | claude | gemini | google |
qwen | glm | zhipu | doubao
```

You can also override the provider per request by adding a `provider` query parameter, for example:

```
POST /api/v1/ai/generate-cases?provider=openai
POST /api/v1/reports/{id}/summarize?provider=anthropic
```

When credentials are missing the system automatically falls back to the mock provider and logs a warning. All providers expose the same four capabilities and return the same validated JSON structures.

## Environment variables

Each provider can be configured with API keys, optional custom base URLs (for gateways), and model identifiers. Default model values are supplied for convenience but you can override them without code changes.

| Provider  | Required variables | Optional variables | Default model |
|-----------|--------------------|--------------------|---------------|
| DeepSeek  | `DEEPSEEK_API_KEY` | `DEEPSEEK_BASE_URL`, `DEEPSEEK_MODEL` | `deepseek-chat` |
| OpenAI    | `OPENAI_API_KEY`   | `OPENAI_BASE_URL`, `OPENAI_MODEL`     | `gpt-4o-mini` |
| Anthropic | `ANTHROPIC_API_KEY`| `ANTHROPIC_BASE_URL`, `ANTHROPIC_MODEL` | `claude-3-5-sonnet-20240620` |
| Gemini    | `GOOGLE_API_KEY`   | `GOOGLE_BASE_URL`, `GEMINI_MODEL`     | `gemini-1.5-flash` |
| Qwen      | `QWEN_API_KEY`     | `QWEN_BASE_URL`, `QWEN_MODEL`         | `qwen-plus` |
| GLM       | `ZHIPU_API_KEY`    | `ZHIPU_BASE_URL`, `GLM_MODEL`         | `glm-4-airx` |
| Doubao    | `DOUBAO_API_KEY`   | `DOUBAO_BASE_URL`, `DOUBAO_MODEL`     | `doubao-pro-4k` |

All providers honour the global `REQUEST_TIMEOUT_SECONDS` for HTTP calls.

## Response consistency

Every provider validates its JSON output against shared Pydantic schemas to ensure deterministic responses:

- `generate-cases`: `{ "cases": [...] }`
- `generate-assertions`: `{ "assertions": [...] }`
- `mock-data`: `{ "data": <object|array> }`
- `summarize-report`: `{ "markdown": "..." }`

If a provider cannot return valid JSON, the request fails with a structured error and a vendor-neutral error code (`AI001`‒`AI006`).

Strict JSON modes are requested where supported (OpenAI Responses API, Claude response format, Gemini MIME hints, etc.). When JSON mode is not honoured, the service performs robust extraction from fenced code blocks before validation.

## Token usage metrics

Successful invocations now persist model names and token usage counts in the `ai_tasks` table:

- `model`
- `prompt_tokens`
- `completion_tokens`
- `total_tokens`

The task output payload continues to store the validated JSON returned to the caller. These metrics are available for analytics and billing without additional API calls.

## Error handling and retries

Every provider shares the same retry strategy:

- Automatic retries on `429` and `5xx` responses with exponential backoff and jitter.
- Transport errors raise `AI004` (unavailable).
- Timeouts raise `AI003`.
- Rate limits surface as `AI002`.

Raw provider error payloads are included in the response envelope under `detail.data` for debugging.

## Testing

Unit tests mock HTTP responses for each provider to verify:

- Successful JSON parsing and schema validation.
- Retry behaviour and error mappings for rate limits and server failures.

Optional integration smoke tests can be added locally by exporting the relevant API key(s); the pytest suite will pick them up automatically and skip them when the variables are absent.

## Troubleshooting

- **Unexpected mock provider in use**: check the logs for `ai_provider_missing_credentials` warnings and ensure the appropriate `*_API_KEY` environment variable is set.
- **JSON decoding errors**: inspect the recorded `ai_tasks.output_payload` and the error payload returned by the provider for malformed responses.
- **Rate limits reached**: consider lowering concurrency or enabling a gateway with higher quotas; the service already retries three times with exponential backoff.
- **Gateway deployments**: set the corresponding `*_BASE_URL` variable to point at your gateway endpoint while leaving the official API key and model identifiers unchanged.
